import os
import sys
import cv2
import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import Config
from database import get_db_connection, init_db
from face_engine import face_engine
from seed_data import generate_synthetic_face

SUBJECTS = [
    ("CAMS3001", "Operating System and Shell Programming"),
    ("CAMS3002", "Software Engineering"),
    ("CAMS3003", "Theory of Computation"),
    ("CAMS3004", "Data Science using Python"),
    ("CAMS3E02", "Network programming"),
    ("CAMS3E08", "Artificial Intelligence & Soft Computing")
]

STUDENTS = [
    (1, "MOHAMMAD AZEEM", "25CAMSA101"),
    (2, "MOHAMMAD MAAZ ALI", "25CAMSA102"),
    (3, "SAHIL HUSEN", "25CAMSA103"),
    (4, "KAPIL PANDEY", "25CAMSA104"),
    (5, "ALTAF KHAN", "25CAMSA105"),
    (6, "PRIYANKA", "25CAMSA106"),
    (7, "NAZIR HUSSAIN", "25CAMSA108"),
    (8, "KAPIL KUMAR SHARMA", "25CAMSA109"),
    (9, "ZEENAT MOHAMMAD SHAHID", "25CAMSA110"),
    (10, "MUKARRAM HUSSAIN", "25CAMSA111"),
    (11, "FAIZAN AHMAD", "25CAMSA112"),
    (12, "AMBIKA SINGH", "25CAMSA113"),
    (13, "NASIR JAWED", "25CAMSA114"),
    (14, "SHAHBAZ KHAN", "25CAMSA115"),
    (15, "IQRA FATIMA UMANG", "25CAMSA116"),
    (16, "LIYANA A K", "25CAMSA117"),
    (17, "MOHAMMAD FIRDOUS ALAM", "25CAMSA118"),
    (18, "RASHMI UPADHYAY", "25CAMSA119"),
    (19, "FAIZA KHALEEQUE", "25CAMSA120"),
    (20, "ABDUL BARI", "25CAMSA121"),
    (21, "ASIF KHAN", "25CAMSA122"),
    (22, "PRINCE KAUSHAL", "25CAMSA123"),
    (23, "TRISHIT HAZRA", "25CAMSA124"),
    (24, "ADEEBA AKHTAR", "25CAMSA125"),
    (25, "MOHD SARFARAZ", "25CAMSA126"),
    (26, "SUMIT", "25CAMSA127"),
    (27, "TAIBA AZAM", "25CAMSA128"),
    (28, "MOHD WASI IMAM", "25CAMSA129"),
    (29, "MURSHAD ALI", "25CAMSA131"),
    (30, "HADIYA MUZAMMIL", "25CAMSA132"),
    (31, "RASHIKA ZEHRA", "25CAMSA133"),
    (32, "WASHIM AKHTAR", "25CAMSA134"),
    (33, "RIYA AGRAWAL", "25CAMSA135"),
    (34, "ILMA GULZAR", "25CAMSA137"),
    (35, "MOHAMMAD TARIQUE", "25CAMSA138"),
    (36, "SHIHAB AHMAD KHAN", "25CAMSA139"),
    (37, "UNZILA", "25CAMSA140"),
    (38, "JYOTI SAINI", "25CAMSA141"),
    (39, "MOHAMMED DANISH", "25CAMSA142"),
    (40, "TULSI SHARMA", "25CAMSA143"),
    (41, "SUMANIYA SHEIKH", "25CAMSA144"),
    (42, "KALEEM AHMED", "25CAMSA145"),
    (43, "SUSHIL KUMAR", "25CAMSA146"),
    (44, "MOHD AJMAL", "25CAMSA147"),
    (45, "MD AHMAD AKRAM CHOUDHURY", "25CAMSA148"),
    (46, "MD SHAHID ANSARI", "25CAMSA149"),
    (47, "SAUOOD ANSARI", "25CAMSA151"),
    (48, "BULBUL VARSHNEY", "25CAMSA152"),
    (49, "NOOR ISLAM", "25CAMSA153"),
    (50, "SAHIL AFRIDI", "25CAMSA154"),
    (51, "FAISAL KHAN", "25CAMSA155"),
    (52, "TABISH HASAN", "25CAMSA156"),
    (53, "MD IRSHAD NADAF", "25CAMSA158"),
    (54, "MD ARSH ISRAR QURESHI", "25CAMSA160"),
    (55, "MOHD MUDASIR HUSSAIN", "25CAMSA161"),
    (56, "QAUSAIN AHMAD", "25CAMSA163"),
    (57, "TAUQEER AHMAD", "25CAMSA164"),
    (58, "TARANA KHAN", "25CAMSA166"),
    (59, "MD ZAHEEN", "25CAMSA167"),
    (60, "FAHAD NAUSHAD KHAN", "25CAMSA168"),
    (61, "MOHD AFFAN MANZOOR", "25CAMSA169"),
    (62, "AFROZ ALAM", "25CAMSA170")
]

