import os
import cv2
import numpy as np
import datetime
from config import Config
from database import get_db_connection, init_db
from face_engine import face_engine

def generate_synthetic_face(student_id, name, variation=0):
    """
    Generates a recognizable synthetic 200x200 grayscale facial pattern
    with distinct features (face oval, eyes, eyebrows, nose, mouth)
    varying systematically by student_id and variation index.
    """
    img = np.full((200, 200), 220, dtype=np.uint8)
    
    # Face oval
    cv2.ellipse(img, (100, 105), (65, 80), 0, 0, 360, 140, -1)
    cv2.ellipse(img, (100, 105), (63, 78), 0, 0, 360, 200, -1)

    # Hair / top
    cv2.ellipse(img, (100, 50), (60, 30), 0, 0, 180, 50 + (student_id * 15) % 80, -1)

    # Eyes (distance varies slightly by student_id)
    eye_offset = 24 + (student_id % 4) * 2
    eye_y = 90 + (variation % 3)
    cv2.circle(img, (100 - eye_offset, eye_y), 9, 70, -1)
    cv2.circle(img, (100 + eye_offset, eye_y), 9, 70, -1)
    cv2.circle(img, (100 - eye_offset, eye_y), 4, 255, -1)
    cv2.circle(img, (100 + eye_offset, eye_y), 4, 255, -1)

    # Eyebrows
    cv2.line(img, (100 - eye_offset - 12, eye_y - 12), (100 - eye_offset + 10, eye_y - 10), 60, 2)
    cv2.line(img, (100 + eye_offset - 10, eye_y - 10), (100 + eye_offset + 12, eye_y - 12), 60, 2)

    # Nose
    cv2.line(img, (100, eye_y + 10), (100, eye_y + 35), 110, 2)
    cv2.line(img, (95, eye_y + 35), (105, eye_y + 35), 110, 2)

    # Mouth
    smile_curve = -10 + (student_id * 5) % 25
    cv2.ellipse(img, (100, 150), (28, 12 + smile_curve // 2), 0, 0, 180, 80, 2)

    # Student text watermark
    cv2.putText(img, f"ID:{student_id}", (15, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.4, 90, 1)

    # Add minor noise for variation realism
    noise = np.random.randint(-5, 6, (200, 200), dtype=np.int16)
    img_noisy = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    return img_noisy

def populate_demo_data():
    """Seeds official subjects, CAMSA students, and attendance records."""
    from add_students_and_subjects import add_data
    add_data()

if __name__ == "__main__":
    populate_demo_data()
