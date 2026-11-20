import cv2
import time
import numpy as np
import threading
from config import Config
from face_engine import face_engine
from attendance_service import AttendanceService
from database import get_db_connection

class VideoCamera:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(VideoCamera, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.camera_index = Config.CAMERA_INDEX
        self.cap = None
        self.is_hardware_available = False
        self.running = True
        self.current_frame = None
        self.current_session_id = None
        self.allowed_student_ids = None
        self.last_recognized = []
        self._init_camera()
        self._initialized = True

        # Background thread to continuously read frames
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _init_camera(self):
        try:
            # Try DirectShow on Windows or standard V4L2 on Linux/Pi
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if hasattr(cv2, 'CAP_DSHOW') else cv2.CAP_ANY)
            if self.cap and self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_WIDTH)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_HEIGHT)
                # Test read one frame
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    self.is_hardware_available = True
                    print(f"[Camera] Physical camera {self.camera_index} initialized successfully.")
                    return
            self.is_hardware_available = False
            print(f"[Camera] Physical camera not detected or busy. Running in simulated / WebRTC mode.")
        except Exception as e:
            self.is_hardware_available = False
            print(f"[Camera] Hardware init exception: {e}")

    def set_active_session(self, session_id):
        """Sets the active session ID for automatic attendance marking."""
        self.current_session_id = session_id
        if session_id:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT s.student_id FROM students s
                JOIN attendance_sessions ses ON s.class_name = ses.class_name
                WHERE ses.session_id = ? AND s.is_active = 1
            """, (session_id,))
            rows = cur.fetchall()
            conn.close()
            self.allowed_student_ids = set([r['student_id'] for r in rows])
        else:
            self.allowed_student_ids = None

    def _generate_synthetic_frame(self, t):
        """Generates a clean synthetic frame when no hardware camera is present."""
        w, h = Config.FRAME_WIDTH, Config.FRAME_HEIGHT
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Gradient background
        for y in range(h):
            val = int(25 + 20 * (y / h))
            frame[y, :] = (val, val, val + 15)

        # Grid lines
        for x in range(0, w, 40):
            cv2.line(frame, (x, 0), (x, h), (40, 45, 55), 1)
        for y in range(0, h, 40):
            cv2.line(frame, (0, y), (w, y), (40, 45, 55), 1)

        # Status text
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, "SMART ATTENDANCE CAMERA (SIMULATION / WEBRTC READY)", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 215, 255), 2)
        cv2.putText(frame, f"System Time: {timestamp}", (20, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
        
        if self.current_session_id:
            cv2.putText(frame, f"ACTIVE SESSION #{self.current_session_id} - SCANNING FOR FACES", (20, 95),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 120), 2)
        else:
            cv2.putText(frame, "STANDBY - NO ACTIVE SESSION", (20, 95),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 200), 1)

        # Animated scanning radar line
        scan_y = int((time.time() * 90) % (h - 140)) + 120
        cv2.line(frame, (40, scan_y), (w - 40, scan_y), (0, 230, 255), 2)

        # Center target box
        cx, cy = w // 2, h // 2 + 30
        cv2.rectangle(frame, (cx - 90, cy - 110), (cx + 90, cy + 110), (0, 180, 255), 1)
        cv2.putText(frame, "ALIGN FACE HERE", (cx - 70, cy + 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 180, 255), 1)

        return frame

    def _capture_loop(self):
        """Continuously reads from hardware camera or generates simulation frames."""
        while self.running:
            raw_frame = None
            if self.is_hardware_available and self.cap:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    raw_frame = frame
                else:
                    self.is_hardware_available = False
            
            if raw_frame is None:
                raw_frame = self._generate_synthetic_frame(time.time())

            # If in an active session, process face detection & recognition
            if self.current_session_id:
                annotated, recognized_students = face_engine.process_frame_for_attendance(
                    raw_frame, self.allowed_student_ids
                )
                self.current_frame = annotated
                self.last_recognized = recognized_students

                # Automatically mark present
                for st in recognized_students:
                    AttendanceService.mark_present(
                        self.current_session_id,
                        st['student_id'],
                        st['confidence']
                    )
            else:
                # In standby, run detection for preview boxes
                annotated, recognized_students = face_engine.process_frame_for_attendance(raw_frame)
                self.current_frame = annotated
                self.last_recognized = recognized_students

            time.sleep(0.04)  # ~25 FPS

    def get_frame_bytes(self):
        """Encodes current frame as JPEG bytes for MJPEG streaming."""
        if self.current_frame is None:
            return None
        ret, jpeg = cv2.imencode('.jpg', self.current_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if ret:
            return jpeg.tobytes()
        return None

    def process_external_image(self, image_np, session_id=None):
        """
        Processes an image sent from browser WebRTC/canvas or file upload.
        Recognizes faces, marks attendance if session_id is active, and returns details.
        """
        target_session = session_id or self.current_session_id
        allowed = None
        if target_session:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT s.student_id FROM students s
                JOIN attendance_sessions ses ON s.class_name = ses.class_name
                WHERE ses.session_id = ? AND s.is_active = 1
            """, (target_session,))
            allowed = set([r['student_id'] for r in cur.fetchall()])
            conn.close()

        annotated, recognized = face_engine.process_frame_for_attendance(image_np, allowed)

        marked_now = []
        if target_session:
            for st in recognized:
                was_marked = AttendanceService.mark_present(
                    target_session,
                    st['student_id'],
                    st['confidence']
                )
                if was_marked:
                    marked_now.append(st)

        # Encode annotated image to jpeg bytes
        ret, jpeg = cv2.imencode('.jpg', annotated)
        return {
            "recognized": recognized,
            "newly_marked": marked_now,
            "annotated_bytes": jpeg.tobytes() if ret else None
        }

# Global camera singleton
camera = VideoCamera()

def gen_camera_frames(session_id=None):
    """Generator function for streaming live video over HTTP (MJPEG)."""
    camera.set_active_session(session_id)
    while True:
        frame_bytes = camera.get_frame_bytes()
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.05)
