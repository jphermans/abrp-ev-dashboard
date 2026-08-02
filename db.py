"""
EV Dashboard — Unified SQLite data layer.
Single database: data/evdashboard.db
Contains: users, user_settings, vehicles, activities, custom_providers.
"""

import sqlite3
import hashlib
import json
import time
from pathlib import Path
from excel_parser import parse_excel_to_records

# ── Single DB path ──────────────────────────────────────────────────
DB_PATH = Path(__file__).parent / "data" / "evdashboard.db"

SCHEMA = """
-- ── Users ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    iterations INTEGER NOT NULL DEFAULT 100000,
    display_name TEXT DEFAULT '',
    created_at REAL DEFAULT 0,
    is_admin INTEGER DEFAULT 0,
    must_change_password INTEGER DEFAULT 0,
    is_fleet_manager INTEGER DEFAULT 0
);

-- ── User Settings ───────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (user_id, key)
);

-- ── Vehicles ────────────────────────────────────────
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
);

-- ── Activities ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    vehicle_id INTEGER,
    date TEXT NOT NULL,
    time TEXT,
    datetime TEXT NOT NULL,
    weekday TEXT,
    activity TEXT NOT NULL,
    duration TEXT,
    distance_km REAL,
    distance_mi REAL,
    start_soc INTEGER,
    end_soc INTEGER,
    energy_kwh REAL,
    start_odo_mi REAL,
    end_odo_mi REAL,
    vehicle TEXT DEFAULT 'EV',
    charge_provider TEXT,
    charge_location TEXT,
    source_file TEXT,
    dedup_hash TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, vehicle_id, dedup_hash)
);

CREATE INDEX IF NOT EXISTS idx_activities_user ON activities(user_id);
CREATE INDEX IF NOT EXISTS idx_activities_vehicle ON activities(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date);
CREATE INDEX IF NOT EXISTS idx_activities_activity ON activities(activity);
CREATE INDEX IF NOT EXISTS idx_activities_provider ON activities(charge_provider);
CREATE INDEX IF NOT EXISTS idx_activities_datetime ON activities(datetime);

-- ── Custom Charge Providers (global, user_id=0) ─────
-- Stored in user_settings with user_id=0, key='custom_providers'
"""


def get_connection():
    """Get a SQLite connection with WAL mode and busy timeout."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    """Initialize the unified database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ── Activities ──────────────────────────────────────────────────────

def _compute_dedup_hash(record: dict) -> str:
    """Compute a unique hash for deduplication."""
    key_parts = [
        record.get('datetime', ''),
        record.get('activity', ''),
        str(record.get('distance_km', '') or ''),
        str(record.get('energy_kwh', '') or ''),
    ]
    return hashlib.sha256('|'.join(key_parts).encode()).hexdigest()[:32]


