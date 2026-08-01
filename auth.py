"""
User database + authentication for multi-user support.
SQLite-based, lightweight for Raspberry Pi.
"""

import sqlite3
import hashlib
import hmac
import secrets
import time
import re
from pathlib import Path
from functools import wraps

from flask import request, jsonify, session, g

DB_PATH = Path(__file__).parent / "data" / "users.db"
SECRET_KEY_FILE = Path(__file__).parent / "data" / ".secret_key"
PBKDF2_ITERATIONS = 100_000  # tuned for Pi (balances security vs. login time)

_USERNAME_RE = re.compile(r'^[a-z0-9._-]{3,32}$')


def init_db():
    """Create the users table if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            iterations INTEGER NOT NULL DEFAULT 100000,
            display_name TEXT DEFAULT '',
            created_at REAL DEFAULT 0,
            is_admin INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()

    # Create default admin if no users exist
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        admin_pw = secrets.token_urlsafe(12)
        _create_user(conn, "admin", "admin@local", admin_pw, "Administrator", is_admin=1)
        print(f"   ⚠️  Default admin created — password: {admin_pw}")
        print(f"   ⚠️  Please change this password immediately after first login!")

    conn.close()


def _hash_password(password: str, salt: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """PBKDF2-HMAC-SHA256 — resistant to GPU/ASIC brute-force."""
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations)
    return dk.hex()


def _verify_password(password: str, salt: str, expected_hash: str, iterations: int) -> bool:
    """Constant-time password verification."""
    computed = _hash_password(password, salt, iterations)
    return hmac.compare_digest(computed, expected_hash)


def _create_user(conn, username, email, password, display_name="", is_admin=0):
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)
    conn.execute(
        "INSERT INTO users (username, email, password_hash, salt, iterations, display_name, created_at, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (username, email, pw_hash, salt, PBKDF2_ITERATIONS, display_name, time.time(), is_admin)
    )
    conn.commit()


def get_db():
    """Get a DB connection for the current request."""
    if 'db' not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA busy_timeout=5000")
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def _get_or_create_secret_key() -> str:
    """Persist the Flask secret key so sessions survive restarts."""
    SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(key)
    SECRET_KEY_FILE.chmod(0o600)
    return key


def register_auth(app):
    """Register auth routes and teardown on the Flask app."""
    init_db()
    app.teardown_appcontext(close_db)
    app.secret_key = _get_or_create_secret_key()
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB upload limit

    @app.route("/api/auth/register", methods=["POST"])
    def auth_register():
        data = request.json or {}
        username = data.get("username", "").strip().lower()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        display_name = data.get("display_name", "").strip()

        if not username or not email or not password:
            return jsonify({"error": "Username, email and password are required"}), 400
        if not _USERNAME_RE.match(username):
            return jsonify({"error": "Username must be 3-32 chars: letters, digits, . _ -"}), 400
        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        if len(email) > 254 or '@' not in email:
            return jsonify({"error": "Invalid email address"}), 400

        conn = get_db()
        try:
            _create_user(conn, username, email, password, display_name or username)
        except sqlite3.IntegrityError:
            return jsonify({"error": "Username or email already exists"}), 409

        user_id = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"]
        session["user_id"] = user_id
        session["username"] = username
        return jsonify({"status": "ok", "message": "Account created", "username": username})

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        data = request.json or {}
        username = data.get("username", "").strip().lower()
        password = data.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?", (username, username)
        ).fetchone()

        # Generic error to prevent user enumeration (H5)
        GENERIC_ERROR = "Invalid username or password"

        if not user:
            return jsonify({"error": GENERIC_ERROR}), 401

        if not _verify_password(password, user["salt"], user["password_hash"], user["iterations"]):
            return jsonify({"error": GENERIC_ERROR}), 401

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["is_admin"] = user["is_admin"]
        return jsonify({
            "status": "ok",
            "username": user["username"],
            "display_name": user["display_name"] or user["username"],
            "is_admin": bool(user["is_admin"])
        })

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        session.clear()
        return jsonify({"status": "ok", "message": "Logged out"})

    @app.route("/api/auth/me")
    def auth_me():
        if "user_id" not in session:
            return jsonify({"authenticated": False})
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not user:
            session.clear()
            return jsonify({"authenticated": False})
        return jsonify({
            "authenticated": True,
            "username": user["username"],
            "display_name": user["display_name"] or user["username"],
            "is_admin": bool(user["is_admin"])
        })

    @app.route("/api/auth/change-password", methods=["POST"])
    @login_required
    def auth_change_password():
        data = request.json or {}
        old_password = data.get("old_password", "")
        new_password = data.get("new_password", "")
        if len(new_password) < 8:
            return jsonify({"error": "New password must be at least 8 characters"}), 400

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not _verify_password(old_password, user["salt"], user["password_hash"], user["iterations"]):
            return jsonify({"error": "Current password incorrect"}), 401

        salt = secrets.token_hex(16)
        pw_hash = _hash_password(new_password, salt)
        conn.execute("UPDATE users SET password_hash = ?, salt = ?, iterations = ? WHERE id = ?",
                     (pw_hash, salt, PBKDF2_ITERATIONS, session["user_id"]))
        conn.commit()
        return jsonify({"status": "ok", "message": "Password changed"})

    @app.route("/api/auth/delete-account", methods=["POST"])
    @login_required
    def auth_delete_account():
        """Permanently delete the current user's account and ALL associated data."""
        data = request.json or {}
        confirm_password = data.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

        if not user:
            session.clear()
            return jsonify({"error": "Account not found"}), 404

        if not _verify_password(confirm_password, user["salt"], user["password_hash"], user["iterations"]):
            return jsonify({"error": "Password incorrect — account not deleted"}), 401

        if user["is_admin"]:
            admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]
            if admin_count <= 1:
                return jsonify({"error": "Cannot delete the last admin account"}), 403

        uid = session["user_id"]
        username = user["username"]

        # 1. Delete user's data directory
        user_dir = Path(__file__).parent / "data" / "users" / str(uid)
        if user_dir.exists():
            import shutil
            shutil.rmtree(user_dir)

        # 2. Delete user settings from database
        conn.execute("DELETE FROM user_settings WHERE user_id = ?", (uid,))
        # 3. Delete the user record
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
        # 4. Clear session
        session.clear()

        return jsonify({"status": "ok", "message": f"Account '{username}' and all associated data permanently deleted"})


# ─── Helpers ─────────────────────────────────────────────────────

def login_required(f):
    """Decorator: redirect to login if not authenticated or user no longer exists."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required", "redirect": "/login"}), 401
        if not user_exists(session["user_id"]):
            session.clear()
            return jsonify({"error": "Account no longer exists", "redirect": "/login"}), 401
        return f(*args, **kwargs)
    return decorated_function


def get_current_user_id() -> int:
    return session.get("user_id")


def get_current_username() -> str:
    return session.get("username", "guest")


def get_user_data_dir(user_id: int) -> Path:
    d = Path(__file__).parent / "data" / "users" / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_exists(user_id: int) -> bool:
    conn = get_db()
    return conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is not None


def get_setting(key: str, default=None):
    uid = get_current_user_id()
    if uid is None:
        return default
    conn = get_db()
    row = conn.execute("SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (uid, key)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    uid = get_current_user_id()
    if uid is None:
        return
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
        (uid, key, str(value))
    )
    conn.commit()
