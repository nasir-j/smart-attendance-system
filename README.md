# IoT-Based Smart Attendance System Using Face Recognition

A production-grade, modular automated attendance management system built in strict compliance with the **Software Requirements Specification (SRS)**. The system is architected for Edge IoT deployments (e.g., Raspberry Pi 3 or PC edge device) using **OpenCV** and the **LBPH (Local Binary Patterns Histograms)** face recognition pipeline, coupled with a responsive **Python Flask** web application and a **Normalized 3NF SQLite database**.

---

## 🏛️ System Architecture

The application implements a 3-tier edge architecture:

```
[ Physical Input: Student Faces ]
               │
               ▼
   [ Camera (Pi Camera / USB) ]
               │ (Video Frames)
               ▼
┌─────────────────────────────────────────────────────────┐
│        RASPBERRY PI 3 / PC EDGE APPLICATION SERVER       │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ LOGIC TIER: Capture & Recognition Module (OpenCV) │  │
│  │  - Frame Capture (640x480 resolution)             │  │
│  │  - Face Detection (Haar Cascade Classifier)       │  │
│  │  - Face Preprocessing & Equalization (200x200)    │  │
│  │  - Face Recognition (OpenCV LBPH Recognizer)      │  │
│  │  - Attendance Service (Mark, Deduplicate, Time)   │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ LOGIC TIER: Web Application (Python / Flask)      │  │
│  │  - Authentication & Role-Based Access Control     │  │
│  │  - Student & Biometric Face Registration          │  │
│  │  - Live Attendance Session Controller             │  │
│  │  - Search, Filter & Report Generation Engine      │  │
│  └───────────────────────────────────────────────────┘  │
│                          │                              │
│                          ▼                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │ DATA TIER: SQLite 3NF Database                    │  │
│  │  - users, students, face_data                     │  │
│  │  - attendance_sessions, attendance_records        │  │
│  │  - Unique (session_id, student_id) constraint     │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
               ▲
               │ HTTP(S) / WebRTC
               ▼
┌─────────────────────────────────────────────────────────┐
│     PRESENTATION TIER: Responsive Web Interface         │
│  - Administrators & Teachers (Desktop, Laptop, Tablet)  │
│  - HTML5, CSS3, JavaScript, Bootstrap 5                 │
└─────────────────────────────────────────────────────────┘
```

---

## 📋 Requirements Traceability Matrix (FR-001 to FR-010)

| Requirement ID | Specification | Implementation in Project |
|---|---|---|
| **FR-001** | User Authentication & Role-Based Access | Salted hashes via `generate_password_hash` / `check_password_hash`. Roles: `ADMIN` and `TEACHER` with access control decorators (`@admin_required`, `@teacher_required`). |
| **FR-002** | Student Registration & Management | Roll number, full name, class registration with server-side validation. Duplicate roll numbers are rejected with an explicit error message. Full edit, activation/deactivation, and deletion. |
| **FR-003** | Face Capture via Camera | Multi-sample capture (5–10 samples) via connected hardware camera (OpenCV) or browser WebRTC webcam, plus manual photo file upload. |
| **FR-004** | Face Detection | Real-time face detection using OpenCV Haar Cascade (`haarcascade_frontalface_default.xml`), isolating bounding boxes and cropping face ROIs. |
| **FR-005** | Face Recognition | Compares detected face with stored encodings using `cv2.face.LBPHFaceRecognizer`. Unknown faces or low-confidence matches (<45%) are ignored without recording attendance. |
| **FR-006** | Automatic Attendance Marking | Recognizes active students during an OPEN session and automatically marks them `PRESENT`. Deduplication ensures at most one record per session. Closing the session automatically marks unrecognized active class students as `ABSENT`. |
| **FR-007** | Date & Time Recording | Records exact `marked_at` timestamp, `student_id`, `session_id`, and recognition `confidence`. ABSENT records maintain `marked_at = NULL`. |
| **FR-008** | Centralized Data Storage | 3NF normalized relational schema with foreign keys, transactional writes, and database uniqueness constraint on `(session_id, student_id)`. |
| **FR-009** | Search and View Attendance | Multi-parameter filtering: student roll no, student name, class, subject, date range, and status. Direct export to CSV. |
| **FR-010** | Attendance Reports & Percentages | Computes attendance percentage as `(Sessions Attended / Total Sessions Held) * 100`. Highlights eligibility (threshold &ge; 75%) and exports to CSV/printable report. |

---

## 🗄️ Normalized 3NF Database Schema

The database strictly fulfills Third Normal Form (3NF) requirements:

- **`users`**: `(user_id PK, username UK, password_hash, full_name, role, is_active)`
- **`students`**: `(student_id PK, roll_no UK, full_name, class_name, is_active, registered_at, registered_by FK)`
- **`face_data`**: `(face_id PK, student_id FK, encoding BLOB, image_path, captured_at)`
- **`attendance_sessions`**: `(session_id PK, subject, class_name, session_date, start_time, end_time, status, created_by FK)`
- **`attendance_records`**: `(record_id PK, session_id FK, student_id FK, status, marked_at, confidence, UNIQUE(session_id, student_id))`

### Performance Indexes:
- `idx_face_student ON face_data(student_id)`
- `idx_att_student ON attendance_records(student_id)`
- `idx_att_session ON attendance_records(session_id)`
- `idx_session_class_date ON attendance_sessions(class_name, session_date)`

---

## 🚀 Quick Start Guide

### 1. Requirements
- Python 3.9+
- Pip package manager

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize & Seed Demo Data
```bash
# Initialize DB tables and seed demo students, classes, and face samples:
python seed_data.py
```

### 4. Run the Web Server
```bash
python app.py
```
Open your browser at: **`http://localhost:5000`** (or `http://<device-ip>:5000` across your local network).

---

## 🔑 Default Accounts

| Role | Username | Password | Permitted Actions |
|---|---|---|---|
| **Administrator** | `admin` | `admin123` | Register/edit students, capture biometrics, retrain face model, manage user accounts, view reports. |
| **Teacher** | `teacher` | `teacher123` | Start/end attendance sessions, view live recognition feeds, search records, generate reports. |

---

## 🍓 Raspberry Pi 3 Deployment Instructions

1. **Hardware Setup**:
   - Connect the Raspberry Pi Camera Module to the CSI ribbon slot (or plug in a standard USB webcam).
   - Ensure camera interface is enabled: `sudo raspi-config` &rarr; Interface Options &rarr; Camera &rarr; Enable.

2. **System Dependencies on Raspberry Pi OS**:
   ```bash
   sudo apt update
   sudo apt install -y python3-pip python3-opencv libatlas-base-dev libhdf5-dev
   ```

3. **Install Python Packages**:
   ```bash
   pip3 install -r requirements.txt
   ```

4. **Run as a Systemd Service (Optional)**:
   Create `/etc/systemd/system/smart_attendance.service`:
   ```ini
   [Unit]
   Description=IoT Smart Attendance System
   After=network.target

   [Service]
   User=pi
   WorkingDirectory=/home/pi/smart_attendance_system
   ExecStart=/usr/bin/python3 app.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable smart_attendance
   sudo systemctl start smart_attendance
   ```

---

## 🧪 Automated Test Suite

To run the verification test suite covering all functional requirements:
```bash
python -m unittest tests/test_system.py -v
```

All 6 test suites verify:
- Authentication, salted hashing, and role isolation
- Duplicate roll number rejection
- Face detection, image preprocessing, and histogram equalization
- Attendance marking, deduplication, timestamping, and automatic absentee recording
- Search and query filters
- Attendance percentage formula calculations