def import_excel(uid: int, excel_path: Path, vehicle_id: int = None, source_name: str = None) -> dict:
    """
    Parse an Excel file and import records into the unified DB.
    Returns {"imported": N, "duplicates": M, "total": T}.
    """
    if source_name is None:
        source_name = excel_path.name

    records = parse_excel_to_records(excel_path)
    if not records:
        return {"imported": 0, "duplicates": 0, "total": 0}

    conn = get_connection()
    imported = 0
    duplicates = 0

    for r in records:
        dedup_hash = _compute_dedup_hash(r)
        try:
            conn.execute("""
                INSERT INTO activities (
                    user_id, vehicle_id, date, time, datetime, weekday, activity, duration,
                    distance_km, distance_mi, start_soc, end_soc,
                    energy_kwh, start_odo_mi, end_odo_mi, vehicle,
                    charge_provider, charge_location, source_file, dedup_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uid, vehicle_id,
                r.get('date', ''), r.get('time', ''), r.get('datetime', ''),
                r.get('weekday', ''), r.get('activity', ''), r.get('duration', ''),
                r.get('distance_km'), r.get('distance_mi'),
                r.get('start_soc'), r.get('end_soc'),
                r.get('energy_kwh'), r.get('start_odo_mi'), r.get('end_odo_mi'),
                r.get('vehicle', 'EV'),
                r.get('charge_provider'), r.get('charge_location'),
                source_name, dedup_hash,
            ))
            imported += 1
        except sqlite3.IntegrityError:
            duplicates += 1

    conn.commit()
    total = conn.execute(
        "SELECT COUNT(*) FROM activities WHERE user_id = ? AND COALESCE(vehicle_id, -1) = COALESCE(?, -1)",
        (uid, vehicle_id)
    ).fetchone()[0]
    conn.close()

    return {"imported": imported, "duplicates": duplicates, "total": total}


def get_activities(uid: int, vehicle_id: int = None) -> list:
    """Get all activities for a user (optionally filtered by vehicle)."""
    conn = get_connection()
    if vehicle_id is not None:
        rows = conn.execute(
            "SELECT * FROM activities WHERE user_id = ? AND vehicle_id = ? ORDER BY datetime",
            (uid, vehicle_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM activities WHERE user_id = ? AND vehicle_id IS NULL ORDER BY datetime",
            (uid,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_charge_summary(uid: int, vehicle_id: int = None) -> list:
    """Get charge provider summary."""
    conn = get_connection()
    if vehicle_id is not None:
        rows = conn.execute("""
            SELECT COALESCE(charge_provider, 'Unknown') as provider,
                   COUNT(*) as sessions,
                   ROUND(SUM(energy_kwh), 1) as total_kwh,
                   ROUND(AVG(energy_kwh), 1) as avg_kwh,
                   MAX(date) as last_visit
            FROM activities
            WHERE user_id = ? AND vehicle_id = ? AND activity = 'Laad op'
            GROUP BY COALESCE(charge_provider, 'Unknown')
            ORDER BY total_kwh DESC
        """, (uid, vehicle_id)).fetchall()
    else:
        rows = conn.execute("""
            SELECT COALESCE(charge_provider, 'Unknown') as provider,
                   COUNT(*) as sessions,
                   ROUND(SUM(energy_kwh), 1) as total_kwh,
                   ROUND(AVG(energy_kwh), 1) as avg_kwh,
                   MAX(date) as last_visit
            FROM activities
            WHERE user_id = ? AND vehicle_id IS NULL AND activity = 'Laad op'
            GROUP BY COALESCE(charge_provider, 'Unknown')
            ORDER BY total_kwh DESC
        """, (uid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_charge_provider(activity_id: int, provider: str):
    """Update the charge_provider for a specific activity."""
    conn = get_connection()
    conn.execute("UPDATE activities SET charge_provider = ? WHERE id = ?", (provider, activity_id))
    conn.commit()
    conn.close()


def get_charge_locations(uid: int, vehicle_id: int = None) -> list:
    """Get all charge sessions with id, location, provider."""
    conn = get_connection()
    if vehicle_id is not None:
        rows = conn.execute("""
            SELECT id, date, charge_location, charge_provider, energy_kwh, duration
            FROM activities
            WHERE user_id = ? AND vehicle_id = ? AND activity = 'Laad op'
            ORDER BY date DESC
        """, (uid, vehicle_id)).fetchall()
    else:
        rows = conn.execute("""
            SELECT id, date, charge_location, charge_provider, energy_kwh, duration
            FROM activities
            WHERE user_id = ? AND vehicle_id IS NULL AND activity = 'Laad op'
            ORDER BY date DESC
        """, (uid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_activities(uid: int, vehicle_id: int = None):
    """Delete all activities for a user (optionally filtered by vehicle)."""
    conn = get_connection()
    if vehicle_id is not None:
        conn.execute("DELETE FROM activities WHERE user_id = ? AND vehicle_id = ?", (uid, vehicle_id))
    else:
        conn.execute("DELETE FROM activities WHERE user_id = ? AND vehicle_id IS NULL", (uid,))
    conn.commit()
    conn.close()


# ── Custom Providers ────────────────────────────────────────────────

def get_custom_providers() -> list:
    """Get global custom charge providers."""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = 0 AND key = 'custom_providers'"
    ).fetchone()
    conn.close()
    return json.loads(row["value"]) if row and row["value"] else []


def add_custom_provider(name: str) -> list:
    """Add a global custom charge provider. Returns the updated list."""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = 0 AND key = 'custom_providers'"
    ).fetchone()
    providers = json.loads(row["value"]) if row and row["value"] else []
    if name not in providers:
        providers.append(name)
        conn.execute(
            "INSERT OR REPLACE INTO user_settings (user_id, key, value) VALUES (0, 'custom_providers', ?)",
            (json.dumps(providers),)
        )
        conn.commit()
    conn.close()
    return providers


# ── KPI Summary ─────────────────────────────────────────────────────

def get_kpi_summary(uid: int, vehicle_id: int = None) -> dict:
    """Get KPI summary for a user/vehicle."""
    conn = get_connection()
    if vehicle_id is not None:
        row = conn.execute("""
            SELECT
                COUNT(CASE WHEN activity='Rijd' THEN 1 END) as drive_count,
                COUNT(CASE WHEN activity='Laad op' THEN 1 END) as charge_count,
                ROUND(COALESCE(SUM(CASE WHEN activity='Rijd' THEN distance_km END), 0)) as total_km,
                ROUND(COALESCE(SUM(CASE WHEN activity='Laad op' THEN energy_kwh END), 0), 1) as total_kwh,
                COUNT(DISTINCT date) as active_days,
                ROUND(MAX(CASE WHEN end_odo_mi IS NOT NULL THEN end_odo_mi * 1.609344 END)) as odometer_km,
                ROUND(MIN(CASE WHEN start_odo_mi IS NOT NULL AND start_odo_mi > 0 THEN start_odo_mi * 1.609344 END)) as odometer_start_km,
                ROUND(MAX(CASE WHEN activity='Rijd' THEN distance_km END)) as longest_trip
            FROM activities WHERE user_id = ? AND vehicle_id = ?
        """, (uid, vehicle_id)).fetchone()
    else:
        row = conn.execute("""
            SELECT
                COUNT(CASE WHEN activity='Rijd' THEN 1 END) as drive_count,
                COUNT(CASE WHEN activity='Laad op' THEN 1 END) as charge_count,
                ROUND(COALESCE(SUM(CASE WHEN activity='Rijd' THEN distance_km END), 0)) as total_km,
                ROUND(COALESCE(SUM(CASE WHEN activity='Laad op' THEN energy_kwh END), 0), 1) as total_kwh,
                COUNT(DISTINCT date) as active_days,
                ROUND(MAX(CASE WHEN end_odo_mi IS NOT NULL THEN end_odo_mi * 1.609344 END)) as odometer_km,
                ROUND(MIN(CASE WHEN start_odo_mi IS NOT NULL AND start_odo_mi > 0 THEN start_odo_mi * 1.609344 END)) as odometer_start_km,
                ROUND(MAX(CASE WHEN activity='Rijd' THEN distance_km END)) as longest_trip
            FROM activities WHERE user_id = ? AND vehicle_id IS NULL
        """, (uid,)).fetchone()
    conn.close()
    return dict(row) if row else {}
