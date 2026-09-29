"""
VOCA - Login Backend
File: login.py

Pure authentication logic — no UI here anymore. This is called by
app.py (Eel) which exposes it to the HTML/JS frontend. The database
schema, password hashing, and validation rules are UNCHANGED from
the original Tkinter version.

FIX: every function now closes its sqlite3 connection in a `finally`
block, so a failed INSERT (e.g. duplicate Faculty ID) can no longer
leave a connection open and holding a lock on voca.db. A busy_timeout
is also set so SQLite waits a moment instead of immediately raising
"database is locked" if another connection briefly holds the file.
"""

import sqlite3, hashlib, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voca.db")


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _hp(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def init_users():
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE, password TEXT,
            role TEXT, fullname TEXT
        )""")
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO users (username,password,role,fullname) VALUES (?,?,?,?)", [
                ("admin",      _hp("admin123"),    "Administrator", "Admin"),
                ("deanoffice", _hp("voca2026"),    "Dean",          "Dean Office"),
                ("dept_head",  _hp("monitor@2026"),"Department Head","Dept Head"),
            ])
        conn.commit()
    finally:
        conn.close()


def check_login(username, password):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("SELECT fullname, role FROM users WHERE username=? AND password=?",
                  (username.strip().lower(), _hp(password)))
        row = c.fetchone()
        return row
    finally:
        conn.close()


def register_user(username, password, fullname, role="Faculty"):
    """Create a new account. `username` is the faculty's login id
    (their Faculty ID). Same validation/hashing as the original app."""
    username = (username or "").strip().lower()
    fullname = (fullname or "").strip()

    if not username or not password or not fullname:
        return False, "Please fill in all fields."
    if len(username) < 4:
        return False, "Faculty ID must be at least 4 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    conn = _connect()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO users (username,password,role,fullname) VALUES (?,?,?,?)",
                  (username, _hp(password), role, fullname))
        conn.commit()
        return True, "Account created successfully."
    except sqlite3.IntegrityError:
        return False, "Faculty ID already registered."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()