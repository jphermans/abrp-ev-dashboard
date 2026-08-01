#!/usr/bin/env python3
"""
ABRP EV Dashboard Server — entry point
Modular design: config, excel_parser, connectors/, routes/
Designed for Raspberry Pi 4/5.
"""

import os
import json
import sqlite3
import sys
from pathlib import Path

# Ensure local modules are importable
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
from config import DATA_DIR, get_pi_model
from excel_parser import parse_excel_to_records
from auth import register_auth, init_db

app = Flask(__name__)

# Register all route modules
from routes.core import register as register_core
from routes.abrp import register as register_abrp
from routes.connectors import register as register_connectors
from routes.locales import register as register_locales

register_auth(app)
register_core(app)
register_abrp(app)
register_connectors(app)
register_locales(app)


def startup_import():
    """
    Auto-import Excel files found in data/ on startup.
    In multi-user mode, these are assigned to the admin user (user ID 1).
    This is a convenience so that files placed in data/ before first boot
    are not invisible.
    """
    excel_files = list(DATA_DIR.glob("*.xlsx"))
    if not excel_files:
        return 0

    # Ensure the database exists and get admin user dir
    init_db()
    db_path = DATA_DIR / "users.db"
    conn = sqlite3.connect(str(db_path))
    admin = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    conn.close()
    if not admin:
        return 0

    admin_dir = DATA_DIR / "users" / str(admin[0])
    admin_dir.mkdir(parents=True, exist_ok=True)

    print(f"   Found {len(excel_files)} Excel file(s) in shared data/, importing to admin user...")
    all_records = []
    for ef in excel_files:
        recs = parse_excel_to_records(ef)
        all_records.extend(recs)
        print(f"   → {ef.name}: {len(recs)} records")
        # Move file into admin's directory so it's owned by admin
        dest = admin_dir / ef.name
        if not dest.exists():
            ef.rename(dest)

    if not all_records:
        return 0

    seen = set()
    deduped = []
    for r in all_records:
        k = f"{r['datetime']}|{r['activity']}"
        if k not in seen:
            seen.add(k)
            deduped.append(r)
    deduped.sort(key=lambda x: x["datetime"])

    # Merge with any existing admin data
    json_file = admin_dir / "activities.json"
    existing = []
    if json_file.exists():
        with open(json_file) as f:
            existing = json.load(f)
    existing.extend(deduped)
    seen2 = set()
    final = []
    for r in existing:
        k = f"{r['datetime']}|{r['activity']}"
        if k not in seen2:
            seen2.add(k)
            final.append(r)
    final.sort(key=lambda x: x["datetime"])
    with open(json_file, "w") as f:
        json.dump(final, f, ensure_ascii=False)
    print(f"   ✅ {len(final)} records loaded for admin user")
    return len(final)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"🚗 ABRP Dashboard starting on http://{host}:{port}")
    print(f"   Pi: {get_pi_model()}")
    print(f"   Data: {DATA_DIR}")
    init_db()
    print(f"   Auth: multi-user enabled")
    startup_import()
    app.run(host=host, port=port, debug=False)
