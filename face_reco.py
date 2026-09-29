import os
import pickle
import face_recognition

ENCODINGS_FILE = "faculty_encodings.pkl"


def register_faculty_face(faculty_name, image_path):
    image = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(image)

    if not encodings:
        return False, "Walang mukhang nadetect sa larawan. Mag-upload ng mas malinaw na pic."

    known_data = load_known_faces()
    known_data[faculty_name] = encodings[0]

    with open(ENCODINGS_FILE, "wb") as f:
        pickle.dump(known_data, f)

    return True, f"Successfully registered face for {faculty_name}!"


def load_known_faces():
    if not os.path.exists(ENCODINGS_FILE):
        return {}
    with open(ENCODINGS_FILE, "rb") as f:
        return pickle.load(f)


def verify_face(frame_rgb, known_faces, tolerance=0.5):
    if not known_faces:
        return "Unknown / Unregistered", False

    face_locations = face_recognition.face_locations(frame_rgb)
    if not face_locations:
        return "No Face Detected", False

    face_encodings = face_recognition.face_encodings(frame_rgb, face_locations)

    for face_encoding in face_encodings:
        names = list(known_faces.keys())
        encodings = list(known_faces.values())

        matches = face_recognition.compare_faces(encodings, face_encoding, tolerance=tolerance)
        distances = face_recognition.face_distance(encodings, face_encoding)

        if True in matches:
            best_match_index = distances.argmin()
            if matches[best_match_index]:
                return names[best_match_index], True

    return "Unknown Person", False