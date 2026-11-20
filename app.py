import os
import io
import csv
import base64
import datetime
import numpy as np
import cv2
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, Response, jsonify, send_file
)
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from database import get_db_connection, init_db
from face_engine import face_engine
from camera import camera, gen_camera_frames
from attendance_service import AttendanceService, ReportService

app = Flask(__name__)
app.config.from_object(Config)

# Ensure required directories exist
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)

# Initialize database on app startup
init_db()

# ---------------------------------------------------------
# Authentication Decorators (FR-001)
# ---------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        if session.get('role') != 'ADMIN':
            flash("Access denied: Administrator privileges required.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        if session.get('role') not in ('ADMIN', 'TEACHER'):
            flash("Access denied: Teacher privileges required.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user():
    return {
        'current_user': {
            'user_id': session.get('user_id'),
            'username': session.get('username'),
            'full_name': session.get('full_name'),
            'role': session.get('role')
        } if 'user_id' in session else None,
        'now': datetime.datetime.now()
    }

# ---------------------------------------------------------
# Authentication Routes (FR-001)
# ---------------------------------------------------------
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash("Please provide both username and password.", "danger")
            return render_template('login.html')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                flash("Your account has been deactivated. Contact an administrator.", "warning")
                return render_template('login.html')

            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            flash(f"Welcome back, {user['full_name']}!", "success")

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password.", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been securely logged out.", "info")
    return redirect(url_for('login'))

# ---------------------------------------------------------
# Dashboard Route
# ---------------------------------------------------------
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor()

    # Overview statistics
    cur.execute("SELECT COUNT(*) FROM students WHERE is_active = 1")
    total_students = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT class_name) FROM students WHERE is_active = 1")
    total_classes = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM attendance_sessions")
    total_sessions = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM attendance_sessions WHERE status = 'OPEN'")
    open_sessions = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM attendance_records WHERE status = 'PRESENT'")
    total_present_records = cur.fetchone()[0]

    # Recent 5 sessions
    cur.execute("""
        SELECT s.*, u.full_name as teacher_name,
               (SELECT COUNT(*) FROM attendance_records r WHERE r.session_id = s.session_id AND r.status = 'PRESENT') as present_count
        FROM attendance_sessions s
        JOIN users u ON s.created_by = u.user_id
        ORDER BY s.session_date DESC, s.start_time DESC
        LIMIT 5
    """)
    recent_sessions = [dict(r) for r in cur.fetchall()]

    conn.close()

    model_trained = face_engine.is_trained
    return render_template(
        'dashboard.html',
        total_students=total_students,
        total_classes=total_classes,
        total_sessions=total_sessions,
        open_sessions=open_sessions,
        total_present_records=total_present_records,
        recent_sessions=recent_sessions,
        model_trained=model_trained
    )

