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

# Allow OAuth2 over plain HTTP (the dashboard runs locally on http://)
# Without this, oauthlib raises InsecureTransportError
import os
os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

# Apply VW auth patch if the connector is installed
try:
    from scripts.patch_vw_auth import main as patch_vw
    patch_vw()
except Exception:
    pass  # No patch needed or connector not installed

from flask import Flask
from config import DATA_DIR, get_pi_model
from excel_parser import parse_excel_to_records
from auth import register_auth, init_db
from data_utils import merge_and_save_records

app = Flask(__name__)

# Prevent browser caching of HTML pages (ensures latest version is served)
@app.after_request
def add_no_cache_headers(response):
    if 'text/html' in response.headers.get('Content-Type', ''):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

from routes.core import register as register_core
from routes.abrp import register as register_abrp
from routes.connectors import register as register_connectors
from routes.locales import register as register_locales
from routes.vehicles import register as register_vehicles
from auth import register_auth, init_db

register_auth(app)
register_core(app)
register_abrp(app)
register_connectors(app)
register_locales(app)
register_vehicles(app)


def startup_import():
    """
    Auto-import Excel files found in data/ on startup.
    Assigned to the admin user (user ID 1).
    """
    excel_files = list(DATA_DIR.glob("*.xlsx"))
    if not excel_files:
        return 0

    init_db()
    conn = sqlite3.connect(str(DATA_DIR / "evdashboard.db"))
    admin = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    conn.close()
    if not admin:
        return 0

    admin_uid = admin[0]
    admin_dir = DATA_DIR / "users" / str(admin_uid)
    admin_dir.mkdir(parents=True, exist_ok=True)

    print(f"   Found {len(excel_files)} Excel file(s) in shared data/, importing to admin user...")
    from db import import_excel
    total_imported = 0
    for ef in excel_files:
        result = import_excel(admin_uid, ef, source_name=ef.name)
        total_imported += result["imported"]
        print(f"   → {ef.name}: {result['imported']} new, {result['duplicates']} dup")
        dest = admin_dir / ef.name
        if not dest.exists():
            ef.rename(dest)

    if total_imported > 0:
        print(f"   ✅ {total_imported} records imported for admin user")
    return total_imported


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"🚗 EV Dashboard starting on http://{host}:{port}")
    print(f"   Pi: {get_pi_model()}")
    print(f"   Data: {DATA_DIR}")
    init_db()
    startup_import()

    # Auto-backup: create weekly backup if last one is >7 days old
    try:
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        import time as _bt
        backups = sorted(backup_dir.glob("evdashboard-backup-*.db"))
        need_backup = True
        if backups:
            age_days = (_bt.time() - backups[-1].stat().st_mtime) / 86400
            if age_days < 7:
                need_backup = False
        if need_backup:
            from datetime import datetime as _bdt
            bname = f"evdashboard-backup-{_bdt.now().strftime('%Y%m%d-%H%M%S')}.db"
            bpath = backup_dir / bname
            _src = sqlite3.connect(str(DATA_DIR / "evdashboard.db"))
            _dst = sqlite3.connect(str(bpath))
            _src.backup(_dst)
            _dst.close()
            _src.close()
            # Keep only 3 most recent
            for old in sorted(backup_dir.glob("evdashboard-backup-*.db"))[:-3]:
                old.unlink(missing_ok=True)
            print(f"   ✅ Auto-backup created (weekly): {bname}")
    except Exception as e:
        print(f"   ⚠️ Auto-backup failed: {e}")

    app.run(host=host, port=port, debug=False)
