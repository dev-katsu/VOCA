"""
VOCA - App Entry Point
File: app.py

One continuous Eel session: login.html -> dashboard.html by browser
navigation (see login.js). This file exposes the old Tkinter
dashboard.py behaviour to the HTML/JS side:

  - Session Setup (subject, course, room, date, limit)
  - Start / Stop recording with detector.Detector (unchanged)
  - Live feed window (livefeed.html) fed with JPEG frames
  - Per-activity frame counts, log, elapsed / remaining timer
  - Auto-stop at the duration limit and auto-save to the database
"""

import eel
import os
import re
import json
import time
import queue
import base64
import uuid
import platform
import subprocess
import datetime
import threading

from login import init_users, check_login, register_user
import database
import pdf_export

FACULTY_PHOTOS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "faculty_photos")
REPORTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "reports")

# Same three activity labels the detector / old dashboard.py used.
ACT_LABELS = ["Writing on Board", "Instructional Gesturing", "Ambient / Idle", "Interacting with the Board", "Crossing legs", "Guiding students", "Looking at the screen", "Teaching or asking", "Using a phone", "Writing"]


# ---------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------

@eel.expose
def try_login(username, password):
    result = check_login(username, password)
    if result:
        fullname, role = result
        return {"ok": True, "fullname": fullname, "role": role}
    return {"ok": False}


@eel.expose
def try_register(username, password, fullname, role):
    """Kept for compatibility. Role comes from the client here, so
    prefer try_signup for public sign-up."""
    ok, msg = register_user(username, password, fullname, role)
    return {"ok": ok, "msg": msg}


@eel.expose
def try_signup(fullname, faculty_id, password):
    """Called by signup.js. Role is fixed server-side to 'Faculty'."""
    ok, msg = register_user(faculty_id, password, fullname, "Faculty")
    return {"ok": ok, "message": msg}


# ---------------------------------------------------------------
# FACULTY MANAGEMENT
# ---------------------------------------------------------------

