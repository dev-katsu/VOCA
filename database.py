"""
VOCA - Database Layer
File: database.py

Shares the same voca.db file as login.py (same folder, same filename),
so users/faculty/sessions all live together in one SQLite database.
"""

import sqlite3
import os
import json
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voca.db")


# -----------------------------------------
# DB INIT
# -----------------------------------------

def init_db():
    """Create all tables used by the app (faculty + sessions) if missing."""
    init_faculty_table()
    init_sessions_table()
    init_settings_table()


def init_settings_table():
    """Small key-value table for simple app state, e.g. which faculty
    member is currently marked Active (so it persists across restarts)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_setting(key, default=None):
    init_settings_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM app_settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key, value):
    init_settings_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)",
              (key, str(value)))
    conn.commit()
    conn.close()


def init_faculty_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS faculty (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT UNIQUE,
            photo    TEXT
        )
    """)
    conn.commit()
    conn.close()


def init_sessions_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instructor TEXT,
            subject TEXT,
            section TEXT,
            room TEXT,
            date TEXT,
            semester TEXT,
            school_year TEXT,
            duration TEXT,
            activity_counts TEXT,
            total_frames INTEGER,
            session_log TEXT,
            created_at TEXT
        )
    """)
    try:
        c.execute("ALTER TABLE sessions ADD COLUMN video_file TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


# -----------------------------------------
# FACULTY FACE FUNCTIONS
# -----------------------------------------

def save_faculty(name, photo_path):
    """Register / update a faculty member's reference photo."""
    init_faculty_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Upsert keeps the same id, so the Active faculty setting stays valid.
    c.execute("""INSERT INTO faculty (name, photo) VALUES (?,?)
                 ON CONFLICT(name) DO UPDATE SET photo=excluded.photo""",
              (name, photo_path))
    conn.commit()
    conn.close()


# kept as an alias so any older code calling the original name still works
def save_faculty_face(name, photo_path):
    save_faculty(name, photo_path)


def delete_faculty(faculty_id):
    init_faculty_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM faculty WHERE id=?", (faculty_id,))
    conn.commit()
    conn.close()


def load_faculty_list():
    init_faculty_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, photo FROM faculty ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return rows


def load_faculty_photos():
    """Returns list of (name, photo_path) for detector use."""
    init_faculty_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, photo FROM faculty WHERE photo IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return rows


# -----------------------------------------
# SESSION FUNCTIONS
# -----------------------------------------

def save_session(session_info, activity_counts, total_frames, session_log):
    """Save a completed/ongoing monitoring session. Returns the new row id."""
    init_sessions_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    sec_str = session_info.get("section", "")

    c.execute("""
        INSERT INTO sessions
            (instructor, subject, section, room, date, semester, school_year,
             duration, activity_counts, total_frames, session_log, created_at, video_file)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        session_info.get("instructor", ""),
        session_info.get("subject", ""),
        sec_str,
        session_info.get("room", ""),
        session_info.get("date", ""),
        session_info.get("semester", ""),
        session_info.get("school_year", ""),
        session_info.get("duration", ""),
        json.dumps(activity_counts),
        total_frames,
        json.dumps(session_log),
        datetime.datetime.now().isoformat(),
        session_info.get("video_file", "")
    ))
    rowid = c.lastrowid
    conn.commit()
    conn.close()
    return rowid


def load_sessions():
    """Returns all saved sessions, most recent first."""
    init_sessions_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, instructor, subject, section, room, date, semester,
               school_year, duration, activity_counts, total_frames,
               session_log, created_at, video_file
        FROM sessions ORDER BY id DESC
    """)
    rows = c.fetchall()
    conn.close()
    return rows