def add_data():
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()

    # Find admin user id
    cur.execute("SELECT user_id FROM users WHERE username = 'admin'")
    admin = cur.fetchone()
    admin_id = admin['user_id'] if admin else 1

    # 1. Add / update Subjects
    print("Adding subjects...")
    for code, title in SUBJECTS:
        cur.execute("""
            INSERT INTO subjects (paper_code, title, is_active)
            VALUES (?, ?, 1)
            ON CONFLICT(paper_code) DO UPDATE SET title = excluded.title
        """, (code, title))
    conn.commit()

    # 2. Add Students
    print("Adding 62 students under class 'CAMSA'...")
    created_student_ids = []
    for s_no, name, roll_no in STUDENTS:
        cur.execute("SELECT student_id FROM students WHERE roll_no = ?", (roll_no,))
        existing = cur.fetchone()
        if existing:
            sid = existing['student_id']
            cur.execute("""
                UPDATE students SET full_name = ?, class_name = 'CAMSA', is_active = 1
                WHERE student_id = ?
            """, (name, sid))
        else:
            cur.execute("""
                INSERT INTO students (roll_no, full_name, class_name, is_active, registered_by)
                VALUES (?, ?, 'CAMSA', 1, ?)
            """, (roll_no, name, admin_id))
            sid = cur.lastrowid
        created_student_ids.append((sid, name, roll_no))

    conn.commit()

    # 3. Generate initial face biometrics for each student (5 samples each)
    print("Generating biometric facial samples for students...")
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    for sid, name, roll_no in created_student_ids:
        cur.execute("SELECT COUNT(*) FROM face_data WHERE student_id = ?", (sid,))
        count = cur.fetchone()[0]
        if count < 5:
            for v in range(5):
                synthetic = generate_synthetic_face(sid, name, variation=v)
                ret, buf = cv2.imencode('.jpg', synthetic)
                blob = buf.tobytes()

                filename = f"student_{sid}_sample_{v}.jpg"
                filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
                cv2.imwrite(filepath, synthetic)

                cur.execute("""
                    INSERT INTO face_data (student_id, encoding, image_path)
                    VALUES (?, ?, ?)
                """, (sid, blob, f"/static/uploads/faces/{filename}"))
    conn.commit()

    # 4. Create sample sessions for CAMSA in the new subjects
    cur.execute("SELECT user_id FROM users WHERE username = 'teacher'")
    teacher = cur.fetchone()
    teacher_id = teacher['user_id'] if teacher else admin_id

    # Add a sample session for Operating System and Shell Programming
    cur.execute("SELECT session_id FROM attendance_sessions WHERE class_name = 'CAMSA' AND subject LIKE '%Operating System%'")
    if not cur.fetchone():
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        cur.execute("""
            INSERT INTO attendance_sessions (subject, class_name, session_date, start_time, end_time, status, created_by)
            VALUES (?, 'CAMSA', ?, '09:30:00', '10:30:00', 'CLOSED', ?)
        """, ("[CAMS3001] Operating System and Shell Programming", today_str, teacher_id))
        sess_id = cur.lastrowid

        # Mark attendance for students (85% present simulation)
        for idx, (sid, name, roll_no) in enumerate(created_student_ids):
            if idx % 7 != 0:
                cur.execute("""
                    INSERT OR IGNORE INTO attendance_records (session_id, student_id, status, marked_at, confidence)
                    VALUES (?, ?, 'PRESENT', ?, ?)
                """, (sess_id, sid, f"{today_str} 09:35:{idx%60:02d}", 91.5 + (idx % 8)))
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO attendance_records (session_id, student_id, status, marked_at, confidence)
                    VALUES (?, ?, 'ABSENT', NULL, NULL)
                """, (sess_id, sid))
        conn.commit()

    conn.close()

    # 5. Retrain Face Recognizer
    print("Retraining LBPH Face Recognition Model...")
    success, num_students, num_samples, msg = face_engine.train_recognizer()
    print(f"Training Result: {msg}")

if __name__ == '__main__':
    add_data()
