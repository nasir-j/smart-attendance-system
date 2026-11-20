import os
import sys
import sqlite3

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import Config
from database import get_db_connection
from face_engine import face_engine

def cleanup():
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Identify non-CAMSA students to remove
    cur.execute("SELECT student_id, roll_no, full_name, class_name FROM students WHERE class_name != 'CAMSA'")
    old_students = cur.fetchall()
    print(f"Found {len(old_students)} previous test student(s) to remove.")

    for s in old_students:
        sid = s['student_id']
        # Find image files on disk
        cur.execute("SELECT image_path FROM face_data WHERE student_id = ?", (sid,))
        paths = cur.fetchall()
        for p in paths:
            rel = p['image_path']
            if rel:
                fname = os.path.basename(rel)
                fpath = os.path.join(Config.UPLOAD_FOLDER, fname)
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception as e:
                        print(f"Error removing {fpath}: {e}")

        # Delete student record (cascades face_data and attendance_records)
        cur.execute("DELETE FROM students WHERE student_id = ?", (sid,))

    # 2. Delete test sessions that are not for CAMSA or not matching the 6 official papers
    cur.execute("""
        DELETE FROM attendance_sessions 
        WHERE class_name != 'CAMSA' 
           OR (
               subject NOT LIKE '%CAMS3001%' AND 
               subject NOT LIKE '%CAMS3002%' AND 
               subject NOT LIKE '%CAMS3003%' AND 
               subject NOT LIKE '%CAMS3004%' AND 
               subject NOT LIKE '%CAMS3E02%' AND 
               subject NOT LIKE '%CAMS3E08%' AND
               subject NOT IN (
                   'Operating System and Shell Programming',
                   'Software Engineering',
                   'Theory of Computation',
                   'Data Science using Python',
                   'Network programming',
                   'Artificial Intelligence & Soft Computing'
               )
           )
    """)
    removed_sessions = cur.rowcount
    print(f"Removed {removed_sessions} previous test session(s).")

    # 3. Clean subjects table to ensure only the 6 official subjects are present
    official_codes = ('CAMS3001', 'CAMS3002', 'CAMS3003', 'CAMS3004', 'CAMS3E02', 'CAMS3E08')
    cur.execute(f"DELETE FROM subjects WHERE paper_code NOT IN ({','.join(['?']*len(official_codes))})", official_codes)

    conn.commit()
    conn.close()

    # 4. Retrain model with only the 62 CAMSA students
    print("Retraining LBPH Model on active CAMSA students only...")
    success, num_students, num_samples, msg = face_engine.train_recognizer()
    print(f"Result: {msg}")

if __name__ == '__main__':
    cleanup()