def _photo_to_data_uri(photo_path):
    if not photo_path or not os.path.exists(photo_path):
        return None
    try:
        with open(photo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None


def _active_faculty_row():
    """(id, name, photo_path) of the Active faculty, or None."""
    active_id = database.get_setting("active_faculty_id")
    if not active_id:
        return None
    for fid, name, photo in database.load_faculty_list():
        if str(fid) == str(active_id):
            return fid, name, photo
    return None


@eel.expose
def get_camera_source():
    return _camera_source()

@eel.expose
def test_camera_source(val):
    val_str = str(val).strip()
    src = int(val_str) if val_str.isdigit() else val_str
    
    import cv2, base64
    cap = None
    if type(src) is int and __import__("os").name == "nt":
        cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
    if cap is None or not cap.isOpened():
        cap = cv2.VideoCapture(src)
        
    if not cap.isOpened():
        return {"ok": False, "msg": f"Failed to open camera {src}"}
        
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    ret, frame = cap.read()
    cap.release()
    
    if not ret or frame is None:
        return {"ok": False, "msg": f"Opened camera {src}, but failed to read frame."}
        
    h, w = frame.shape[:2]
    if w > 1280:
        scale = 1280 / w
        frame = cv2.resize(frame, (1280, int(h * scale)))
        
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
    if not ok:
        return {"ok": False, "msg": "Failed to encode frame."}
        
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    uri = f"data:image/jpeg;base64,{b64}"
    return {"ok": True, "uri": uri, "shape": f"{w}x{h}"}

@eel.expose
def set_camera_source(val):
    import database
    database.set_setting("camera_source", str(val).strip())
    return {"ok": True}

@eel.expose
def get_term_dates():
    import database
    return {
        "date_sem1": database.get_setting("term_date_sem1") or "",
        "date_sem2": database.get_setting("term_date_sem2") or ""
    }

@eel.expose
def save_term_date(term, date_val):
    import database
    if term not in ["date_sem1", "date_sem2"]:
        return {"ok": False, "msg": "Invalid term"}
    database.set_setting(f"term_{term}", str(date_val).strip())
    return {"ok": True}

@eel.expose
def get_faculty_list():
    active_id = database.get_setting("active_faculty_id")
    out = []
    for fid, name, photo in database.load_faculty_list():
        out.append({
            "id": fid,
            "name": name,
            "photo": _photo_to_data_uri(photo),
            "active": (str(fid) == str(active_id)) if active_id else False,
        })
    return out


@eel.expose
def get_active_faculty():
    row = _active_faculty_row()
    if not row:
        return None
    fid, name, photo = row
    return {"id": fid, "name": name, "photo": _photo_to_data_uri(photo)}


@eel.expose
def save_faculty_photo(name, photo_data_uri):
    name = (name or "").strip()
    if not name:
        return {"ok": False, "msg": "Please enter a faculty name."}
    if not photo_data_uri or "," not in photo_data_uri:
        return {"ok": False, "msg": "Please take or upload a photo first."}
    try:
        os.makedirs(FACULTY_PHOTOS_DIR, exist_ok=True)
        header, b64data = photo_data_uri.split(",", 1)
        raw = base64.b64decode(b64data)

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        filename = f"{safe_name}_{uuid.uuid4().hex[:8]}.jpg"
        path = os.path.join(FACULTY_PHOTOS_DIR, filename)
        with open(path, "wb") as f:
            f.write(raw)

        database.save_faculty(name, path)
        return {"ok": True, "msg": f"Saved faculty photo for {name}."}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


@eel.expose
def delete_faculty_entry(faculty_id):
    try:
        database.delete_faculty(faculty_id)
        active_id = database.get_setting("active_faculty_id")
        if active_id and str(active_id) == str(faculty_id):
            database.set_setting("active_faculty_id", "")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


@eel.expose
def set_active_faculty(faculty_id):
    database.set_setting("active_faculty_id", faculty_id)
    # Same as the old dashboard: the Active faculty becomes the instructor.
    row = _active_faculty_row()
    if row:
        s = _load_session()
        s["instructor"] = row[1]
        database.set_setting("current_session", json.dumps(s))
    return {"ok": True}

@eel.expose
def clear_session_setup():
    database.set_setting("current_session", json.dumps({}))
    database.set_setting("term_date_sem1", "")
    database.set_setting("term_date_sem2", "")
    return {"ok": True}


@eel.expose
def clear_active_faculty():
    database.set_setting("active_faculty_id", "")
    return {"ok": True}


# ---------------------------------------------------------------
# SESSION SETUP
# ---------------------------------------------------------------

def _default_session():
    return {
        "subject": "", "section": "", "instructor": "", "room": "",
        "date": datetime.date.today().strftime("%B %d, %Y"),
        "semester": "1st Semester", "school_year": "2024-2025",
        "limit_h": 0, "limit_m": 0, "course": "", "year": "", "save_video": True,
    }


def _load_session():
    data = _default_session()
    raw = database.get_setting("current_session", "")
    try:
        saved = json.loads(raw) if raw else {}
        if isinstance(saved, dict):
            data.update({k: v for k, v in saved.items() if k in data})
    except Exception:
        pass
    return data


def _to_int(v, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


@eel.expose
def get_session_setup():
    return _load_session()


@eel.expose
def set_session_setup(info):
    s = _load_session()
    info = info or {}
    for k in ("course", "year", "subject", "section", "instructor", "room", "date",
              "semester", "school_year"):
        if k in info:
            s[k] = str(info[k]).strip()
    if "limit_h" in info:
        s["limit_h"] = _to_int(info["limit_h"], 0, 8)
    if "limit_m" in info:
        s["limit_m"] = _to_int(info["limit_m"], 0, 59)
    if "save_video" in info:
        s["save_video"] = bool(info["save_video"])
        
    database.set_setting("current_session", json.dumps(s))
    return {"ok": True}




def _camera_source():
    v = str(database.get_setting("camera_source", "0")).strip()
    return int(v) if v.isdigit() else v


# ---------------------------------------------------------------
# REPORTS  (same fields / percentages / PDF layout as the old
# Tkinter _show_reports, _save_to_db and _export_pdf)
# ---------------------------------------------------------------

def _latest_saved_session():
    """Most recent row from the sessions table for the active faculty, or None."""
    rows = database.load_sessions()
    
    # Filter by active faculty if one is selected
    active = _active_faculty_row()
    if active and active[1]:
        active_name = active[1].lower().strip()
        filtered = [r for r in rows if (r[1] or "").lower().strip() == active_name]
        return filtered[0] if filtered else None
    
    return rows[0] if rows else None


def _report_source():
    """Prefer the session that just finished recording (still in memory,
    with its full per-frame log) so a save/export right after Stop has
    everything; otherwise fall back to the last row saved in the DB.
    Returns (info, counts, total, log, sid) — sid is None when the data
    is still only in memory (not yet written to the sessions table)."""
    with _lock:
        if _rec["log"]:
            info = dict(_rec["session_info"])
            info["duration"] = _fmt(_rec["last_elapsed"])
            return info, dict(_rec["counts"]), _rec["total"], list(_rec["log"]), _rec["saved_id"]

    row = _latest_saved_session()
    if not row:
        return None, {}, 0, [], None
    sid, instructor, subject, section, room, date, semester, school_year,     duration, counts_json, total_frames, log_json, created_at, *videos = row
    video_file = videos[-1] if videos else None
    info = {
        "instructor": instructor, "subject": subject, "section": section,
        "room": room, "date": date, "semester": semester,
        "school_year": school_year, "duration": duration, "video_file": video_file
    }
    counts = json.loads(counts_json or "{}")
    log = json.loads(log_json or "[]")
    return info, counts, total_frames or 0, log, sid


@eel.expose
def get_latest_report():
    """Session Details + Activity Summary for the Reports page."""
    row = _latest_saved_session()
    if not row:
        return {"ok": False}
    sid, instructor, subject, section, room, date, semester, school_year,     duration, counts_json, total_frames, log_json, created_at, *videos = row
    video_file = videos[-1] if videos else None

    counts = json.loads(counts_json or "{}")
    total = total_frames or 0
    summary = [
        {"activity": act, "pct": round(counts.get(act, 0) / total * 100) if total else 0}
        for act in ACT_LABELS
    ]
    log = json.loads(log_json or "[]")

    return {
        "ok": True,
        "id": sid,
        "session_info": {
            "subject": subject, "section": section, "instructor": instructor,
            "room": room, "date": date, "semester": semester,
            "school_year": school_year, "duration": duration, "video_file": video_file
        },
        "summary": summary,
        "log_entries": len(log),
    }


@eel.expose
def save_report_to_database():
    data = _report_source()
    if not data or not data[3]:
        return {"ok": False, "msg": "No session data to save yet."}
    info, counts, total, log, sid = data
    try:
        new_id = database.save_session(info, counts, total, log)
        return {"ok": True, "msg": f"Session saved. ID: {new_id}"}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


def _open_file(path):
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def _photo_for_instructor(name):
    """Best-effort match: the faculty member's registered photo, looked
    up by name, for the Summary PDF's instructor portrait."""
    name = (name or "").strip().lower()
    if not name:
        return None
    for fid, fname, photo in database.load_faculty_list():
        if (fname or "").strip().lower() == name:
            return photo
    return None


def _slug_date(date_str):
    for fmt in ("%B %d, %Y",):
        try:
            return datetime.datetime.strptime(date_str, fmt).date().isoformat()
        except (TypeError, ValueError):
            pass
    return datetime.date.today().isoformat()


def _export_pdf(full):
    data = _report_source()
    if not data or not data[3]:
        return {"ok": False, "msg": "No session data to export yet."}
    info, counts, total, log, sid = data
    try:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", info.get("instructor") or "Report")
        kind = "Full" if full else "Summary"
        fname = f"VOCA_{kind}_{safe_name}_{datetime.date.today()}.pdf"
        path = os.path.join(REPORTS_DIR, fname)
        if full:
            pdf_export.export_full_pdf(info, counts, total, log, path)
        else:
            photo = _photo_for_instructor(info.get("instructor"))
            recording_name = f"VOCA_Session_{_slug_date(info.get('date',''))}_{(sid or 1):02d}.mp4"
            pdf_export.export_summary_pdf(info, counts, total, path,
                                           instructor_photo_path=photo,
                                           recording_filename=recording_name)
        _open_file(path)
        return {"ok": True, "path": path, "msg": f"PDF saved: {path}"}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


@eel.expose
def export_summary_report_pdf():
    return _export_pdf(full=False)


@eel.expose
def export_full_report_pdf():
    return _export_pdf(full=True)


# ---------------------------------------------------------------
# RECORDING  (Detector thread -> queue -> greenlet -> UI)
# ---------------------------------------------------------------

_lock = threading.RLock()


def _fresh_state():
    return {
        "running": False, "started": None, "detector": None, "queue": None,
        "counts": {k: 0 for k in ACT_LABELS}, "total": 0, "log": [],
        "current": "--", "fps": 0.0, "status": "", "error": "",
        "limit_sec": 0, "session_info": {},
        "last_elapsed": 0, "ended_reason": "", "saved_id": None,
        "feed_seen": False, "last_beat": 0.0, "last_push": 0.0,
    }


_rec = _fresh_state()


def _fmt(sec):
    sec = max(0, int(sec))
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


@eel.expose
def get_recording_status():
    with _lock:
        running = _rec["running"]
        elapsed = (time.time() - _rec["started"]) if (running and _rec.get("started")) else 0
        limit = _rec["limit_sec"]
        return {
            "running": running,
            "elapsed": elapsed,
            "limit_sec": limit,
            "remaining": max(0, limit - elapsed) if (running and limit) else None,
            "counts": dict(_rec["counts"]),
            "total": _rec["total"],
            "current_activity": _rec["current"],
            "fps": _rec["fps"],
            "status": _rec["status"],
            "log_entries": len(_rec["log"]),
            "last_elapsed": _rec["last_elapsed"],
            "ended_reason": _rec["ended_reason"],
            "error": _rec["error"],
            "saved_id": _rec["saved_id"],
            "session_info": dict(_rec.get("session_info", {})),
        }


@eel.expose
def feed_heartbeat():
    """livefeed.html pings this every second. If the window is closed
    with the X button, the pings stop and the session ends + saves."""
    with _lock:
        _rec["feed_seen"] = True
        _rec["last_beat"] = time.time()
    return True


@eel.expose
def start_recording():
    with _lock:
        if _rec["running"]:
            return {"ok": False, "msg": "Recording is already running."}

    try:
        from detector import Detector
    except Exception as e:
        return {"ok": False, "msg": f"Detector could not load: {e}"}

    s = _load_session()
    print(s)
    limit = s["limit_h"] * 3600 + s["limit_m"] * 60
    row = _active_faculty_row()
    fac_name = row[1] if row else None
    fac_photo = row[2] if row else None     # None = detect anyone in frame

    q = queue.Queue(maxsize=2)
    det = Detector(q, camera_source=_camera_source(), limit_sec=limit,
                   faculty_photo=fac_photo, faculty_name=fac_name, save_video=s.get("save_video", False))

    with _lock:
        _rec.update(_fresh_state())
        _rec.update(running=True, started=None, detector=det, queue=q,
                    limit_sec=limit, current="Starting...",
                    status="Starting...", session_info=s)
    det.start()
    eel.spawn(_consume)
    return {"ok": True}


@eel.expose
def stop_recording():
    _finish("user")
    return {"ok": True, "saved_id": _rec["saved_id"]}


def _consume():
    """Runs as a gevent greenlet: drains the detector queue."""
    while True:
        with _lock:
            if not _rec["running"]:
                return
            q = _rec["queue"]
        try:
            while True:
                if _handle(q.get_nowait()):
                    return
        except queue.Empty:
            pass

        with _lock:
            gone = (_rec["feed_seen"] and time.time() - _rec["last_beat"] > 6)
        if gone:
            _finish("feed_closed")
            return
        eel.sleep(0.03)


def _handle(msg):
    """Same rules as the old LiveFeedWindow._poll + DashboardApp._on_detection.
    Returns True when the session ended."""
    if "timeout" in msg:
        _finish("limit")
        return True
    if "error" in msg:
        with _lock:
            _rec["error"] = str(msg["error"])
        _finish("error")
        return True
    if "status" in msg:
        with _lock:
            _rec["status"] = msg["status"]
            if "Camera ready" in msg["status"] or "detecting" in msg["status"]:
                _rec["started"] = time.time()
        return False

    if "video_saved" in msg:
        with _lock:
            _rec["session_info"]["video_file"] = msg["video_saved"]
        return False

    activity = msg.get("activity", "Ambient / Idle")
    fps = msg.get("fps", 0.0)
    ts = msg.get("timestamp", "")
    frame = msg.get("frame")
    recordable = msg.get("recordable", True)

    with _lock:
        _rec["current"] = activity
        _rec["fps"] = fps
        _rec["status"] = ""
        # Only the Active faculty is ever counted / logged.
        if recordable:
            if activity in _rec["counts"]:
                _rec["counts"][activity] += 1
                _rec["total"] += 1
            if not _rec["log"] or _rec["log"][-1][1] != activity:
                _rec["log"].append((ts, activity))
        do_push = frame is not None and time.time() - _rec["last_push"] >= 0.033
        if do_push:
            _rec["last_push"] = time.time()

    if do_push:
        try:
            import cv2
            h, w = frame.shape[:2]
            if w > 720:
                frame = cv2.resize(frame, (720, int(h * 720 / w)))
            # Resize to prevent 1080p frames from choking the WebSocket
            h, w = frame.shape[:2]
            if w > 1280:
                scale = 1280 / w
                frame_sm = cv2.resize(frame, (1280, int(h * scale)))
            else:
                frame_sm = frame
            ok, buf = cv2.imencode(".jpg", frame_sm, [cv2.IMWRITE_JPEG_QUALITY, 50])
            if ok:
                uri = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
                eel.update_feed(uri, activity, fps)
        except Exception:
            pass
    return False


def _finish(reason):
    with _lock:
        if not _rec["running"]:
            return
        _rec["running"] = False
        elapsed = time.time() - _rec["started"] if _rec.get("started") else 0
        _rec["last_elapsed"] = elapsed
        _rec["ended_reason"] = reason
        det = _rec["detector"]
        q = _rec["queue"]

    if det:
        try:
            det.stop()
            det.join(timeout=3.0)  # Wait for the thread to release resources and push final messages
        except Exception:
            pass

    # Drain any remaining messages (especially video_saved)
    if q:
        while not q.empty():
            try:
                msg = q.get_nowait()
                _handle(msg)
            except queue.Empty:
                break

    with _lock:
        info = dict(_rec["session_info"])
        counts = dict(_rec["counts"])
        total = _rec["total"]
        log = list(_rec["log"])

    # Auto-save exactly like the old _on_feed_closed: only if something was logged.
    if log:
        try:
            info_to_save = {
                "instructor": info.get("instructor", ""),
                "subject": info.get("subject", ""),
                "section": info.get("section", ""),
                "room": info.get("room", ""),
                "date": info.get("date", ""),
                "semester": info.get("semester", ""),
                "school_year": info.get("school_year", ""),
                "duration": _fmt(elapsed),
                "video_file": info.get("video_file", "")
            }
            saved_id = database.save_session(info_to_save, counts, total, log)
            with _lock:
                _rec["saved_id"] = saved_id
        except Exception as e:
            print(f"[App] Auto-save error: {e}")

    try:
        eel.close_feed()
    except Exception:
        pass


def main():
    init_users()
    database.init_db()

    eel.init("web")
    eel.start("login.html", size=(1280, 760), block=True, mode="chrome")


if __name__ == "__main__":
    main()

@eel.expose
def open_video(filepath):
    import os, subprocess
    if os.path.exists(filepath):
        os.startfile(os.path.abspath(filepath))



@eel.expose
def get_video_thumbnail(filepath):
    import os, cv2, base64
    if not filepath or not os.path.exists(filepath):
        return None
    cap = cv2.VideoCapture(filepath)
    ret, frame = cap.read()
    cap.release()
    if ret:
        h, w = frame.shape[:2]
        if w > 320:
            frame = cv2.resize(frame, (320, int(h * 320 / w)))
        _, buf = cv2.imencode('.jpg', frame)
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode('ascii')
    return None
