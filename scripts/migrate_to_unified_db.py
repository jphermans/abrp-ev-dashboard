"""
Migrate old split databases (users.db + activities.db per user/vehicle)
into the unified evdashboard.db.

Run once after upgrading to v3.0.0.
Usage: python3 scripts/migrate_to_unified_db.py
"""

import sqlite3
import shutil
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
UNIFIED_DB = DATA_DIR / "evdashboard.db"
OLD_USERS_DB = DATA_DIR / "users.db"


def migrate():
    if not OLD_USERS_DB.exists() and not UNIFIED_DB.exists():
        print("No old databases found. Fresh install — nothing to migrate.")
        return

    # If unified DB already exists, skip
    if UNIFIED_DB.exists():
        # Check if it already has data
        conn = sqlite3.connect(str(UNIFIED_DB))
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count > 0:
            print(f"Unified DB already exists with {count} users. Skipping migration.")
            conn.close()
            return
        conn.close()

    print("Starting migration to unified database...")

    # Step 1: Copy users.db → evdashboard.db (schema + data)
    if OLD_USERS_DB.exists():
        print(f"  Copying {OLD_USERS_DB.name} → {UNIFIED_DB.name}")
        # Ensure unified DB has the new schema
        from db import init_db
        init_db()

        old_conn = sqlite3.connect(str(OLD_USERS_DB))
        old_conn.row_factory = sqlite3.Row

        # Copy users
        users = old_conn.execute("SELECT * FROM users").fetchall()
        new_conn = sqlite3.connect(str(UNIFIED_DB))
        for u in users:
            new_conn.execute("""
                INSERT OR REPLACE INTO users (id, username, email, password_hash, salt, iterations,
                    display_name, created_at, is_admin, must_change_password, is_fleet_manager)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (u["id"], u["username"], u["email"], u["password_hash"], u["salt"],
                  u["iterations"], u["display_name"], u["created_at"], u["is_admin"],
                  u["must_change_password"] if "must_change_password" in u.keys() else 0,
                  u["is_fleet_manager"] if "is_fleet_manager" in u.keys() else 0))

        # Copy user_settings
        settings = old_conn.execute("SELECT * FROM user_settings").fetchall()
        for s in settings:
            new_conn.execute("INSERT OR REPLACE INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
                             (s["user_id"], s["key"], s["value"]))

        # Copy vehicles
        vehicles = old_conn.execute("SELECT * FROM vehicles").fetchall()
        for v in vehicles:
            new_conn.execute("""
                INSERT OR REPLACE INTO vehicles (id, user_id, name, vin, brand, model,
                    license_plate, connector_brand, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (v["id"], v["user_id"], v["name"], v["vin"], v["brand"], v["model"],
                  v["license_plate"], v["connector_brand"], v["created_at"]))

        new_conn.commit()

        user_count = new_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        veh_count = new_conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
        print(f"  ✅ Copied {user_count} users, {veh_count} vehicles, {len(settings)} settings")

        old_conn.close()
        new_conn.close()

    # Step 2: Import per-user activities
    users_dir = DATA_DIR / "users"
    if users_dir.exists():
        new_conn = sqlite3.connect(str(UNIFIED_DB))
        total_acts = 0
        for user_dir in users_dir.iterdir():
            if not user_dir.is_dir():
                continue
            uid_str = user_dir.name
            try:
                uid = int(uid_str)
            except ValueError:
                continue

            # Legacy activities.db (no vehicle)
            old_acts = user_dir / "activities.db"
            if old_acts.exists():
                ac = sqlite3.connect(str(old_acts))
                ac.row_factory = sqlite3.Row
                rows = ac.execute("SELECT * FROM activities").fetchall()
                for r in rows:
                    try:
                        new_conn.execute("""
                            INSERT OR IGNORE INTO activities (
                                user_id, vehicle_id, date, time, datetime, weekday, activity,
                                duration, distance_km, distance_mi, start_soc, end_soc,
                                energy_kwh, start_odo_mi, end_odo_mi, vehicle,
                                charge_provider, charge_location, source_file, dedup_hash
                            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (uid, r["date"], r["time"], r["datetime"], r["weekday"],
                              r["activity"], r["duration"], r["distance_km"], r["distance_mi"],
                              r["start_soc"], r["end_soc"], r["energy_kwh"], r["start_odo_mi"],
                              r["end_odo_mi"], r["vehicle"], r["charge_provider"],
                              r["charge_location"], r["source_file"], r["dedup_hash"]))
                        total_acts += 1
                    except sqlite3.IntegrityError:
                        pass
                ac.close()
                print(f"  User {uid}: imported from activities.db")

            # Per-vehicle activities.db
            vehicles_dir = user_dir / "vehicles"
            if vehicles_dir.exists():
                for vdir in vehicles_dir.iterdir():
                    if not vdir.is_dir():
                        continue
                    vid_str = vdir.name
                    try:
                        vid = int(vid_str)
                    except ValueError:
                        continue
                    old_v_acts = vdir / "activities.db"
                    if old_v_acts.exists():
                        ac = sqlite3.connect(str(old_v_acts))
                        ac.row_factory = sqlite3.Row
                        rows = ac.execute("SELECT * FROM activities").fetchall()
                        v_count = 0
                        for r in rows:
                            try:
                                new_conn.execute("""
                                    INSERT OR IGNORE INTO activities (
                                        user_id, vehicle_id, date, time, datetime, weekday, activity,
                                        duration, distance_km, distance_mi, start_soc, end_soc,
                                        energy_kwh, start_odo_mi, end_odo_mi, vehicle,
                                        charge_provider, charge_location, source_file, dedup_hash
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (uid, vid, r["date"], r["time"], r["datetime"], r["weekday"],
                                      r["activity"], r["duration"], r["distance_km"], r["distance_mi"],
                                      r["start_soc"], r["end_soc"], r["energy_kwh"], r["start_odo_mi"],
                                      r["end_odo_mi"], r["vehicle"], r["charge_provider"],
                                      r["charge_location"], r["source_file"], r["dedup_hash"]))
                                v_count += 1
                                total_acts += 1
                            except sqlite3.IntegrityError:
                                pass
                        ac.close()
                        print(f"  User {uid}, Vehicle {vid}: imported {v_count} activities")

        new_conn.commit()
        new_conn.close()
        print(f"  ✅ Total activities imported: {total_acts}")

    # Step 3: Rename old DBs
    if OLD_USERS_DB.exists():
        backup = OLD_USERS_DB.with_suffix(".db.bak")
        OLD_USERS_DB.rename(backup)
        print(f"  Renamed {OLD_USERS_DB.name} → {backup.name}")

    # Rename old per-user .db files
    if users_dir.exists():
        for user_dir in users_dir.iterdir():
            if not user_dir.is_dir():
                continue
            old = user_dir / "activities.db"
            if old.exists():
                old.rename(old.with_suffix(".db.bak"))
            vd = user_dir / "vehicles"
            if vd.exists():
                for vdir in vd.iterdir():
                    old = vdir / "activities.db"
                    if old.exists():
                        old.rename(old.with_suffix(".db.bak"))

    print("\n✅ Migration complete!")
    print(f"   Unified DB: {UNIFIED_DB}")
    print("   Old DBs renamed to .bak")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    migrate()
