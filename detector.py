import cv2
import numpy as np
import urllib.request
import os
import sys
import time
import threading
import queue
import datetime
from collections import Counter

# ── FACE MATCHER ─────────────────────────────────────────────────────────────
# Uses OpenCV's YuNet (face detection) + SFace (face recognition) deep-learning
# models — real facial-feature matching, not just a color/histogram guess.
# Both .onnx files must be in the models/ folder (see MODEL_DIR below).

_FACE_DET_MODEL = None   # set once MODEL_DIR is defined further down
_FACE_REC_MODEL = None


class FaceMatcher:
    """
    Loads faculty reference photos and matches them against faces detected
    in the camera frame using OpenCV's YuNet + SFace models.

    Usage:
        fm = FaceMatcher()
        fm.load_faculty()                 # or load_single_faculty(name, photo)
        faces = fm.detect_faces(frame)     # raw YuNet rows
        for face_row in faces:
            name = fm.match(frame, face_row)
    """

    # Cosine similarity threshold for a positive match.
    # We apply CLAHE normalization so embeddings are more stable,
    # allowing a slightly lower threshold for better recall.
    MATCH_THRESHOLD = 0.50

    def __init__(self):
        self._faculty  = []
        self._ready    = False   # False if models missing — disables face check
        try:
            if not os.path.exists(_FACE_DET_MODEL):
                print(f"[FaceMatcher] Detection model not found: {_FACE_DET_MODEL}")
                print("[FaceMatcher] Face recognition disabled — all persons allowed.")
                return
            if not os.path.exists(_FACE_REC_MODEL):
                print(f"[FaceMatcher] Recognition model not found: {_FACE_REC_MODEL}")
                print("[FaceMatcher] Face recognition disabled — all persons allowed.")
                return
            self._detector   = cv2.FaceDetectorYN_create(
                _FACE_DET_MODEL, "", (320, 320), 0.6, 0.3, 5000)
            self._recognizer = cv2.FaceRecognizerSF_create(_FACE_REC_MODEL, "")
            # CLAHE for lighting normalization
            self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            self._ready = True
        except Exception as e:
            print(f"[FaceMatcher] Could not load models: {e}")
            print("[FaceMatcher] Face recognition disabled — all persons allowed.")

    def _normalize_lighting(self, img):
        """Apply CLAHE histogram equalization to normalize lighting variations."""
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = self._clahe.apply(l)
        lab = cv2.merge([l, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def load_faculty(self):
        """Load all registered faculty photos from the database."""
        self._faculty = []
        try:
            from database import load_faculty_photos
            for name, photo_path in load_faculty_photos():
                feats = self._features_from_photo(photo_path)
                if feats:
                    self._faculty.append((name, feats))
                    print(f"[FaceMatcher] Loaded: {name} ({len(feats)} embedding(s))")
        except Exception as e:
            print(f"[FaceMatcher] Could not load faculty: {e}")
        print(f"[FaceMatcher] {len(self._faculty)} faculty loaded.")

    def load_single_faculty(self, name, photo_path):
        """
        Load exactly ONE imported photo as the reference face (the
        professor currently marked 'Active' on the dashboard). Once this
        is loaded, match() will only recognize this person — everyone
        else in frame is treated as unrecognized.
        """
        self._faculty = []
        feats = self._features_from_photo(photo_path)
        if feats:
            self._faculty.append((name or "Faculty", feats))
            print(f"[FaceMatcher] Active faculty loaded: {name} ({len(feats)} embedding(s))")
        else:
            print(f"[FaceMatcher] Could not find a usable face in: {photo_path}")

    def _features_from_photo(self, photo_path):
        """Detect face(s) in a reference photo and return a list of
        embeddings. We generate multiple augmented embeddings (original,
        normalized, brightened, darkened) for more robust matching."""
        if not self._ready:
            return []
        if not photo_path or not os.path.exists(photo_path):
            return []
        img = cv2.imread(photo_path)
        if img is None:
            return []

        embeddings = []

        # Generate variants: original + lighting-normalized + brightness tweaks
        variants = [img, self._normalize_lighting(img)]
        # Slightly brighter
        bright = cv2.convertScaleAbs(img, alpha=1.2, beta=20)
        variants.append(bright)
        # Slightly darker
        dark = cv2.convertScaleAbs(img, alpha=0.8, beta=-20)
        variants.append(dark)

        for variant in variants:
            h, w = variant.shape[:2]
            self._detector.setInputSize((w, h))
            _, faces = self._detector.detect(variant)
            if faces is None or len(faces) == 0:
                continue
            face_row = faces[0]   # YuNet returns faces sorted by confidence
            try:
                aligned = self._recognizer.alignCrop(variant, face_row)
                feat = self._recognizer.feature(aligned)
                embeddings.append(feat)
            except Exception:
                continue

        return embeddings

    def _feature_from_photo(self, photo_path):
        """Legacy wrapper — returns first embedding or None."""
        feats = self._features_from_photo(photo_path)
        return feats[0] if feats else None

    def detect_faces(self, frame):
        """
        Returns YuNet's raw detections for this frame. Each row is:
        [x, y, w, h, 5x(landmark_x, landmark_y), confidence]
        Returns [] if models not loaded.
        """
        if not self._ready:
            return []
        try:
            h, w = frame.shape[:2]
            self._detector.setInputSize((w, h))
            # Skip CLAHE on live frame for performance - camera has consistent lighting
            _, faces = self._detector.detect(frame)
            return faces if faces is not None else []
        except Exception:
            return []

    def match(self, frame, face_row):
        """
        Compare a detected face (a row from detect_faces, in `frame`)
        against all registered faculty.
        Returns faculty name if matched, None if no match or no faculty registered.
        """
        if not self._ready or not self._faculty:
            return None   # models not loaded or no faculty registered
        try:
            # Normalize live frame lighting before extracting features
            normalized = self._normalize_lighting(frame)
            aligned = self._recognizer.alignCrop(normalized, face_row)
            feat = self._recognizer.feature(aligned)
        except Exception:
            return None
        best_score = -1.0
        best_name  = None
        for name, ref_feats in self._faculty:
            # Match against ALL stored embeddings and take the best score
            for ref_feat in ref_feats:
                score = self._recognizer.match(
                    feat, ref_feat, cv2.FaceRecognizerSF_FR_COSINE)
                if score > best_score:
                    best_score = score
                    best_name  = name
        if best_score >= self.MATCH_THRESHOLD:
            return best_name
        return None   # face not recognized


# ── CONFIG ──────────────────────────────────────────────────────────────────
CAMERA_SOURCE = 0
FRAME_WIDTH   = 1280
FRAME_HEIGHT  = 720
WINDOW_TITLE  = "VOCA  |  drag=ROI  R=reset  Q=quit"

MODEL_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
YOLO_MODEL_CUSTOM = os.path.join(MODEL_DIR, "yolov8_custom.pt")
YOLO_MODEL_BASE = os.path.join(MODEL_DIR, "yolov8n.pt")
YOLO_MODEL = YOLO_MODEL_CUSTOM if os.path.exists(YOLO_MODEL_CUSTOM) else YOLO_MODEL_BASE
POSE_MODEL = os.path.join(MODEL_DIR, "pose_landmarker_lite.task")
FACE_DET_MODEL = os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx")
FACE_REC_MODEL = os.path.join(MODEL_DIR, "face_recognition_sface_2021dec.onnx")

# Wire these into FaceMatcher (defined above, before MODEL_DIR existed).
_FACE_DET_MODEL = FACE_DET_MODEL
_FACE_REC_MODEL = FACE_REC_MODEL

POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_lite/float16/latest/"
    "pose_landmarker_lite.task"
)

os.makedirs(MODEL_DIR, exist_ok=True)

# ── ACTIVITY COLOURS ─────────────────────────────────────────────────────────
ACTIVITIES = {
    "Writing on Board":       (0,   210, 100),
    "Instructional Gesturing":    (30,  144, 255),
    "Active Roving":            (102,181,164),
    "Seated Instruction":       (91,160,217),
    "Ambient / Idle": (160, 160, 160), "Interacting with the Board":       (160, 160, 160),
    "No Person Detected":         (60,   60,  60),
}

# ── MEDIAPIPE LANDMARK INDICES ───────────────────────────────────────────────
_LS, _RS = 11, 12
_LE, _RE = 13, 14
_LW, _RW = 15, 16
_LH, _RH = 23, 24
_NOSE    = 0

_SKELETON = [
    (11,12),(11,13),(13,15),(12,14),(14,16),
    (11,23),(12,24),(23,24),(23,25),(24,26),(25,27),(26,28),
    (15,17),(15,19),(16,18),(16,20),
]


# ══════════════════════════════════════════════════════════════════════════════
#  MODEL DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════

def _download(url, dest, label):
    if os.path.exists(dest):
        return
    print(f"[VOCA] Downloading {label} ...")
    try:
        def _hook(count, block, total):
            if total > 0:
                pct = min(count * block * 100 // total, 100)
                print(f"\r  {pct}%", end="", flush=True)
        urllib.request.urlretrieve(url, dest, reporthook=_hook)
        print(f"\r  Done -> {dest}")
    except Exception as e:
        print(f"\n[VOCA] WARNING: Could not download {label}: {e}")
        print(f"       Place it manually at: {dest}")


# ══════════════════════════════════════════════════════════════════════════════
#  ACTIVITY CLASSIFIER
# ══════════════════════════════════════════════════════════════════════════════

def classify(landmarks, gesture_tracker=None):
    """
    Activity Classifier — VOCA System

    Priority:
      1. Writing on Board        — wrist(s) raised clearly above shoulder
      2. Instructional Gesturing — arms/hands moving between waist and chest,
                                   or arms slightly above waist line
      3. Ambient / Idle          — default (standing, talking, no arm movement)

    MediaPipe y-axis: increases DOWNWARD (0 = top, 1 = bottom of frame).
    """
    if not landmarks:
        return "No Person Detected", 0.0

    lm = landmarks

    def y(i): return lm[i][1] if isinstance(lm[i], tuple) else lm[i].y
    def x(i): return lm[i][0] if isinstance(lm[i], tuple) else lm[i].x
    def vis(i): return lm[i][2] if isinstance(lm[i], tuple) else (getattr(lm[i], "visibility", 1.0) or 0.0)

    # ── Key body reference points ──────────────────────────────────────────
    sh_mid_y  = (y(_LS) + y(_RS)) / 2          # shoulder midpoint (y)
    sh_mid_x  = (x(_LS) + x(_RS)) / 2          # shoulder midpoint (x)
    hip_mid_y = (y(_LH) + y(_RH)) / 2          # hip midpoint (y)
    torso_h   = max(abs(hip_mid_y - sh_mid_y), 0.05)   # torso height (normalised)
    shoulder_w = abs(x(_LS) - x(_RS))          # shoulder width reference

    # Waist line = midpoint between shoulder and hip
    waist_y = sh_mid_y + torso_h * 0.5

    # ── Wrist positions ────────────────────────────────────────────────────
    lw_y = y(_LW);  rw_y = y(_RW)
    lw_x = x(_LW);  rw_x = x(_RW)
    if gesture_tracker is not None:
        gesture_tracker.update(lw_x, lw_y, rw_x, rw_y)

    # How far each wrist is ABOVE the shoulder (positive = above shoulder line)
    lw_raise  = sh_mid_y - lw_y
    rw_raise  = sh_mid_y - rw_y
    max_raise = max(lw_raise, rw_raise)

    # Wrist vertical distance below shoulder (positive = below)
    lw_below_sh = lw_y - sh_mid_y
    rw_below_sh = rw_y - sh_mid_y

    # ── Elbow positions ────────────────────────────────────────────────────
    le_y = y(_LE);  re_y = y(_RE)
    le_above_sh = (sh_mid_y - le_y) > torso_h * 0.05
    re_above_sh = (sh_mid_y - re_y) > torso_h * 0.05

    # ── Arm bent check: elbow between shoulder and wrist vertically ────────
    # True when arm is folded/bent (holding pose) rather than extended straight
    larm_bent = sh_mid_y < le_y < (lw_y + torso_h * 0.15)
    rarm_bent = sh_mid_y < re_y < (rw_y + torso_h * 0.15)

    # ── Wrist proximity ────────────────────────────────────────────────────
    wrist_h_dist = abs(lw_x - rw_x)            # horizontal distance between wrists
    wrist_v_dist = abs(lw_y - rw_y)            # vertical distance between wrists
    # Wrists close = both hands near each other (holding same object)
    wrists_close = (wrist_h_dist < shoulder_w * 1.2 and
                    wrist_v_dist < torso_h * 0.30)

    # ── Wrist spread (for gesturing) ───────────────────────────────────────
    spread_ratio = wrist_h_dist / max(shoulder_w, 0.01)

    # ── Wrist horizontal position relative to body centre ─────────────────
    wrist_cx      = (lw_x + rw_x) / 2
    wrists_centre = abs(sh_mid_x - wrist_cx) < shoulder_w * 1.0   # hands in front

    # ══════════════════════════════════════════════════════════════════════
    #  RULE 1 — Writing on Board
    #  One or both wrists raised clearly above shoulder line,
    #  and the elbow on that side is also up (arm extended upward).
    # ══════════════════════════════════════════════════════════════════════
    # Check if facing away by looking at shoulder X coordinates!
    # If facing the camera, the person's left shoulder (_LS) is on the right side of the image (x is larger).
    # If facing away, their left shoulder is on the left side of the image (x is smaller).
    facing_away = x(_LS) > x(_RS)  # frame is horizontally flipped!

    # If they are facing the board (turned away) AND their hand is at least at chest level
    # OR if they are facing the camera but reach HIGH up (above head)
    writing = (
        (facing_away and (lw_raise > -torso_h * 0.2 or rw_raise > -torso_h * 0.2)) or
        (lw_raise > shoulder_w * 0.5 or rw_raise > shoulder_w * 0.5)
    )
    if writing:
        conf = round(min(1.0, 0.60 + max_raise * 1.5), 2)
        return "Writing on Board", conf

    # ══════════════════════════════════════════════════════════════════════
    #  RULE 3 — Instructional Gesturing
    #  Arms/hands active between waist and chest area, OR slightly above waist.
    #
    #  Triggers when:
    #    A) Arms spread between waist and chest zone (pointing, directing)
    #    B) One or both wrists moving above waist line (emphasis gestures)
    #    C) One arm extended outward at chest/waist height
    #
    #  Zone: between waist (sh + 50% torso) and shoulder level
    # ══════════════════════════════════════════════════════════════════════
    # Wrist is in the gesturing zone: between shoulder and waist
    lw_gesture_zone = sh_mid_y < lw_y < waist_y + torso_h * 0.15
    rw_gesture_zone = sh_mid_y < rw_y < waist_y + torso_h * 0.15

    # Wrist slightly above waist (emphasis / pointing downward gesture)
    lw_above_waist = lw_y < waist_y + torso_h * 0.20
    rw_above_waist = rw_y < waist_y + torso_h * 0.20

    # One wrist extended out to the side
    lw_extended = abs(lw_x - x(_LS)) > shoulder_w * 0.6 and vis(_LW) > 0.5
    rw_extended = abs(rw_x - x(_RS)) > shoulder_w * 0.6 and vis(_RW) > 0.5

    gesture_a = (lw_gesture_zone and rw_gesture_zone and
                 spread_ratio > 0.6)                    # arms somewhat spread at chest/waist

    gesture_b = ((lw_above_waist or rw_above_waist) and
                 not (lw_raise > torso_h * 0.12 or
                      rw_raise > torso_h * 0.12))       # above waist but not above shoulder

    gesture_c = ((lw_extended and lw_gesture_zone) or
                 (rw_extended and rw_gesture_zone))     # arm extended at chest/waist height

    gesturing = gesture_a or gesture_b or gesture_c
    if gesturing:
        if gesture_tracker is None or gesture_tracker.is_moving(0.025):
            conf = round(min(1.0, 0.58 + spread_ratio * 0.12), 2)
            return "Instructional Gesturing", conf
        else:
            return "Ambient / Idle", 0.88

    # ══════════════════════════════════════════════════════════════════════
    #  RULE 4 — Ambient / Idle
    #  Arms hanging down, standing still, talking without arm movement
    # ══════════════════════════════════════════════════════════════════════


    return "Ambient / Idle", 0.88


# ══════════════════════════════════════════════════════════════════════════════
#  SMOOTHING BUFFER
# ══════════════════════════════════════════════════════════════════════════════

class SmoothBuffer:
    def __init__(self, size=20):
        self._buf  = []
        self._size = size

    def push(self, label):
        self._buf.append(label)
        if len(self._buf) > self._size:
            self._buf.pop(0)

    def top(self):
        if not self._buf:
            return "No Person Detected"
        return Counter(self._buf).most_common(1)[0][0]


# ══════════════════════════════════════════════════════════════════════════════
#  LANDMARK SMOOTHER  — averages keypoint positions over N frames
# ══════════════════════════════════════════════════════════════════════════════

class LandmarkSmoother:
    """
    Exponential moving average on each landmark x,y position.
    alpha=1.0 = no smoothing (raw), alpha=0.1 = very smooth but laggy.
    alpha=0.4 is a good balance for live pose.
    """
    def __init__(self, n_landmarks=33, alpha=0.4):
        self._alpha = alpha
        self._n    = n_landmarks
        self._xs   = None
        self._ys   = None

    def smooth(self, landmarks):
        """
        Returns a list of (x, y, visibility) tuples, smoothed.
        landmarks: list of NormalizedLandmark from MediaPipe
        """
        xs = [lm.x for lm in landmarks]
        ys = [lm.y for lm in landmarks]
        vs = [getattr(lm, "visibility", 1.0) or 0.0 for lm in landmarks]

        if self._xs is None:
            self._xs = xs[:]
            self._ys = ys[:]
        else:
            a = self._alpha
            self._xs = [a * nx + (1 - a) * px for nx, px in zip(xs, self._xs)]
            self._ys = [a * ny + (1 - a) * py for ny, py in zip(ys, self._ys)]

        return list(zip(self._xs, self._ys, vs))

    def reset(self):
        self._xs = None
        self._ys = None


# ══════════════════════════════════════════════════════════════════════════════
#  BOUNDING BOX SMOOTHER — prevents box from jumping around
# ══════════════════════════════════════════════════════════════════════════════


class GestureTracker:
    def __init__(self, history_size=15):
        self.history = []
        self.history_size = history_size
        
    def update(self, lw_x, lw_y, rw_x, rw_y):
        self.history.append((lw_x, lw_y, rw_x, rw_y))
        if len(self.history) > self.history_size:
            self.history.pop(0)
            
    def is_moving(self, threshold=0.025):
        if len(self.history) < self.history_size:
            return True
        lw_x_vals = [h[0] for h in self.history]
        lw_y_vals = [h[1] for h in self.history]
        rw_x_vals = [h[2] for h in self.history]
        rw_y_vals = [h[3] for h in self.history]
        lw_dx = max(lw_x_vals) - min(lw_x_vals)
        lw_dy = max(lw_y_vals) - min(lw_y_vals)
        rw_dx = max(rw_x_vals) - min(rw_x_vals)
        rw_dy = max(rw_y_vals) - min(rw_y_vals)
        return (lw_dx > threshold) or (lw_dy > threshold) or (rw_dx > threshold) or (rw_dy > threshold)

class BoxSmoother:
    """Exponential moving average on bounding box coords."""
    def __init__(self, alpha=0.35):
        self._alpha = alpha
        self._box   = None

    def smooth(self, box):
        """box = (x1, y1, x2, y2) ints"""
        if self._box is None:
            self._box = [float(v) for v in box]
        else:
            a = self._alpha
            self._box = [a * n + (1 - a) * p
                         for n, p in zip(box, self._box)]
        return tuple(int(v) for v in self._box)

    def reset(self):
        self._box = None


# ══════════════════════════════════════════════════════════════════════════════
#  WRIST STABILITY TRACKER
#  Measures how much the wrists are moving between frames.
#  Holding an object = wrists are relatively STILL.
#  Gesturing         = wrists are MOVING.
# ══════════════════════════════════════════════════════════════════════════════

class Detector(threading.Thread):
    """
    Background thread: opens camera, runs YOLO + MediaPipe,
    puts result dicts into result_queue.

    Constructor accepts an optional limit_sec (int):
      0 or None = unlimited
      N         = auto-stop after N seconds and push {"timeout": True}
    """

    def __init__(self, result_queue: queue.Queue,
                 camera_source=0, limit_sec=0,
                 faculty_photo=None, faculty_name=None, save_video=False):
        super().__init__(daemon=True)
        self._queue         = result_queue
        self._camera_source = camera_source
        self._limit_sec     = limit_sec or 0   # 0 = unlimited
        self._faculty_photo = faculty_photo    # imported photo of the active prof
        self._faculty_name  = faculty_name     # active prof's name
        self._save_video    = save_video
        print(f"[Detector] save_video initialized to: {self._save_video}")
        self._video_writer  = None
        self._video_path    = None
        self._stop_event    = threading.Event()
        self._start_time    = None

    def stop(self):
        self._stop_event.set()

    def _put(self, msg: dict):
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
        try:
            self._queue.put_nowait(msg)
        except queue.Full:
            pass

    def run(self):
        self._put({"status": "Downloading / loading models…"})
        _download(POSE_MODEL_URL, POSE_MODEL, "pose_landmarker_lite.task")

        yolo = None
        _yolo_device = "cpu"
        try:
            from ultralytics import YOLO
            import torch
            self._put({"status": "Loading YOLOv8n…"})
            yolo = YOLO(YOLO_MODEL)
            if torch.cuda.is_available():
                _yolo_device = "cuda"
                yolo.to("cuda")
                if hasattr(yolo.model, "half"):
                    yolo.model.half()  # FP16 for ~2x speed on RTX
                print(f"[Detector] YOLO running on GPU: {torch.cuda.get_device_name(0)}")
            else:
                print("[Detector] YOLO running on CPU (no CUDA)")
        except Exception as e:
            print(f"[Detector] YOLOv8 not available: {e}")

        pose_landmarker = None
        try:
            import mediapipe as mp
            from mediapipe.tasks.python.vision import (
                PoseLandmarker, PoseLandmarkerOptions, RunningMode
            )
            if not os.path.exists(POSE_MODEL):
                raise FileNotFoundError(f"Pose model not found: {POSE_MODEL}")
            options = PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=POSE_MODEL),
                running_mode=RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.3,
                min_pose_presence_confidence=0.3,
                min_tracking_confidence=0.3,
            )
            pose_landmarker = PoseLandmarker.create_from_options(options)
        except Exception as e:
            print(f"[Detector] MediaPipe Pose not available: {e}")

        self._put({"status": f"Opening camera {self._camera_source}…"})
        # On Windows, cv2.VideoCapture() opened from a background thread
        # (this class IS a thread — started from the dashboard) can hang
        # indefinitely with the default backend (MSMF) due to COM
        # apartment-threading conflicts. This is exactly why running
        # detector.py directly (main thread) works fine but starting the
        # camera through the dashboard freezes. DSHOW is far more
        # reliable when opened off the main thread.
        cap = None
        cap = None
        if os.name == "nt" and isinstance(self._camera_source, int):
            cap = cv2.VideoCapture(self._camera_source, cv2.CAP_DSHOW)
        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(self._camera_source)
        if not cap.isOpened():
            self._put({"error": f"Cannot open camera '{self._camera_source}'."})
            return

        if self._save_video:
            os.makedirs("reports", exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self._video_path = os.path.join("reports", f"recording_{timestamp}.mp4")
            self._video_writer = None  # Will be initialized on first frame

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Reduce latency/lag

        smooth        = SmoothBuffer(size=20)
        lm_smoother   = LandmarkSmoother(n_landmarks=33, alpha=0.75)
        box_smoother  = BoxSmoother(alpha=0.35)
        face_matcher = FaceMatcher()
        if self._faculty_photo:
            # A specific professor was set "Active" on the dashboard and their
            # imported photo was passed in — lock detection to that person only.
            self._put({"status": f"Loading face profile for {self._faculty_name}…"})
            face_matcher.load_single_faculty(self._faculty_name, self._faculty_photo)
        else:
            # No active faculty selected — allow anyone in frame (old behavior).
            face_matcher._faculty = []
        recognized_name  = None
        _match_candidate = None   # last person matched, awaiting confirmation
        _match_streak    = 0      # consecutive checks that agreed on _match_candidate
        _REQUIRED_STREAK = 3      # must match the SAME person 3 checks in a row
        frame_idx  = 0
        prev_box   = None
        prev_conf  = 0.0
        ts_ms      = 0
        t_prev     = time.time()
        fps        = 0.0
        self._start_time = time.time()
        face_visible = False
        auth_face_box = None
        last_face_draws = []
        is_authorized = True
        unseen_frames = 0
        gesture_tracker = GestureTracker()

        self._put({"status": "Camera ready — detecting…"})

        last_smoothed_lms = None
        last_mp_activity = None
        last_mp_conf = 0.0

        try:
            while not self._stop_event.is_set():

                # ── Duration limit check ──────────────────────────────────────
                elapsed = int(time.time() - self._start_time)
                if self._limit_sec > 0 and elapsed >= self._limit_sec:
                    self._put({"timeout": True, "elapsed": elapsed})
                    break

                remaining = (self._limit_sec - elapsed) if self._limit_sec > 0 else None

                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                frame = cv2.flip(frame, 1)
                fh, fw = frame.shape[:2]
                output = frame.copy()

                search = frame
                ox, oy = 0, 0
                sh, sw = fh, fw

                person_crop = search
                px_off, py_off = ox, oy

                # -- Face recognition every 8 frames (was 15) — checking more
                # often means a covered/changed face gets re-verified sooner
                # instead of the old ~0.5s lag before the system reacts.
                if frame_idx % 15 == 0:
                    faces = face_matcher.detect_faces(frame)
                    face_visible = len(faces) > 0
                
                    last_face_draws = []
                
                    if face_visible:
                        cycle_match = None
                        for face_row in faces:
                            fx, fy, fw2, fh2 = face_row[:4].astype(int)
                            matched = face_matcher.match(frame, face_row)
                            if matched:
                                cycle_match = matched
                                auth_face_box = (fx, fy, fx+fw2, fy+fh2)
                                last_face_draws.append((fx, fy, fw2, fh2, matched, True))
                                break
                            else:
                                last_face_draws.append((fx, fy, fw2, fh2, "Unknown", False))

                        if not cycle_match:
                            auth_face_box = None
                        
                        if cycle_match:
                            if _match_candidate == cycle_match:
                                _match_streak += 1
                            else:
                                _match_candidate = cycle_match
                                _match_streak = 1
                        else:
                            _match_candidate = "Unknown"
                            _match_streak += 1

                    if _match_candidate != "Unknown" and _match_streak >= _REQUIRED_STREAK:
                        recognized_name = _match_candidate
                        unseen_frames = 0
                    elif _match_candidate == "Unknown" and _match_streak >= 10:
                        recognized_name = None
            
                # Persistent drawing of face boxes every frame
                for (fx, fy, fw2, fh2, label_txt, is_match) in last_face_draws:
                    if is_match:
                        cv2.rectangle(output,(fx,fy),(fx+fw2,fy+fh2),(34,197,94),4)
                        cv2.putText(output,label_txt,(fx,fy-15),cv2.FONT_HERSHEY_SIMPLEX,1.1,(34,197,94),3)
                    else:
                        cv2.rectangle(output,(fx,fy),(fx+fw2,fy+fh2),(60,60,200),4)
                        cv2.putText(output,label_txt,(fx,fy-15),cv2.FONT_HERSHEY_SIMPLEX,0.9,(60,60,200),2)
            
                is_authorized = True
                if face_matcher._faculty:
                    is_authorized = (recognized_name is not None)

                custom_activity = None
                if not is_authorized:
                    prev_box = None
                    box_smoother.reset()

                if is_authorized:
                    if yolo is not None and frame_idx % 6 == 0:
                        try:
                            is_custom = len(yolo.names) < 80
                            y_classes = None if is_custom else [0]
                            results = yolo(search, classes=y_classes, verbose=False, conf=0.20, imgsz=416, device=_yolo_device, half=(_yolo_device=="cuda"))
                            boxes   = results[0].boxes if results else None
                            if boxes is not None and len(boxes) > 0:
                                best = -1
                                max_iou = -1
                            
                                target_box = None
                                if face_visible and auth_face_box is not None:
                                    target_box = auth_face_box
                                elif prev_box is not None:
                                    target_box = prev_box
                                
                                if target_box is not None:
                                    tx1, ty1, tx2, ty2 = target_box
                                    for i, b in enumerate(boxes.xyxy.cpu().numpy()):
                                        bx1, by1, bx2, by2 = b
                                        inter = max(0, min(bx2, tx2) - max(bx1, tx1)) * max(0, min(by2, ty2) - max(by1, ty1))
                                        area_t = (tx2 - tx1) * (ty2 - ty1)
                                        coverage = inter / float(area_t + 1e-6)
                                        if coverage > max_iou:
                                            max_iou = coverage
                                            best = i
                                    if max_iou < 0.50:
                                        best = -1
                                if best == -1:
                                    best = int(boxes.conf.argmax())
                            
                                if best != -1:
                                    best_cls = int(boxes.cls[best].cpu())
                                    if is_custom:
                                        custom_activity = yolo.names[best_cls]
                                    bx1, by1, bx2, by2 = (
                                        boxes.xyxy[best].cpu().numpy().astype(int))
                                    raw_box   = (bx1, by1, bx2, by2)
                                    prev_box  = box_smoother.smooth(raw_box)
                                    prev_conf = float(boxes.conf[best].cpu())
                                else:
                                    prev_box = None
                                    box_smoother.reset()
                                    custom_activity = None
                            else:
                                prev_box = None
                                box_smoother.reset()
                        except Exception:
                            pass

                if is_authorized and face_matcher._faculty:
                    if prev_box is None:
                        unseen_frames += 1
                    else:
                        unseen_frames = 0
                
                    if unseen_frames > 300:
                        recognized_name = None
                        _match_candidate = None
                        _match_streak = 0
                        is_authorized = False

                if prev_box:
                    bx1, by1, bx2, by2 = prev_box
                
                    # Show the truth in the box label: the actual verified
                    # faculty name when one's active and confirmed, otherwise
                    # a plain "Person" — never a hardcoded "Faculty" claim.
                    box_label = recognized_name if (face_matcher._faculty and recognized_name) else "Person"
                    draw_yolo_box(output,
                                  bx1 + ox, by1 + oy,
                                  bx2 + ox, by2 + oy,
                                  prev_conf, box_label)
                    m = 20
                    cx1 = max(0, bx1 - m); cy1 = max(0, by1 - m)
                    cx2 = min(sw, bx2 + m); cy2 = min(sh, by2 + m)
                    person_crop = search[cy1:cy2, cx1:cx2]
                    px_off = ox + cx1
                    py_off = oy + cy1

                if not is_authorized:
                    if face_visible:
                        activity = "Unrecognized Person"
                    else:
                        activity = "Waiting for Faculty..."
                else:
                    activity = "Ambient / Idle" 
                
                confidence = 0.0
                mp_activity = None
                mp_conf = 0.0

                if is_authorized and prev_box is not None and pose_landmarker is not None and search.size > 0:
                    if frame_idx % 2 == 0:
                        try:
                            import mediapipe as mp
                            rgb    = cv2.cvtColor(search, cv2.COLOR_BGR2RGB)
                            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                            ts_ms += 33
                            result = pose_landmarker.detect_for_video(mp_img, ts_ms)
                            if result.pose_landmarks and len(result.pose_landmarks) > 0:
                                raw_lms = result.pose_landmarks[0]

                                ch, cw = person_crop.shape[:2]
                                lw_px = int(raw_lms[_LW].x * cw) + px_off
                                lw_py = int(raw_lms[_LW].y * ch) + py_off
                                rw_px = int(raw_lms[_RW].x * cw) + px_off
                                rw_py = int(raw_lms[_RW].y * ch) + py_off

                                last_smoothed_lms = lm_smoother.smooth(raw_lms)
                                mp_activity, mp_conf = classify(last_smoothed_lms, gesture_tracker)
                                last_mp_activity, last_mp_conf = mp_activity, mp_conf
                            else:
                                last_smoothed_lms = None
                                lm_smoother.reset()
                        except Exception:
                            pass
                    else:
                        mp_activity = last_mp_activity
                        mp_conf = last_mp_conf
                
                    if last_smoothed_lms is not None:
                        draw_skeleton(output, last_smoothed_lms, search.shape, ox, oy)

                # ── Combine YOLO and MediaPipe ─────────────────────────────
                is_turned_around = (face_matcher._faculty and not face_visible)
            
                # 1. Writing on Board (if back is turned / face not visible)
                if is_turned_around and mp_activity and mp_activity != "No Person Detected":
                    activity = "Writing on Board"
                    confidence = mp_conf
                
                # 2. Custom Activities
                elif custom_activity and custom_activity not in ["Person", "Teaching or asking", "Writing"]:
                    activity = custom_activity
                    confidence = prev_conf
                
                # 3. Instructional Gesturing / MediaPipe gestures
                elif mp_activity and mp_activity != "Ambient / Idle":
                    activity = mp_activity
                    confidence = mp_conf
                
                # 4. Fallbacks
                elif custom_activity:
                    activity = custom_activity
                    confidence = prev_conf
                elif mp_activity:
                    activity = mp_activity
                    confidence = mp_conf
                
                smooth.push(activity)
                smoothed = smooth.top()

                draw_roi(output)

                # Add overlay
                draw_hud(output, smoothed, confidence, elapsed_sec=elapsed, remaining_sec=remaining)
                
                if self._save_video:
                    if self._video_writer is None:
                        h, w = output.shape[:2]
                        self._video_writer = cv2.VideoWriter(self._video_path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
                    self._video_writer.write(output)
                        
                ts = time.time()
                if ts - t_prev > 0:
                    fps = 1.0 / (ts - t_prev)
                t_prev = ts
            
                self._put({
                    "activity":   smoothed,

                    "timestamp":  ts,
                    "fps":        round(fps, 1),
                    "frame":      output,
                    "elapsed":    elapsed,
                    "remaining":  remaining,
                    "recordable": True,
                })

                frame_idx += 1
        except Exception as e:
            import traceback
            with open("crash.log", "w") as errf:
                errf.write(traceback.format_exc())
            self._put({"error": f"Detector crashed: {str(e)}"})
        finally:
            if self._video_writer:
                self._video_writer.release()
                self._put({"video_saved": self._video_path})
            if cap:
                cap.release()
            if pose_landmarker:
                try: pose_landmarker.close()
                except: pass
            print("[Detector] Stopped.")


# ══════════════════════════════════════════════════════════════════════════════
#  STANDALONE — run directly for the OpenCV window with ROI drag support
# ══════════════════════════════════════════════════════════════════════════════



# ── DRAWING HELPERS ───────────────────────────────────────────────────────────

def draw_yolo_box(frame, x1, y1, x2, y2, conf, label_text="Person"):
    cv2.rectangle(frame, (x1,y1),(x2,y2),(255,210,0),4)
    label = f"{label_text}  {conf:.0%}"
    (lw,lh),_ = cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,0.6,2)
    cv2.rectangle(frame,(x1,y1-lh-14),(x1+lw+12,y1),(255,210,0),-1)
    cv2.putText(frame,label,(x1+6,y1-8),cv2.FONT_HERSHEY_SIMPLEX,1.0,(0,0,0),3)


def draw_skeleton(frame, landmarks, crop_shape, off_x, off_y):
    _SKELETON = [
            (11,12),(11,13),(13,15),(12,14),(14,16),
            (11,23),(12,24),(23,24),(23,25),(24,26),(25,27),(26,28),
            (15,17),(15,19),(16,18),(16,20),
    ]
    ch, cw = crop_shape[:2]
    pts = {}
    for i, lm in enumerate(landmarks):
            if isinstance(lm, tuple):
                sx, sy, v = lm[0], lm[1], lm[2] if len(lm) > 2 else 1.0
            else:
                sx = lm.x; sy = lm.y
                v  = getattr(lm,"visibility",1.0) or 0.0
            if v > 0.35:
                px = int(sx*cw) + off_x
                py = int(sy*ch) + off_y
                pts[i] = (px,py)
                cv2.circle(frame,(px,py),8,(0,255,255),-1)
                cv2.circle(frame,(px,py),8,(0,0,0),2)
    for a,b in _SKELETON:
            if a in pts and b in pts:
                cv2.line(frame,pts[a],pts[b],(0,220,255),4)


def draw_hud(frame, activity, confidence, elapsed_sec=None, remaining_sec=None):
    return
    LABEL_COLORS = {
            "Writing on Board":         (59,130,246),
            "Instructional Gesturing":  (6,182,212),
            "Active Roving":            (102,181,164),
            "Seated Instruction":       (91,160,217),
            "Ambient / Idle": (160, 160, 160), "Interacting with the Board":           (100,116,139),
            "No Person Detected":       (60,60,60),
            "Unrecognized Person":      (60,60,200),
            "Waiting for Faculty...":   (100,116,139),
    }
    h, w = frame.shape[:2]
    color = LABEL_COLORS.get(activity,(200,200,200))
    bar = frame.copy()
    cv2.rectangle(bar,(0,h-120),(w,h),(15,15,15),-1)
    cv2.addWeighted(bar,0.55,frame,0.45,0,frame)
    cv2.putText(frame,activity,(32,h-70),cv2.FONT_HERSHEY_DUPLEX,1.3,color,3)
    bar_w = int(confidence*400)
    cv2.rectangle(frame,(32,h-50),(432,h-20),(50,50,50),-1)
    cv2.rectangle(frame,(32,h-50),(32+bar_w,h-20),color,-1)
    cv2.putText(frame,f"{confidence:.0%}",(445,h-25),
                    cv2.FONT_HERSHEY_SIMPLEX,1.0,(200,200,200),2)
    if elapsed_sec is not None:
            eh=elapsed_sec//3600; em=(elapsed_sec%3600)//60; es=elapsed_sec%60
            cv2.putText(frame,f"Elapsed: {eh:02d}:{em:02d}:{es:02d}",
                        (w-400,h-70),cv2.FONT_HERSHEY_SIMPLEX,1.0,(180,180,180),2)
    if remaining_sec is not None and remaining_sec >= 0:
            rh=remaining_sec//3600; rm=(remaining_sec%3600)//60; rs=remaining_sec%60
            tc = (60,60,200) if remaining_sec<=0 else              (0,165,255) if remaining_sec<=60 else              (0,215,255) if remaining_sec<=300 else (0,210,100)
            cv2.putText(frame,f"Remaining: {rh:02d}:{rm:02d}:{rs:02d}",
                        (w-400,h-30),cv2.FONT_HERSHEY_SIMPLEX,1.0,tc,3)
    for i,txt in enumerate([""]):
            cv2.putText(frame,txt,(w-175,26+i*22),
                        cv2.FONT_HERSHEY_SIMPLEX,0.5,(180,180,180),1)


# ── ROI STATE ─────────────────────────────────────────────────────────────────
roi = {"drawing": False, "x1": 0, "y1": 0, "x2": 0, "y2": 0, "locked": False}

def mouse_cb(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
            roi["drawing"] = True; roi["locked"] = False
            roi["x1"] = roi["x2"] = x; roi["y1"] = roi["y2"] = y
    elif event == cv2.EVENT_MOUSEMOVE and roi["drawing"]:
            roi["x2"] = x; roi["y2"] = y
    elif event == cv2.EVENT_LBUTTONUP and roi["drawing"]:
            roi["drawing"] = False; roi["x2"] = x; roi["y2"] = y
            if abs(roi["x2"]-roi["x1"]) > 20 and abs(roi["y2"]-roi["y1"]) > 20:
                roi["locked"] = True
            else:
                roi["locked"] = False

def roi_reset():
    roi["drawing"] = False; roi["locked"] = False
    roi["x1"] = roi["y1"] = roi["x2"] = roi["y2"] = 0

def roi_pixel_rect():
    if not roi["locked"] and not roi["drawing"]:
            return None
    x1 = min(roi["x1"], roi["x2"]); y1 = min(roi["y1"], roi["y2"])
    x2 = max(roi["x1"], roi["x2"]); y2 = max(roi["y1"], roi["y2"])
    return (x1, y1, x2, y2)

def draw_roi(frame):
    rect = roi_pixel_rect()
    if rect is None: return
    x1, y1, x2, y2 = rect
    color = (0, 255, 0) if roi["drawing"] else (0, 255, 200)
    if roi["locked"]:
            overlay = frame.copy(); h, w = frame.shape[:2]
            cv2.rectangle(overlay, (0,0),(w,h),(0,0,0),-1)
            cv2.rectangle(overlay,(x1,y1),(x2,y2),(0,0,0),-1)
            fc = frame.copy()
            cv2.addWeighted(overlay,0.35,frame,0.65,0,frame)
            frame[y1:y2, x1:x2] = fc[y1:y2, x1:x2]
    cv2.rectangle(frame,(x1,y1),(x2,y2),color,4)
    label = "Drawing ROI..." if roi["drawing"] else "ROI"
    (tw,th),_ = cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,0.6,2)
    cv2.rectangle(frame,(x1,y1-th-8),(x1+tw+8,y1),color,-1)
    cv2.putText(frame,label,(x1+6,y1-8),cv2.FONT_HERSHEY_SIMPLEX,1.0,(0,0,0),3)


def run():
    print("=" * 60)
    print("  VOCA  -  Teaching Activity Detection")
    print("=" * 60)

    _download(POSE_MODEL_URL, POSE_MODEL, "pose_landmarker_lite.task")

    yolo = None
    try:
        from ultralytics import YOLO
        print("[VOCA] Loading YOLOv8n ...")
        yolo = YOLO(YOLO_MODEL)
        print("[VOCA] YOLOv8n ready.")
    except Exception as e:
        print(f"[VOCA] YOLOv8 not available: {e}")

    pose_landmarker = None
    try:
        import mediapipe as mp
        from mediapipe.tasks.python.vision import (
            PoseLandmarker, PoseLandmarkerOptions, RunningMode
        )
        if not os.path.exists(POSE_MODEL):
            raise FileNotFoundError(f"Pose model not found: {POSE_MODEL}")
        options = PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=POSE_MODEL),
            running_mode=RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.3,
            min_pose_presence_confidence=0.3,
            min_tracking_confidence=0.3,
        )
        pose_landmarker = PoseLandmarker.create_from_options(options)
        print("[VOCA] MediaPipe PoseLandmarker ready.")
    except Exception as e:
        print(f"[VOCA] MediaPipe Pose not available: {e}")

    print(f"[VOCA] Opening camera {CAMERA_SOURCE} ...")
    cap = cv2.VideoCapture(CAMERA_SOURCE)
    if not cap.isOpened():
        print(f"[VOCA] ERROR: Cannot open camera '{CAMERA_SOURCE}'.")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Reduce latency/lag

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW_TITLE, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback(WINDOW_TITLE, mouse_cb)

    smooth        = SmoothBuffer(size=20)
    lm_smoother   = LandmarkSmoother(n_landmarks=33, alpha=0.75)
    box_smoother  = BoxSmoother(alpha=0.35)
    face_matcher  = FaceMatcher()
    face_matcher.load_faculty()
    recognized_name = None
    frame_idx = 0
    prev_box  = None
    prev_conf = 0.0
    ts_ms     = 0
    start_t   = time.time()
    face_visible = False

    print("[VOCA] Running.  Drag on the window to draw ROI.")
    print("-" * 60)

    last_smoothed_lms = None
    last_mp_activity = None
    last_mp_conf = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        frame = cv2.flip(frame, 1)
        fh, fw = frame.shape[:2]
        output = frame.copy()
        elapsed = int(time.time() - start_t)

        rect = roi_pixel_rect()
        if rect and roi["locked"]:
            rx1, ry1, rx2, ry2 = rect
            rx1 = max(0, min(rx1, fw - 1))
            ry1 = max(0, min(ry1, fh - 1))
            rx2 = max(0, min(rx2, fw - 1))
            ry2 = max(0, min(ry2, fh - 1))
            search = frame[ry1:ry2, rx1:rx2]
            ox, oy = rx1, ry1
        else:
            search = frame
            ox, oy = 0, 0

        sh, sw = search.shape[:2]
        if sh < 10 or sw < 10:
            search = frame
            ox, oy = 0, 0
            sh, sw = fh, fw

        person_crop = search
        px_off, py_off = ox, oy

        is_authorized = True
        custom_activity = None
        
        if not is_authorized:
            prev_box = None
            box_smoother.reset()

        if yolo is not None and frame_idx % 6 == 0:
            try:
                is_custom = len(yolo.names) < 80
                y_classes = None if is_custom else [0]
                results = yolo(search, classes=y_classes, verbose=False, conf=0.20, imgsz=416)
                boxes   = results[0].boxes if results else None
                if boxes is not None and len(boxes) > 0:
                    best = int(boxes.conf.argmax())
                    best_cls = int(boxes.cls[best].cpu())
                    if is_custom:
                        custom_activity = yolo.names[best_cls]
                        if custom_activity == "Sitting":
                            custom_activity = "Seated Instruction"
                        elif custom_activity == "Walking / Pacing":
                            custom_activity = "Active Roving"
                    bx1, by1, bx2, by2 = boxes.xyxy[best].cpu().numpy().astype(int)
                    prev_box  = box_smoother.smooth((bx1, by1, bx2, by2))
                    prev_conf = float(boxes.conf[best].cpu())
                else:
                    prev_box = None
                    box_smoother.reset()
            except Exception:
                pass

        if prev_box:
            bx1, by1, bx2, by2 = prev_box
            draw_yolo_box(output, bx1 + ox, by1 + oy, bx2 + ox, by2 + oy, prev_conf, custom_activity if custom_activity else "Person")
            m = 20
            cx1 = max(0, bx1 - m); cy1 = max(0, by1 - m)
            cx2 = min(sw, bx2 + m); cy2 = min(sh, by2 + m)
            person_crop = search[cy1:cy2, cx1:cx2]
            px_off = ox + cx1
            py_off = oy + cy1

        activity   = "No Person Detected"
        confidence = 0.0
        mp_activity = None
        mp_conf = 0.0

        if is_authorized and prev_box is not None and pose_landmarker is not None and search.size > 0:
            if frame_idx % 2 == 0:
                try:
                    import mediapipe as mp
                    rgb    = cv2.cvtColor(search, cv2.COLOR_BGR2RGB)
                    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    ts_ms += 33
                    result = pose_landmarker.detect_for_video(mp_img, ts_ms)
                    if result.pose_landmarks and len(result.pose_landmarks) > 0:
                        raw_lms = result.pose_landmarks[0]

                        ch2, cw2 = search.shape[:2]
                        lw_px = int(raw_lms[_LW].x * cw2) + ox
                        lw_py = int(raw_lms[_LW].y * ch2) + oy
                        rw_px = int(raw_lms[_RW].x * cw2) + ox
                        rw_py = int(raw_lms[_RW].y * ch2) + oy

                        last_smoothed_lms = lm_smoother.smooth(raw_lms)
                        mp_activity, mp_conf = classify(last_smoothed_lms, gesture_tracker)
                        last_mp_activity, last_mp_conf = mp_activity, mp_conf
                    else:
                        last_smoothed_lms = None
                        lm_smoother.reset()
                except Exception:
                    pass
            else:
                mp_activity = last_mp_activity
                mp_conf = last_mp_conf
            
            if last_smoothed_lms is not None:
                draw_skeleton(output, last_smoothed_lms, search.shape, ox, oy)

        # ── Combine YOLO and MediaPipe ─────────────────────────────
        is_turned_around = (face_matcher._faculty and not face_visible)
        
        if is_turned_around and mp_activity and mp_activity != "No Person Detected":
            activity = "Writing on Board"
            confidence = mp_conf
        elif custom_activity and custom_activity not in ["Person", "Teaching or asking", "Writing"]:
            activity = custom_activity
            confidence = prev_conf
        elif mp_activity and mp_activity != "Ambient / Idle":
            activity = mp_activity
            confidence = mp_conf
        elif custom_activity:
            activity = custom_activity
            confidence = prev_conf
        elif mp_activity:
            activity = mp_activity
            confidence = mp_conf

        smooth.push(activity)
        smoothed = smooth.top()

        draw_roi(output)
        draw_hud(output, smoothed, confidence, elapsed_sec=elapsed)

        cv2.imshow(WINDOW_TITLE, output)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), ord('Q')):
            break
        elif key in (ord('r'), ord('R')):
            roi_reset()

        frame_idx += 1

    cap.release()
    if pose_landmarker:
        pose_landmarker.close()
    cv2.destroyAllWindows()
    print("[VOCA] Closed.")


if __name__ == "__main__":
    run()
