import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart-attendance-secret-key-2026-iot-pi')
    DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'smart_attendance.db')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'faces')
    MODEL_PATH = os.path.join(BASE_DIR, 'data', 'trainer.yml')
    LABEL_MAP_PATH = os.path.join(BASE_DIR, 'data', 'labels.json')
    
    # Face recognition tuning (LBPH distance threshold: lower = stricter match)
    # Default 70.0; distances < 70 are treated as matches
    LBPH_DISTANCE_THRESHOLD = 70.0
    MIN_CONFIDENCE_PERCENT = 45.0
    
    # Camera settings (reduced resolution suitable for Pi 3 / web)
    FRAME_WIDTH = 640
    FRAME_HEIGHT = 480
    CAMERA_INDEX = 0  # Default local webcam or Pi Camera
    
    # Samples required per student registration
    SAMPLES_PER_STUDENT = 10
