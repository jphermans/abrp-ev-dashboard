"""
ABRP EV Dashboard — SQLite data layer.
Converts Excel exports to a normalized SQLite database with deduplication.
This is the single source of truth for all activity data.
"""

import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from excel_parser import parse_excel_to_records


SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    -- Dedup key: hash of datetime + activity + key numeric fields
    dedup_hash TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date);
CREATE INDEX IF NOT EXISTS idx_activities_activity ON activities(activity);
CREATE INDEX IF NOT EXISTS idx_activities_provider ON activities(charge_provider);
CREATE INDEX IF NOT EXISTS idx_activities_datetime ON activities(datetime);
"""


def get_db_path(data_dir: Path) -> Path:
    """Get the SQLite database path for a data directory."""
    return data_dir / "activities.db"


def init_db(db_path: Path):
    """Initialize the SQLite database with the schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _compute_dedup_hash(record: dict) -> str:
    """Compute a unique hash for deduplication."""
    key_parts = [
        record.get('datetime', ''),
        record.get('activity', ''),
        str(record.get('distance_km', '') or ''),
        str(record.get('energy_kwh', '') or ''),
    ]
    raw = '|'.join(key_parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def import_excel_to_db(db_path: Path, excel_path: Path, source_name: str = None) -> dict:
    """
    Parse an Excel file and import its records into the SQLite DB.
    Returns {"imported": N, "duplicates": M, "total": T}.
    """
    if source_name is None:
        source_name = excel_path.name

    # Parse the Excel
    records = parse_excel_to_records(excel_path)
    if not records:
        return {"imported": 0, "duplicates": 0, "total": 0}

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")

    imported = 0
    duplicates = 0

    for r in records:
        dedup_hash = _compute_dedup_hash(r)
        try:
            conn.execute("""
                INSERT INTO activities (
                    date, time, datetime, weekday, activity, duration,
                    distance_km, distance_mi, start_soc, end_soc,
                    energy_kwh, start_odo_mi, end_odo_mi, vehicle,
                    charge_provider, charge_location, source_file, dedup_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.get('date', ''),
                r.get('time', ''),
                r.get('datetime', ''),
                r.get('weekday', ''),
                r.get('activity', ''),
                r.get('duration', ''),
                r.get('distance_km'),
                r.get('distance_mi'),
                r.get('start_soc'),
                r.get('end_soc'),
                r.get('energy_kwh'),
                r.get('start_odo_mi'),
                r.get('end_odo_mi'),
                r.get('vehicle', 'EV'),
                r.get('charge_provider'),
                r.get('charge_location'),
                source_name,
                dedup_hash,
            ))
            imported += 1
        except sqlite3.IntegrityError:
            # Duplicate — dedup_hash already exists
            duplicates += 1

    conn.commit()

    # Get total count
    total = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    conn.close()

    return {"imported": imported, "duplicates": duplicates, "total": total}


def import_all_excels(db_path: Path, data_dir: Path) -> dict:
    """
    Import all Excel files from a directory into the DB.
    Skips files already imported (dedup via hash).
    """
    init_db(db_path)

    excel_files = sorted(data_dir.glob("*.xlsx"))
    if not excel_files:
        return {"files": 0, "imported": 0, "duplicates": 0, "total": 0}

    total_imported = 0
    total_dups = 0
    files_processed = 0

    for ef in excel_files:
        result = import_excel_to_db(db_path, ef, ef.name)
        total_imported += result["imported"]
        total_dups += result["duplicates"]
        if result["imported"] > 0 or result["duplicates"] > 0:
            files_processed += 1

    conn = sqlite3.connect(str(db_path))
    final_total = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    conn.close()

    return {
        "files": files_processed,
        "imported": total_imported,
        "duplicates": total_dups,
        "total": final_total,
    }


def get_all_activities(db_path: Path, date_from: str = None, date_to: str = None) -> list:
    """Get all activities from the DB, optionally filtered by date range."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if date_from and date_to:
        rows = conn.execute(
            "SELECT * FROM activities WHERE date >= ? AND date <= ? ORDER BY datetime",
            (date_from, date_to)
        ).fetchall()
    elif date_from:
        rows = conn.execute(
            "SELECT * FROM activities WHERE date >= ? ORDER BY datetime",
            (date_from,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM activities ORDER BY datetime"
        ).fetchall()

    result = [dict(r) for r in rows]
    conn.close()
    return result


def get_charge_summary(db_path: Path) -> list:
    """Get charge provider summary from the DB."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT 
            COALESCE(charge_provider, 'Unknown') as provider,
            COUNT(*) as sessions,
            ROUND(SUM(energy_kwh), 1) as total_kwh,
            ROUND(AVG(energy_kwh), 1) as avg_kwh,
            MAX(date) as last_visit
        FROM activities 
        WHERE activity = 'Laad op'
        GROUP BY COALESCE(charge_provider, 'Unknown')
        ORDER BY total_kwh DESC
    """).fetchall()

    result = [dict(r) for r in rows]
    conn.close()
    return result


def get_kpi_summary(db_path: Path, date_from: str = None, date_to: str = None) -> dict:
    """Get KPI summary from the DB."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    where = ""
    params = ()
    if date_from and date_to:
        where = "WHERE date >= ? AND date <= ?"
        params = (date_from, date_to)
    elif date_from:
        where = "WHERE date >= ?"
        params = (date_from,)

    row = conn.execute(f"""
        SELECT
            COUNT(CASE WHEN activity='Rijd' THEN 1 END) as drive_count,
            COUNT(CASE WHEN activity='Laad op' THEN 1 END) as charge_count,
            ROUND(COALESCE(SUM(CASE WHEN activity='Rijd' THEN distance_km END), 0)) as total_km,
            ROUND(COALESCE(SUM(CASE WHEN activity='Laad op' THEN energy_kwh END), 0), 1) as total_kwh,
            COUNT(DISTINCT date) as active_days,
            ROUND(MAX(CASE WHEN end_odo_mi IS NOT NULL THEN end_odo_mi * 1.609344 END)) as odometer_km,
            ROUND(MIN(CASE WHEN start_odo_mi IS NOT NULL AND start_odo_mi > 0 THEN start_odo_mi * 1.609344 END)) as odometer_start_km,
            ROUND(MAX(CASE WHEN activity='Rijd' THEN distance_km END)) as longest_trip
        FROM activities
        {where}
    """, params).fetchone()

    result = dict(row) if row else {}
    conn.close()
    return result


def update_charge_provider(db_path: Path, activity_id: int, provider: str):
    """Update the charge_provider for a specific activity."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE activities SET charge_provider = ? WHERE id = ?",
        (provider, activity_id)
    )
    conn.commit()
    conn.close()


def delete_all_activities(db_path: Path):
    """Delete all activities from the DB."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM activities")
    conn.commit()
    conn.close()
