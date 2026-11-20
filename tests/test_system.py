import os
import sys
import unittest
import datetime

# Ensure project root in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import Config
from database import get_db_connection, init_db
from attendance_service import AttendanceService, ReportService
from face_engine import face_engine, FaceEngine
from seed_data import generate_synthetic_face
import cv2
import numpy as np

class SmartAttendanceSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize database fresh
        init_db(drop=False)

    def test_fr001_authentication_and_hashing(self):
        """Test FR-001: Passwords stored as salted hashes, roles enforced."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password_hash, role FROM users WHERE username = 'admin'")
        admin = cur.fetchone()
        self.assertIsNotNone(admin)
        self.assertEqual(admin['role'], 'ADMIN')
        # Ensure password is not plain text
        self.assertNotEqual(admin['password_hash'], 'admin123')
        self.assertTrue(admin['password_hash'].startswith('scrypt:') or admin['password_hash'].startswith('pbkdf2:'))
        conn.close()

    def test_fr002_student_registration_and_duplicate_rejection(self):
        """Test FR-002: Add student, reject duplicate roll number."""
        conn = get_db_connection()
        cur = conn.cursor()

        roll = "TEST_ROLL_99"
        cur.execute("DELETE FROM students WHERE roll_no = ?", (roll,))
        conn.commit()

        # Insert new student
        cur.execute("""
            INSERT INTO students (roll_no, full_name, class_name, is_active, registered_by)
            VALUES (?, 'Test Student', 'TEST-CLASS', 1, 1)
        """, (roll,))
        conn.commit()

        # Attempt to insert duplicate roll number - should raise IntegrityError
        with self.assertRaises(Exception):
            cur.execute("""
                INSERT INTO students (roll_no, full_name, class_name, is_active, registered_by)
                VALUES (?, 'Duplicate Student', 'TEST-CLASS', 1, 1)
            """, (roll,))
            conn.commit()

        # Clean up test student
        cur.execute("DELETE FROM students WHERE roll_no = ?", (roll,))
        conn.commit()
        conn.close()

    def test_fr003_fr004_face_detection_and_preprocessing(self):
        """Test FR-003 & FR-004: Face detection and normalization."""
        # Create a synthetic face
        img = generate_synthetic_face(1, "Test Face")
        processed = FaceEngine.preprocess_face(img)
        self.assertEqual(processed.shape, (200, 200))
        self.assertEqual(len(processed.shape), 2)  # Single channel (grayscale)

    def test_fr005_fr006_fr007_fr008_attendance_marking_and_deduplication(self):
        """Test FR-006, FR-007, FR-008: Attendance marking, deduplication, absentees marking."""
        conn = get_db_connection()
        cur = conn.cursor()

        test_class = "TEST-SEC-A"
        # Create 2 test students
        cur.execute("DELETE FROM students WHERE class_name = ?", (test_class,))
        conn.commit()

        cur.execute("""
            INSERT INTO students (roll_no, full_name, class_name, is_active, registered_by)
            VALUES ('TEST_A1', 'Present Student', ?, 1, 1)
        """, (test_class,))
        st1_id = cur.lastrowid

        cur.execute("""
            INSERT INTO students (roll_no, full_name, class_name, is_active, registered_by)
            VALUES ('TEST_A2', 'Absent Student', ?, 1, 1)
        """, (test_class,))
        st2_id = cur.lastrowid

        # Create OPEN session
        now_date = datetime.date.today().strftime("%Y-%m-%d")
        cur.execute("""
            INSERT INTO attendance_sessions (subject, class_name, session_date, start_time, status, created_by)
            VALUES ('Test Subject', ?, ?, '10:00:00', 'OPEN', 1)
        """, (test_class, now_date))
        session_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Mark st1 PRESENT
        marked_first = AttendanceService.mark_present(session_id, st1_id, 92.5)
        self.assertTrue(marked_first, "Student 1 should be marked PRESENT")

        # Attempt duplicate mark (Deduplication check)
        marked_second = AttendanceService.mark_present(session_id, st1_id, 95.0)
        self.assertFalse(marked_second, "Duplicate mark should be rejected / ignored")

        # Verify record in database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM attendance_records WHERE session_id = ? AND student_id = ?", (session_id, st1_id))
        rec = cur.fetchone()
        self.assertIsNotNone(rec)
        self.assertEqual(rec['status'], 'PRESENT')
        self.assertIsNotNone(rec['marked_at'], "FR-007: Timestamp must be recorded for PRESENT")
        self.assertEqual(rec['confidence'], 92.5)

        # Verify only 1 record exists (no duplicate)
        cur.execute("SELECT COUNT(*) FROM attendance_records WHERE session_id = ? AND student_id = ?", (session_id, st1_id))
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()

        # End session -> st2 must be marked ABSENT
        absent_count = AttendanceService.mark_absentees(session_id)
        self.assertEqual(absent_count, 1, "Exactly 1 student should be marked ABSENT")

        summary = AttendanceService.get_session_summary(session_id)
        self.assertEqual(summary['session']['status'], 'CLOSED')
        self.assertEqual(summary['present_count'], 1)
        self.assertEqual(summary['absent_count'], 1)
        self.assertEqual(summary['total_students'], 2)
        self.assertEqual(summary['percentage'], 50.0)

        # Clean up test records after verification
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM attendance_sessions WHERE session_id = ?", (session_id,))
        cur.execute("DELETE FROM students WHERE class_name = ?", (test_class,))
        conn.commit()
        conn.close()

    def test_fr009_attendance_search(self):
        """Test FR-009: Search attendance records by filters."""
        results = ReportService.search({'class_name': 'CAMSA'})
        self.assertIsInstance(results, list)
        if len(results) > 0:
            self.assertEqual(results[0]['class_name'], 'CAMSA')

    def test_fr010_attendance_percentage_calculation(self):
        """Test FR-010: Percentage calculation (Attended / Total * 100)."""
        report = ReportService.generate_report(class_name='CAMSA')
        self.assertIsInstance(report, list)
        self.assertGreater(len(report), 0)
        for row in report:
            self.assertIn('percentage', row)
            if row['total_sessions'] > 0:
                expected_pct = round((row['attended_sessions'] / row['total_sessions']) * 100.0, 2)
                self.assertEqual(row['percentage'], expected_pct)

if __name__ == '__main__':
    unittest.main()