# ---------------------------------------------------------
# User Management (Admin Only)
# ---------------------------------------------------------
@app.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def admin_users():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'TEACHER')

        if not username or not full_name or not password:
            flash("All fields are required to create a user.", "danger")
        elif role not in ('ADMIN', 'TEACHER'):
            flash("Invalid role selected.", "danger")
        else:
            try:
                pass_hash = generate_password_hash(password)
                cur.execute("""
                    INSERT INTO users (username, password_hash, full_name, role, is_active)
                    VALUES (?, ?, ?, ?, 1)
                """, (username, pass_hash, full_name, role))
                conn.commit()
                flash(f"User account '{username}' created successfully.", "success")
            except Exception as e:
                flash(f"Error creating user: Username '{username}' already exists.", "danger")

    cur.execute("SELECT user_id, username, full_name, role, is_active FROM users ORDER BY role, username")
    users = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    if user_id == session.get('user_id'):
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for('admin_users'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_active = NOT is_active WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash("User account status updated.", "info")
    return redirect(url_for('admin_users'))

# ---------------------------------------------------------
# Subject / Curriculum Management
# ---------------------------------------------------------
@app.route('/admin/subjects', methods=['GET', 'POST'])
@login_required
def admin_subjects():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST' and session.get('role') == 'ADMIN':
        paper_code = request.form.get('paper_code', '').strip().upper()
        title = request.form.get('title', '').strip()

        if not paper_code or not title:
            flash("Paper code and title are both required.", "danger")
        else:
            try:
                cur.execute("""
                    INSERT INTO subjects (paper_code, title, is_active)
                    VALUES (?, ?, 1)
                """, (paper_code, title))
                conn.commit()
                flash(f"Subject '{paper_code} - {title}' added successfully.", "success")
            except Exception as e:
                flash(f"Error adding subject: Paper code '{paper_code}' already exists.", "danger")

    cur.execute("""
        SELECT s.*, 
               (SELECT COUNT(*) FROM attendance_sessions ses WHERE ses.subject LIKE '%' || s.paper_code || '%' OR ses.subject = s.title) as session_count
        FROM subjects s
        ORDER BY s.paper_code
    """)
    subjects = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template('admin/subjects.html', subjects=subjects)

@app.route('/admin/subjects/<int:subject_id>/toggle', methods=['POST'])
@admin_required
def toggle_subject_status(subject_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE subjects SET is_active = NOT is_active WHERE subject_id = ?", (subject_id,))
    conn.commit()
    conn.close()
    flash("Subject status updated.", "info")
    return redirect(url_for('admin_subjects'))

# ---------------------------------------------------------
# Student Registration & Management (FR-002)
# ---------------------------------------------------------
@app.route('/admin/students')
@login_required
def students_list():
    class_filter = request.args.get('class_name', '').strip()
    search = request.args.get('q', '').strip()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT class_name FROM students ORDER BY class_name")
    classes = [r['class_name'] for r in cur.fetchall()]

    query = """
        SELECT s.*, u.full_name as registered_by_name,
               (SELECT COUNT(*) FROM face_data fd WHERE fd.student_id = s.student_id) as sample_count
        FROM students s
        LEFT JOIN users u ON s.registered_by = u.user_id
        WHERE 1=1
    """
    params = []
    if class_filter:
        query += " AND s.class_name = ?"
        params.append(class_filter)
    if search:
        query += " AND (s.roll_no LIKE ? OR s.full_name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY s.class_name, s.roll_no"
    cur.execute(query, params)
    students = [dict(r) for r in cur.fetchall()]
    conn.close()

    return render_template('admin/students.html', students=students, classes=classes, selected_class=class_filter, search=search)

@app.route('/admin/students/register', methods=['GET', 'POST'])
@admin_required
def register_student():
    if request.method == 'POST':
        roll_no = request.form.get('roll_no', '').strip().upper()
        full_name = request.form.get('full_name', '').strip()
        class_name = request.form.get('class_name', '').strip().upper()

        if not roll_no or not full_name or not class_name:
            flash("Roll Number, Full Name, and Class/Section are required.", "danger")
            return render_template('admin/student_register.html')

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO students (roll_no, full_name, class_name, is_active, registered_by)
                VALUES (?, ?, ?, 1, ?)
            """, (roll_no, full_name, class_name, session['user_id']))
            student_id = cur.lastrowid
            conn.commit()
            conn.close()
            flash(f"Student '{full_name}' ({roll_no}) registered successfully! Please capture face samples.", "success")
            return redirect(url_for('capture_face_samples', student_id=student_id))
        except Exception as e:
            conn.close()
            # FR-002: Duplicate roll number shall be rejected
            flash(f"Registration failed: Roll Number '{roll_no}' already exists in the system.", "danger")
            return render_template('admin/student_register.html', roll_no=roll_no, full_name=full_name, class_name=class_name)

    return render_template('admin/student_register.html')

@app.route('/admin/students/<int:student_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_student(student_id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        roll_no = request.form.get('roll_no', '').strip().upper()
        full_name = request.form.get('full_name', '').strip()
        class_name = request.form.get('class_name', '').strip().upper()

        try:
            cur.execute("""
                UPDATE students
                SET roll_no = ?, full_name = ?, class_name = ?
                WHERE student_id = ?
            """, (roll_no, full_name, class_name, student_id))
            conn.commit()
            flash("Student details updated successfully.", "success")
            conn.close()
            return redirect(url_for('students_list'))
        except Exception as e:
            flash(f"Update failed: Roll number '{roll_no}' may already be in use.", "danger")

    cur.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
    student = cur.fetchone()
    conn.close()

    if not student:
        flash("Student record not found.", "warning")
        return redirect(url_for('students_list'))

    return render_template('admin/student_edit.html', student=student)

@app.route('/admin/students/<int:student_id>/toggle', methods=['POST'])
@admin_required
def toggle_student_status(student_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE students SET is_active = NOT is_active WHERE student_id = ?", (student_id,))
    conn.commit()
    conn.close()
    flash("Student status updated. (Remember to retrain model if active list changed)", "info")
    return redirect(url_for('students_list'))

@app.route('/admin/students/<int:student_id>/delete', methods=['POST'])
@admin_required
def delete_student(student_id):
    # Non-functional requirement Privacy: Remove biometric facial data when student record deleted
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Remove stored image files on disk
    cur.execute("SELECT image_path FROM face_data WHERE student_id = ?", (student_id,))
    paths = cur.fetchall()
    for row in paths:
        if row['image_path'] and os.path.exists(row['image_path']):
            try:
                os.remove(row['image_path'])
            except Exception:
                pass

    cur.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
    conn.commit()
    conn.close()
    flash("Student record and all associated biometric facial data were securely removed.", "success")
    return redirect(url_for('students_list'))

# ---------------------------------------------------------
# Face Capture & Model Training (FR-003, FR-004, FR-005)
# ---------------------------------------------------------
@app.route('/admin/students/<int:student_id>/capture')
@admin_required
def capture_face_samples(student_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
    student = cur.fetchone()

    cur.execute("SELECT face_id, image_path, captured_at FROM face_data WHERE student_id = ? ORDER BY captured_at DESC", (student_id,))
    samples = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for('students_list'))

    return render_template('admin/capture.html', student=student, samples=samples)

@app.route('/api/students/<int:student_id>/save_sample', methods=['POST'])
@admin_required
def api_save_face_sample(student_id):
    """
    Receives either a base64 canvas image from browser webcam OR uploaded file.
    Detects face, normalizes ROI, saves BLOB to face_data, and saves disk preview.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
    student = cur.fetchone()
    if not student:
        conn.close()
        return jsonify({"success": False, "error": "Student not found"}), 404

    image_bytes = None
    if 'image' in request.files:
        file = request.files['image']
        image_bytes = file.read()
    elif request.is_json and 'image_data' in request.json:
        # Base64 dataURL from WebRTC canvas
        data_url = request.json['image_data']
        header, encoded = data_url.split(',', 1)
        image_bytes = base64.b64decode(encoded)

    if not image_bytes:
        conn.close()
        return jsonify({"success": False, "error": "No image data received"}), 400

    # Decode image with OpenCV
    nparr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        conn.close()
        return jsonify({"success": False, "error": "Failed to decode image frame"}), 400

    # FR-004: Face Detection
    faces = face_engine.detect_faces(frame)
    if len(faces) == 0:
        conn.close()
        return jsonify({"success": False, "error": "No face detected. Please ensure your face is clearly visible with good lighting."}), 422

    # Take primary face (largest area)
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    x, y, w, h = faces[0]
    face_roi = frame[y:y+h, x:x+w]

    # Preprocess & normalize to 200x200 grayscale
    normalized = face_engine.preprocess_face(face_roi)

    # Encode normalized face to JPG bytes for DB BLOB storage
    ret, buf = cv2.imencode('.jpg', normalized)
    if not ret:
        conn.close()
        return jsonify({"success": False, "error": "Face encoding compression failed"}), 500

    encoding_blob = buf.tobytes()

    # Save to disk as preview
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"student_{student_id}_{timestamp}.jpg"
    filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
    cv2.imwrite(filepath, normalized)

    # Relative path for web serving
    rel_path = f"/static/uploads/faces/{filename}"

    cur.execute("""
        INSERT INTO face_data (student_id, encoding, image_path)
        VALUES (?, ?, ?)
    """, (student_id, encoding_blob, rel_path))
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM face_data WHERE student_id = ?", (student_id,))
    total_samples = cur.fetchone()[0]
    conn.close()

    return jsonify({
        "success": True,
        "message": f"Sample captured successfully! (Total: {total_samples})",
        "sample_url": rel_path,
        "total_samples": total_samples
    })

@app.route('/admin/train', methods=['GET', 'POST'])
@admin_required
def train_model():
    if request.method == 'POST':
        success, num_students, num_samples, msg = face_engine.train_recognizer()
        if success:
            flash(f"Recognition Model Trained Successfully: {msg}", "success")
        else:
            flash(f"Model Training Warning: {msg}", "warning")
        return redirect(url_for('train_model'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.student_id, s.roll_no, s.full_name, s.class_name, s.is_active,
               COUNT(fd.face_id) as sample_count
        FROM students s
        LEFT JOIN face_data fd ON s.student_id = fd.student_id
        GROUP BY s.student_id
        ORDER BY s.class_name, s.roll_no
    """)
    students_data = [dict(r) for r in cur.fetchall()]
    conn.close()

    return render_template(
        'admin/train_model.html',
        students=students_data,
        is_trained=face_engine.is_trained,
        model_path=Config.MODEL_PATH
    )

# ---------------------------------------------------------
# Attendance Sessions & Automatic Recognition (FR-006, FR-007)
# ---------------------------------------------------------
@app.route('/sessions')
@login_required
def sessions_list():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT s.*, u.full_name as teacher_name,
               (SELECT COUNT(*) FROM attendance_records r WHERE r.session_id = s.session_id AND r.status = 'PRESENT') as present_count,
               (SELECT COUNT(*) FROM attendance_records r WHERE r.session_id = s.session_id AND r.status = 'ABSENT') as absent_count
        FROM attendance_sessions s
        JOIN users u ON s.created_by = u.user_id
        ORDER BY s.session_date DESC, s.start_time DESC
    """)
    sessions = [dict(r) for r in cur.fetchall()]
    conn.close()

    return render_template('sessions/index.html', sessions=sessions)

@app.route('/sessions/start', methods=['GET', 'POST'])
@teacher_required
def start_session():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        class_name = request.form.get('class_name', '').strip().upper()

        if not subject or not class_name:
            flash("Subject and Class Name are required.", "danger")
        else:
            # Check if class has active registered students
            cur.execute("SELECT COUNT(*) FROM students WHERE class_name = ? AND is_active = 1", (class_name,))
            student_count = cur.fetchone()[0]
            if student_count == 0:
                flash(f"Cannot start session: No active students registered in class '{class_name}'.", "warning")
            else:
                now = datetime.datetime.now()
                session_date = now.strftime("%Y-%m-%d")
                start_time = now.strftime("%H:%M:%S")

                cur.execute("""
                    INSERT INTO attendance_sessions (subject, class_name, session_date, start_time, status, created_by)
                    VALUES (?, ?, ?, ?, 'OPEN', ?)
                """, (subject, class_name, session_date, start_time, session['user_id']))
                session_id = cur.lastrowid
                conn.commit()
                conn.close()

                flash(f"Attendance session #{session_id} for {class_name} ({subject}) started!", "success")
                return redirect(url_for('live_session', session_id=session_id))

    cur.execute("SELECT DISTINCT class_name FROM students WHERE is_active = 1 ORDER BY class_name")
    classes = [r['class_name'] for r in cur.fetchall()]
    cur.execute("SELECT paper_code, title FROM subjects WHERE is_active = 1 ORDER BY paper_code")
    subjects = [dict(r) for r in cur.fetchall()]
    conn.close()

    return render_template('sessions/start.html', classes=classes, subjects=subjects)

@app.route('/sessions/<int:session_id>/live')
@login_required
def live_session(session_id):
    summary = AttendanceService.get_session_summary(session_id)
    if not summary:
        flash("Session not found.", "danger")
        return redirect(url_for('sessions_list'))

    # If open, notify camera module
    if summary['session']['status'] == 'OPEN':
        camera.set_active_session(session_id)

    # Fetch total enrolled active students in this class
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT student_id, roll_no, full_name
        FROM students
        WHERE class_name = ? AND is_active = 1
        ORDER BY roll_no
    """, (summary['session']['class_name'],))
    enrolled_students = [dict(r) for r in cur.fetchall()]
    conn.close()

    return render_template(
        'sessions/live.html',
        session=summary['session'],
        summary=summary,
        enrolled_students=enrolled_students,
        is_trained=face_engine.is_trained
    )

@app.route('/sessions/<int:session_id>/end', methods=['POST'])
@teacher_required
def end_session(session_id):
    # Stops camera loop for this session & marks absentees automatically
    absent_count = AttendanceService.mark_absentees(session_id)
    if camera.current_session_id == session_id:
        camera.set_active_session(None)

    flash(f"Session closed successfully. {absent_count} absentee student(s) automatically marked.", "success")
    return redirect(url_for('session_summary', session_id=session_id))

@app.route('/sessions/<int:session_id>/summary')
@login_required
def session_summary(session_id):
    summary = AttendanceService.get_session_summary(session_id)
    if not summary:
        flash("Session not found.", "danger")
        return redirect(url_for('sessions_list'))

    return render_template('sessions/summary.html', summary=summary, session=summary['session'])

# ---------------------------------------------------------
# Real-Time AJAX & Video Streaming Endpoints
# ---------------------------------------------------------
@app.route('/video_feed/<int:session_id>')
@login_required
def video_feed(session_id):
    """MJPEG stream for live browser preview and face detection bounding boxes."""
    return Response(
        gen_camera_frames(session_id),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/api/sessions/<int:session_id>/live_status')
@login_required
def api_session_live_status(session_id):
    """Returns real-time session stats and newly recognized students for dynamic polling."""
    summary = AttendanceService.get_session_summary(session_id)
    if not summary:
        return jsonify({"error": "Session not found"}), 404

    return jsonify({
        "status": summary['session']['status'],
        "total_enrolled": summary['total_students'],
        "present_count": summary['present_count'],
        "absent_count": summary['absent_count'],
        "percentage": summary['percentage'],
        "records": summary['records']
    })

@app.route('/api/sessions/<int:session_id>/scan_frame', methods=['POST'])
@login_required
def api_scan_frame(session_id):
    """
    Endpoint for WebRTC Browser Camera frames.
    Allows testing/marking via browser webcam from client device!
    """
    data = request.get_json()
    if not data or 'image_data' not in data:
        return jsonify({"success": False, "error": "No image data"}), 400

    try:
        header, encoded = data['image_data'].split(',', 1)
        image_bytes = base64.b64decode(encoded)
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        result = camera.process_external_image(frame, session_id=session_id)
        return jsonify({
            "success": True,
            "recognized": result['recognized'],
            "newly_marked": result['newly_marked']
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ---------------------------------------------------------
# Search & View Attendance Records (FR-009)
# ---------------------------------------------------------
@app.route('/attendance/search')
@login_required
def attendance_search():
    roll_no = request.args.get('roll_no', '').strip()
    student_name = request.args.get('student_name', '').strip()
    class_name = request.args.get('class_name', '').strip()
    subject = request.args.get('subject', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    status = request.args.get('status', '').strip()

    filters = {
        'roll_no': roll_no,
        'student_name': student_name,
        'class_name': class_name,
        'subject': subject,
        'start_date': start_date,
        'end_date': end_date,
        'status': status
    }

    records = ReportService.search(filters)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT class_name FROM students ORDER BY class_name")
    classes = [r['class_name'] for r in cur.fetchall()]
    cur.execute("""
        SELECT DISTINCT subject FROM (
            SELECT subject FROM attendance_sessions
            UNION
            SELECT '[' || paper_code || '] ' || title as subject FROM subjects WHERE is_active = 1
        ) WHERE subject IS NOT NULL AND subject != '' ORDER BY subject
    """)
    subjects = [r['subject'] for r in cur.fetchall()]
    conn.close()

    # CSV Export support
    if request.args.get('export') == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Record ID', 'Roll No', 'Student Name', 'Class', 'Subject', 'Date', 'Time Marked', 'Status', 'Confidence %', 'Teacher'])
        for r in records:
            writer.writerow([
                r['record_id'],
                r['roll_no'],
                r['student_name'],
                r['class_name'],
                r['subject'],
                r['session_date'],
                r['marked_at'] or 'N/A',
                r['status'],
                f"{r['confidence']}%" if r['confidence'] else 'N/A',
                r['teacher_name']
            ])
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=attendance_records.csv"}
        )

    return render_template(
        'attendance/search.html',
        records=records,
        classes=classes,
        subjects=subjects,
        filters=filters
    )

# ---------------------------------------------------------
# Attendance Reports & Percentages (FR-010)
# ---------------------------------------------------------
@app.route('/attendance/reports')
@login_required
def attendance_reports():
    class_name = request.args.get('class_name', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    report = ReportService.generate_report(
        class_name=class_name or None,
        start_date=start_date or None,
        end_date=end_date or None
    )

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT class_name FROM students ORDER BY class_name")
    classes = [r['class_name'] for r in cur.fetchall()]
    conn.close()

    # CSV Export support
    if request.args.get('export') == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Roll No', 'Student Name', 'Class', 'Total Sessions Held', 'Sessions Attended', 'Sessions Absent', 'Attendance %'])
        for row in report:
            writer.writerow([
                row['roll_no'],
                row['full_name'],
                row['class_name'],
                row['total_sessions'],
                row['attended_sessions'],
                row['absent_sessions'],
                f"{row['percentage']}%"
            ])
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=attendance_percentage_report.csv"}
        )

    return render_template(
        'attendance/reports.html',
        report=report,
        classes=classes,
        selected_class=class_name,
        start_date=start_date,
        end_date=end_date
    )

# ---------------------------------------------------------
# Camera Diagnostics & Tips (Section 4.2)
# ---------------------------------------------------------
@app.route('/camera_test')
@login_required
def camera_test():
    return render_template(
        'camera_test.html',
        camera_available=camera.is_hardware_available,
        model_trained=face_engine.is_trained
    )

# ---------------------------------------------------------
# Quick Demo Seeder Route (for seamless presentation & evaluation)
# ---------------------------------------------------------
@app.route('/seed_demo', methods=['POST'])
@admin_required
def seed_demo():
    from seed_data import populate_demo_data
    populate_demo_data()
    face_engine.load_model()
    flash("Demo data (classes, students, historical sessions, and records) seeded successfully!", "success")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    # Run development server (accessible over local network as specified in SRS Section 2.4)
    app.run(host='0.0.0.0', port=5000, debug=True)
