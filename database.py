import sqlite3
import os
from werkzeug.security import generate_password_hash
from config import Config

def get_db_connection():
    """Create and return a new database connection with row factory enabled."""
    db_path = Config.DATABASE_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Enforce SQLite foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(drop=False):
    """Initializes normalized 3NF database schema and seeds initial accounts."""
    conn = get_db_connection()
    cur = conn.cursor()

    if drop:
        cur.executescript("""
            DROP TABLE IF EXISTS attendance_records;
            DROP TABLE IF EXISTS attendance_sessions;
            DROP TABLE IF EXISTS face_data;
            DROP TABLE IF EXISTS students;
            DROP TABLE IF EXISTS users;
        """)

    # 1. users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('ADMIN', 'TEACHER')),
            is_active BOOLEAN NOT NULL DEFAULT 1
        );
    """)

    # 2. students table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            registered_by INTEGER NOT NULL,
            FOREIGN KEY (registered_by) REFERENCES users(user_id) ON DELETE RESTRICT
        );
    """)

    # 3. face_data table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS face_data (
            face_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            encoding BLOB NOT NULL,
            image_path TEXT,
            captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        );
    """)

    # 4. attendance_sessions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            class_name TEXT NOT NULL,
            session_date DATE NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME,
            status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'CLOSED')),
            created_by INTEGER NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE RESTRICT
        );
    """)

    # 5. attendance_records table (with UNIQUE constraint on session_id, student_id)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PRESENT', 'ABSENT')),
            marked_at TIMESTAMP,
            confidence REAL,
            FOREIGN KEY (session_id) REFERENCES attendance_sessions(session_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
            UNIQUE(session_id, student_id)
        );
    """)

    # 6. subjects table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_code TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1
        );
    """)

    # Create Indexes as specified in SRS 3NF analysis (Figure 3.3 & Section 2.3)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_face_student ON face_data(student_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_att_student ON attendance_records(student_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_att_session ON attendance_records(session_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_session_class_date ON attendance_sessions(class_name, session_date);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_subject_code ON subjects(paper_code);")

    # Seed initial 6 Subjects from Curriculum if not present
    curriculum_papers = [
        ("CAMS3001", "Operating System and Shell Programming"),
        ("CAMS3002", "Software Engineering"),
        ("CAMS3003", "Theory of Computation"),
        ("CAMS3004", "Data Science using Python"),
        ("CAMS3E02", "Network programming"),
        ("CAMS3E08", "Artificial Intelligence & Soft Computing")
    ]
    for code, title in curriculum_papers:
        cur.execute("""
            INSERT OR IGNORE INTO subjects (paper_code, title, is_active)
            VALUES (?, ?, 1)
        """, (code, title))

    # Seed initial Admin and Teacher if no users exist
    cur.execute("SELECT COUNT(*) FROM users;")
    count = cur.fetchone()[0]
    if count == 0:
        admin_pass = generate_password_hash("admin123")
        teacher_pass = generate_password_hash("teacher123")
        cur.execute("""
            INSERT INTO users (username, password_hash, full_name, role, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, ("admin", admin_pass, "System Administrator", "ADMIN"))
        cur.execute("""
            INSERT INTO users (username, password_hash, full_name, role, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, ("teacher", teacher_pass, "Class Teacher", "TEACHER"))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", Config.DATABASE_PATH)
