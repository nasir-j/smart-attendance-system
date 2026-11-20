import os
import cv2
import json
import numpy as np
from config import Config
from database import get_db_connection

# Load OpenCV Cascade Classifier
CASCADE_PATH = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)

class FaceEngine:
    def __init__(self):
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=1,
            neighbors=8,
            grid_x=8,
            grid_y=8,
            threshold=Config.LBPH_DISTANCE_THRESHOLD
        )
        self.is_trained = False
        self.load_model()

    def load_model(self):
        """Attempts to load pre-trained LBPH model from disk."""
        if os.path.exists(Config.MODEL_PATH) and os.path.exists(Config.LABEL_MAP_PATH):
            try:
                self.recognizer.read(Config.MODEL_PATH)
                self.is_trained = True
                return True
            except Exception as e:
                print(f"[FaceEngine] Error loading model: {e}")
                self.is_trained = False
                return False
        self.is_trained = False
        return False

    @staticmethod
    def preprocess_face(face_roi):
        """Normalizes face crop: grayscale, 200x200 resize, histogram equalization."""
        if len(face_roi.shape) == 3:
            gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        else:
            gray = face_roi
        # Equalize histogram for illumination invariant recognition
        eq = cv2.equalizeHist(gray)
        resized = cv2.resize(eq, (200, 200), interpolation=cv2.INTER_AREA)
        return resized

    def detect_faces(self, frame):
        """
        Detects faces in a BGR or Gray image.
        Returns: list of (x, y, w, h) bounding boxes.
        """
        if frame is None or frame.size == 0:
            return []
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        
        # Fast Haar face detection
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.15,
            minNeighbors=5,
            minSize=(60, 60),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        return faces

    def train_recognizer(self):
        """
        Loads all face samples of active students from the database and trains LBPH.
        Saves trainer.yml and labels.json.
        Returns: (success: bool, num_students: int, num_samples: int, message: str)
        """
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Fetch samples only for active students
        cur.execute("""
            SELECT fd.student_id, fd.encoding, s.full_name, s.roll_no
            FROM face_data fd
            JOIN students s ON fd.student_id = s.student_id
            WHERE s.is_active = 1
            ORDER BY fd.student_id
        """)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            self.is_trained = False
            return False, 0, 0, "No face samples found for active students."

        faces = []
        labels = []
        label_map = {}  # student_id -> { "name": ..., "roll_no": ... }

        for row in rows:
            student_id = row['student_id']
            encoding_blob = row['encoding']
            full_name = row['full_name']
            roll_no = row['roll_no']

            # Decode image from stored blob
            nparr = np.frombuffer(encoding_blob, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                norm_face = cv2.resize(img, (200, 200))
                faces.append(norm_face)
                labels.append(student_id)
                if str(student_id) not in label_map:
                    label_map[str(student_id)] = {
                        "name": full_name,
                        "roll_no": roll_no
                    }

        if len(faces) == 0:
            self.is_trained = False
            return False, 0, 0, "Failed to decode face samples."

        # Train LBPH
        new_recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=1,
            neighbors=8,
            grid_x=8,
            grid_y=8,
            threshold=Config.LBPH_DISTANCE_THRESHOLD
        )
        new_recognizer.train(faces, np.array(labels, dtype=np.int32))

        os.makedirs(os.path.dirname(Config.MODEL_PATH), exist_ok=True)
        new_recognizer.write(Config.MODEL_PATH)
        
        with open(Config.LABEL_MAP_PATH, 'w') as f:
            json.dump(label_map, f, indent=2)

        self.recognizer = new_recognizer
        self.is_trained = True

        return True, len(label_map), len(faces), f"Model trained with {len(faces)} samples across {len(label_map)} students."

    def recognize_face(self, face_roi):
        """
        Compares face_roi with trained models.
        Returns: (student_id, confidence_percentage, status_label)
        If not confident or unknown, student_id will be None.
        """
        if not self.is_trained:
            return None, 0.0, "Model Not Trained"

        processed = self.preprocess_face(face_roi)
        
        try:
            # LBPH predict returns (label/student_id, distance)
            # Distance: 0 = exact match; typical match < 60-70.
            student_id, distance = self.recognizer.predict(processed)
            
            # Convert LBPH distance to confidence %
            # distance 0 -> 100%, distance 80 -> ~33%, distance 120 -> 0%
            confidence = max(0.0, min(100.0, round((1.0 - (distance / 115.0)) * 100.0, 1)))

            if distance < Config.LBPH_DISTANCE_THRESHOLD and confidence >= Config.MIN_CONFIDENCE_PERCENT:
                return student_id, confidence, "Recognized"
            else:
                return None, confidence, "Unknown Face"
        except Exception as e:
            print(f"[FaceEngine] Prediction error: {e}")
            return None, 0.0, "Error"

    def process_frame_for_attendance(self, frame, allowed_student_ids=None):
        """
        Processes a single video frame:
        1. Detects faces.
        2. Recognizes each face.
        3. Draws bounding boxes and labels.
        4. Returns (annotated_frame, list_of_recognized_students)
        Where each recognized student is dict:
        {'student_id': int, 'confidence': float, 'name': str, 'roll_no': str}
        """
        if frame is None:
            return None, []

        annotated = frame.copy()
        faces = self.detect_faces(annotated)
        recognized_list = []

        label_map = {}
        if os.path.exists(Config.LABEL_MAP_PATH):
            try:
                with open(Config.LABEL_MAP_PATH, 'r') as f:
                    label_map = json.load(f)
            except Exception:
                label_map = {}

        for (x, y, w, h) in faces:
            face_roi = annotated[y:y+h, x:x+w]
            student_id, conf, status_label = self.recognize_face(face_roi)

            # Check if recognized student belongs to this session's class (if filtered)
            is_valid_student = False
            if student_id is not None:
                if allowed_student_ids is None or student_id in allowed_student_ids:
                    is_valid_student = True

            if is_valid_student:
                info = label_map.get(str(student_id), {})
                name = info.get("name", f"Student #{student_id}")
                roll_no = info.get("roll_no", "")
                label_text = f"{name} ({conf:.0f}%)"
                box_color = (0, 200, 0)  # Green for recognized
                recognized_list.append({
                    "student_id": student_id,
                    "confidence": conf,
                    "name": name,
                    "roll_no": roll_no
                })
            else:
                label_text = f"Unknown ({conf:.0f}%)" if conf > 0 else "Unknown"
                box_color = (0, 0, 255)  # Red for unknown

            # Draw sleek UI box on frame
            cv2.rectangle(annotated, (x, y), (x+w, y+h), box_color, 2)
            cv2.rectangle(annotated, (x, y-26), (x+w, y), box_color, -1)
            cv2.putText(
                annotated,
                label_text,
                (x + 5, y - 7),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )

        return annotated, recognized_list

# Global engine instance
face_engine = FaceEngine()
