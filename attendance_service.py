import datetime
from database import get_db_connection

class AttendanceService:
    @staticmethod
    def mark_present(session_id, student_id, confidence):
        """
        Marks student as PRESENT for the given session if not already marked.
        Enforces deduplication both in logic and database uniqueness constraint.
        Returns: True if newly marked, False if already marked or error.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # Check if session is OPEN
            cur.execute("SELECT status, class_name FROM attendance_sessions WHERE session_id = ?", (session_id,))
            session = cur.fetchone()
            if not session or session['status'] != 'OPEN':
                conn.close()
                return False

            # Verify student belongs to this session's class and is active
            cur.execute("SELECT student_id, class_name FROM students WHERE student_id = ? AND is_active = 1", (student_id,))
            student = cur.fetchone()
            if not student or student['class_name'] != session['class_name']:
                conn.close()
                return False

            # Check if already marked (deduplication check)
            cur.execute(
                "SELECT record_id FROM attendance_records WHERE session_id = ? AND student_id = ?",
                (session_id, student_id)
            )
            existing = cur.fetchone()
            if existing:
                conn.close()
                return False

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO attendance_records (session_id, student_id, status, marked_at, confidence)
                VALUES (?, ?, 'PRESENT', ?, ?)
            """, (session_id, student_id, now, round(confidence, 2)))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            # Handles duplicate key constraint gracefully
            conn.rollback()
            conn.close()
            return False

    @staticmethod
    def mark_absentees(session_id):
        """
        When session ends, all active students of the session's class who were
        not marked PRESENT are recorded as ABSENT (marked_at=NULL, confidence=NULL).
        Updates session status to CLOSED and sets end_time.
        Returns: number of absentees marked.
        """
        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute("SELECT class_name, status FROM attendance_sessions WHERE session_id = ?", (session_id,))
            session = cur.fetchone()
            if not session:
                conn.close()
                return 0

            class_name = session['class_name']

            # Find active students in this class not yet recorded in this session
            cur.execute("""
                SELECT student_id FROM students
                WHERE class_name = ? AND is_active = 1
                AND student_id NOT IN (
                    SELECT student_id FROM attendance_records WHERE session_id = ?
                )
            """, (class_name, session_id))
            absent_students = cur.fetchall()

            for s in absent_students:
                cur.execute("""
                    INSERT OR IGNORE INTO attendance_records (session_id, student_id, status, marked_at, confidence)
                    VALUES (?, ?, 'ABSENT', NULL, NULL)
                """, (session_id, s['student_id']))

            # Close the session
            now_time = datetime.datetime.now().strftime("%H:%M:%S")
            cur.execute("""
                UPDATE attendance_sessions
                SET status = 'CLOSED', end_time = ?
                WHERE session_id = ?
            """, (now_time, session_id))

            conn.commit()
            absent_count = len(absent_students)
            conn.close()
            return absent_count
        except Exception as e:
            print(f"[AttendanceService] Error marking absentees: {e}")
            conn.rollback()
            conn.close()
            return 0

    @staticmethod
    def get_session_summary(session_id):
        """Returns statistics of an attendance session."""
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT s.*, u.full_name as teacher_name
            FROM attendance_sessions s
            JOIN users u ON s.created_by = u.user_id
            WHERE s.session_id = ?
        """, (session_id,))
        session = cur.fetchone()
        
        if not session:
            conn.close()
            return None

        cur.execute("""
            SELECT 
                COUNT(*) as total_students,
                SUM(CASE WHEN ar.status = 'PRESENT' THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN ar.status = 'ABSENT' THEN 1 ELSE 0 END) as absent_count
            FROM attendance_records ar
            WHERE ar.session_id = ?
        """, (session_id,))
        stats = cur.fetchone()

        cur.execute("""
            SELECT ar.*, st.roll_no, st.full_name as student_name
            FROM attendance_records ar
            JOIN students st ON ar.student_id = st.student_id
            WHERE ar.session_id = ?
            ORDER BY ar.status DESC, ar.marked_at ASC, st.roll_no ASC
        """, (session_id,))
        records = cur.fetchall()

        conn.close()
        
        total = stats['total_students'] or 0
        present = stats['present_count'] or 0
        absent = stats['absent_count'] or 0
        pct = round((present / total * 100.0), 2) if total > 0 else 0.0

        return {
            "session": dict(session),
            "total_students": total,
            "present_count": present,
            "absent_count": absent,
            "percentage": pct,
            "records": [dict(r) for r in records]
        }


class ReportService:
    @staticmethod
    def search(filters=None):
        """
        Search attendance records with dynamic filters:
        roll_no, full_name, class_name, subject, start_date, end_date, status.
        """
        filters = filters or {}
        conn = get_db_connection()
        cur = conn.cursor()

        query = """
            SELECT 
                ar.record_id,
                ar.session_id,
                ar.student_id,
                ar.status,
                ar.marked_at,
                ar.confidence,
                st.roll_no,
                st.full_name as student_name,
                st.class_name,
                se.subject,
                se.session_date,
                se.start_time,
                se.end_time,
                u.full_name as teacher_name
            FROM attendance_records ar
            JOIN students st ON ar.student_id = st.student_id
            JOIN attendance_sessions se ON ar.session_id = se.session_id
            JOIN users u ON se.created_by = u.user_id
            WHERE 1=1
        """
        params = []

        if filters.get('roll_no'):
            query += " AND st.roll_no LIKE ?"
            params.append(f"%{filters['roll_no']}%")

        if filters.get('student_name'):
            query += " AND st.full_name LIKE ?"
            params.append(f"%{filters['student_name']}%")

        if filters.get('class_name'):
            query += " AND se.class_name = ?"
            params.append(filters['class_name'])

        if filters.get('subject'):
            query += " AND se.subject LIKE ?"
            params.append(f"%{filters['subject']}%")

        if filters.get('start_date'):
            query += " AND se.session_date >= ?"
            params.append(filters['start_date'])

        if filters.get('end_date'):
            query += " AND se.session_date <= ?"
            params.append(filters['end_date'])

        if filters.get('status'):
            query += " AND ar.status = ?"
            params.append(filters['status'])

        query += " ORDER BY se.session_date DESC, ar.marked_at DESC, st.roll_no ASC"

        cur.execute(query, params)
        records = [dict(r) for r in cur.fetchall()]
        conn.close()
        return records

    @staticmethod
    def calculate_percentage(student_id, class_name=None):
        """
        Calculates student attendance percentage:
        (total sessions attended / total sessions held) * 100.
        """
        conn = get_db_connection()
        cur = conn.cursor()

        query_total = """
            SELECT COUNT(DISTINCT se.session_id) as total_sessions
            FROM attendance_sessions se
            JOIN attendance_records ar ON se.session_id = ar.session_id
            WHERE ar.student_id = ?
        """
        cur.execute(query_total, (student_id,))
        total = cur.fetchone()['total_sessions']

        query_present = """
            SELECT COUNT(*) as attended_sessions
            FROM attendance_records
            WHERE student_id = ? AND status = 'PRESENT'
        """
        cur.execute(query_present, (student_id,))
        attended = cur.fetchone()['attended_sessions']

        conn.close()

        pct = round((attended / total * 100.0), 2) if total > 0 else 0.0
        return {
            "student_id": student_id,
            "total_sessions": total,
            "attended_sessions": attended,
            "percentage": pct
        }

    @staticmethod
    def generate_report(class_name=None, start_date=None, end_date=None):
        """
        Generates aggregate attendance report for each student:
        Roll No, Name, Class, Total Sessions, Attended, Absent, Attendance %
        """
        conn = get_db_connection()
        cur = conn.cursor()

        query = """
            SELECT 
                st.student_id,
                st.roll_no,
                st.full_name,
                st.class_name,
                COUNT(ar.record_id) as total_sessions,
                SUM(CASE WHEN ar.status = 'PRESENT' THEN 1 ELSE 0 END) as attended_sessions,
                SUM(CASE WHEN ar.status = 'ABSENT' THEN 1 ELSE 0 END) as absent_sessions
            FROM students st
            LEFT JOIN attendance_records ar ON st.student_id = ar.student_id
            LEFT JOIN attendance_sessions se ON ar.session_id = se.session_id
            WHERE st.is_active = 1
        """
        params = []

        if class_name:
            query += " AND st.class_name = ?"
            params.append(class_name)

        if start_date:
            query += " AND (se.session_date >= ? OR se.session_date IS NULL)"
            params.append(start_date)

        if end_date:
            query += " AND (se.session_date <= ? OR se.session_date IS NULL)"
            params.append(end_date)

        query += " GROUP BY st.student_id, st.roll_no, st.full_name, st.class_name ORDER BY st.class_name, st.roll_no"

        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        report = []
        for r in rows:
            tot = r['total_sessions'] or 0
            att = r['attended_sessions'] or 0
            ab = r['absent_sessions'] or 0
            pct = round((att / tot * 100.0), 2) if tot > 0 else 0.0
            report.append({
                "student_id": r['student_id'],
                "roll_no": r['roll_no'],
                "full_name": r['full_name'],
                "class_name": r['class_name'],
                "total_sessions": tot,
                "attended_sessions": att,
                "absent_sessions": ab,
                "percentage": pct
            })

        return report
