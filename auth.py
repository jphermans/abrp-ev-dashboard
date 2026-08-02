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
    """Create the users table if it doesn't exist. Thread/process safe with retry."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Retry loop: handles concurrent init from multiple gunicorn workers
    for attempt in range(5):
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("PRAGMA journal_mode=WAL")
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 4:
                import time as _time
                _time.sleep(0.5 * (attempt + 1))
                continue
            raise
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
    # Migration: add must_change_password column for existing databases
    try:
        conn.execute("SELECT must_change_password FROM users LIMIT 1")
    except sqlite3.OperationalError:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")
            print("   DB migrated: added must_change_password column")
        except sqlite3.OperationalError:
            pass  # Another worker already added it
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    # Migration: add is_fleet_manager column
    try:
        conn.execute("SELECT is_fleet_manager FROM users LIMIT 1")
    except sqlite3.OperationalError:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN is_fleet_manager INTEGER DEFAULT 0")
            print("   DB migrated: added is_fleet_manager column")
        except sqlite3.OperationalError:
            pass  # Another worker already added it
    # Vehicles table — supports multiple vehicles per user
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT 'My Vehicle',
            vin TEXT,
            brand TEXT,
            model TEXT,
            license_plate TEXT,
            connector_brand TEXT,
            created_at REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()

    # Create default admin if no users exist
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        try:
            admin_pw = "admin123"  # Fixed default — forced to change on first login
            _create_user(conn, "admin", "admin@local", admin_pw, "Administrator", is_admin=1)
            conn.execute("UPDATE users SET must_change_password = 1 WHERE username = 'admin'")
            conn.commit()
            print(f"   Default admin created — password: {admin_pw}")
            print(f"   You will be forced to change this password on first login!")
        except sqlite3.IntegrityError:
            pass  # Another worker already created the admin

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
        g.db = sqlite3.connect(str(DB_PATH), timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA busy_timeout=10000")
        g.db.execute("PRAGMA journal_mode=WAL")
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
    app.config['SESSION_COOKIE_PERMANENT'] = False  # Session expires when browser closes

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
        must_change = bool(user["must_change_password"]) if "must_change_password" in user.keys() else False
        fleet_mgr = bool(user["is_fleet_manager"]) if "is_fleet_manager" in user.keys() else False
        return jsonify({
            "status": "ok",
            "username": user["username"],
            "display_name": user["display_name"] or user["username"],
            "is_admin": bool(user["is_admin"]),
            "must_change_password": must_change,
            "is_fleet_manager": fleet_mgr
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
        must_change = bool(user["must_change_password"]) if "must_change_password" in user.keys() else False
        fleet_mgr = bool(user["is_fleet_manager"]) if "is_fleet_manager" in user.keys() else False
        return jsonify({
            "authenticated": True,
            "username": user["username"],
            "display_name": user["display_name"] or user["username"],
            "is_admin": bool(user["is_admin"]),
            "must_change_password": must_change,
            "is_fleet_manager": fleet_mgr
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
        conn.execute("UPDATE users SET password_hash = ?, salt = ?, iterations = ?, must_change_password = 0 WHERE id = ?",
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


# ─── Vehicle Management ──────────────────────────────────────────

def get_vehicle_data_dir(user_id: int, vehicle_id: int) -> Path:
    """Get the per-vehicle data directory."""
    d = Path(__file__).parent / "data" / "users" / str(user_id) / "vehicles" / str(vehicle_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_user_vehicles(user_id: int) -> list:
    """Get all vehicles for a user."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM vehicles WHERE user_id = ? ORDER BY created_at", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_vehicle_by_id(vehicle_id: int, user_id: int = None) -> dict:
    """Get a vehicle by ID. If user_id is given, verify ownership."""
    conn = get_db()
    if user_id is not None:
        row = conn.execute("SELECT * FROM vehicles WHERE id = ? AND user_id = ?", (vehicle_id, user_id)).fetchone()
    else:
        row = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    return dict(row) if row else None


def create_vehicle(user_id: int, name: str, brand: str = None, model: str = None,
                   vin: str = None, license_plate: str = None, connector_brand: str = None) -> int:
    """Create a new vehicle for a user. Returns the vehicle ID."""
    import time as _time
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO vehicles (user_id, name, vin, brand, model, license_plate, connector_brand, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, name, vin, brand, model, license_plate, connector_brand, _time.time())
    )
    conn.commit()
    vid = cursor.lastrowid
    # Create the vehicle data directory
    get_vehicle_data_dir(user_id, vid)
    return vid


def delete_vehicle(vehicle_id: int, user_id: int):
    """Delete a vehicle and its data directory."""
    import shutil
    conn = get_db()
    conn.execute("DELETE FROM vehicles WHERE id = ? AND user_id = ?", (vehicle_id, user_id))
    conn.commit()
    vdir = Path(__file__).parent / "data" / "users" / str(user_id) / "vehicles" / str(vehicle_id)
    if vdir.exists():
        shutil.rmtree(vdir)


def is_fleet_manager() -> bool:
    """Check if the current user is a fleet manager."""
    uid = get_current_user_id()
    if uid is None:
        return False
    conn = get_db()
    row = conn.execute("SELECT is_fleet_manager FROM users WHERE id = ?", (uid,)).fetchone()
    return bool(row["is_fleet_manager"]) if row else False
