"""Core routes: serve dashboard, data API, Excel upload, charge editor."""

import json
import time
import sqlite3
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import send_file, send_from_directory, request, jsonify, session
from config import DATA_DIR, DASHBOARD_HTML, _cache, CACHE_TTL
from auth import login_required, get_current_user_id, get_current_username, get_user_data_dir
from db import (
    DB_PATH, init_db, get_connection, import_excel, get_activities, get_charge_summary,
    get_charge_locations, update_charge_provider, get_custom_providers, add_custom_provider
)

LOGIN_HTML = Path(__file__).parent.parent / "templates" / "login.html"
STATIC_DIR = Path(__file__).parent.parent / "static"


def register(app):
    @app.route("/")
    def index():
        if "user_id" not in session:
            return send_file(LOGIN_HTML)
        return send_file(DASHBOARD_HTML)

    @app.route("/login")
    def login_page():
        return send_file(LOGIN_HTML)

    @app.route("/static/<path:filename>")
    def serve_static(filename):
        return send_from_directory(str(STATIC_DIR), filename)

    @app.route("/sw.js")
    def service_worker():
        return send_from_directory(str(STATIC_DIR), "sw.js", mimetype="application/javascript")

    @app.route("/manifest.json")
    def manifest():
        return send_from_directory(str(STATIC_DIR), "manifest.json", mimetype="application/manifest+json")

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(str(STATIC_DIR), "icons/favicon-32.png", mimetype="image/png")

    @app.route("/api/data")
    @login_required
    def get_data():
        uid = get_current_user_id()
        cache_key = f"data_{uid}"
        cached = _cache.get(cache_key)
        if cached and time.time() - cached["time"] < CACHE_TTL:
            return jsonify(cached["data"])
        data = get_activities(uid)
        _cache[cache_key] = {"time": time.time(), "data": data}
        return jsonify(data)

    @app.route("/api/upload", methods=["POST"])
    @login_required
    def upload_excel():
        uid = get_current_user_id()
        user_dir = get_user_data_dir(uid)

        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400

        files = request.files.getlist("files")
        total_imported = 0
        total_dups = 0
        uploaded = 0

        for file in files:
            if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
                continue
            fname = secure_filename(file.filename)
            if not fname:
                continue
            filepath = user_dir / fname
            file.save(filepath)
            try:
                result = import_excel(uid, filepath, source_name=fname)
                total_imported += result["imported"]
                total_dups += result["duplicates"]
                if result["imported"] > 0 or result["duplicates"] > 0:
                    uploaded += 1
                # Delete the Excel file after successful import — data lives in the DB
                filepath.unlink(missing_ok=True)
            except Exception:
                pass

        if uploaded == 0:
            return jsonify({"error": "No valid Excel files uploaded"}), 400

        _cache.pop(f"data_{uid}", None)
        total = len(get_activities(uid))

        return jsonify({
            "status": "ok",
            "uploaded": uploaded,
            "imported": total_imported,
            "duplicates": total_dups,
            "total_records": total,
            "message": f"{uploaded} file(s) processed — {total_imported} new, {total_dups} duplicates skipped, {total} total"
        })

    @app.route("/api/status")
    @login_required
    def status():
        uid = get_current_user_id()
        user_dir = get_user_data_dir(uid)
        record_count = len(get_activities(uid))
        connected = []
        for b in ["vw", "tesla", "bmw", "hyundai_kia", "mercedes"]:
            if (user_dir / f"connector_{b}.json").exists():
                connected.append(b)
        return jsonify({
            "status": "running",
            "excel_files": len(list(user_dir.glob("*.xlsx"))),
            "total_records": record_count,
            "connectors": connected,
            "user": get_current_username(),
        })

    @app.route("/api/charge-summary")
    @login_required
    def charge_summary():
        uid = get_current_user_id()
        return jsonify(get_charge_summary(uid))

    # ── Custom charge providers (global) ──
    @app.route("/api/custom-providers")
    @login_required
    def custom_providers_get():
        return jsonify(get_custom_providers())

    @app.route("/api/custom-providers", methods=["POST"])
    @login_required
    def custom_providers_add():
        data = request.json or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Provider name required"}), 400
        if len(name) > 50:
            return jsonify({"error": "Name too long (max 50 chars)"}), 400
        providers = add_custom_provider(name)
        return jsonify({"status": "ok", "providers": providers})

    # ── Charge locations editor ──
    @app.route("/api/charge-locations")
    @login_required
    def charge_locations_api():
        uid = get_current_user_id()
        return jsonify(get_charge_locations(uid))

    @app.route("/api/charge-location/<int:activity_id>", methods=["PATCH"])
    @login_required
    def charge_location_update(activity_id):
        uid = get_current_user_id()
        data = request.json or {}
        provider = data.get("provider", "").strip()
        if not provider:
            return jsonify({"error": "Provider required"}), 400
        update_charge_provider(activity_id, provider)
        _cache.pop(f"data_{uid}", None)
        return jsonify({"status": "ok", "message": f"Provider updated to {provider}"})

    # ── Admin: DB Backup ──────────────────────────────────────────
    def _create_backup():
        """Create a SQLite backup in data/backups/. Keeps only the 3 most recent."""
        from datetime import datetime as _dt
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Clean old backups: keep only the 3 most recent
        old_backups = sorted(backup_dir.glob("evdashboard-backup-*.db"))
        for old in old_backups[:-3]:
            old.unlink(missing_ok=True)

        backup_name = f"evdashboard-backup-{_dt.now().strftime('%Y%m%d-%H%M%S')}.db"
        backup_path = backup_dir / backup_name
        backup_conn = sqlite3.connect(str(backup_path))
        source_conn = sqlite3.connect(str(DB_PATH))
        source_conn.backup(backup_conn)
        backup_conn.close()
        source_conn.close()
        return backup_path, backup_name

    def _auto_backup_if_needed():
        """Create a backup if the last one is older than 7 days."""
        import time as _time
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backups = sorted(backup_dir.glob("evdashboard-backup-*.db"))
        if backups:
            last_mtime = backups[-1].stat().st_mtime
            age_days = (_time.time() - last_mtime) / 86400
            if age_days < 7:
                return  # Recent enough
        try:
            _create_backup()
            print(f"   ✅ Auto-backup created (weekly)")
        except Exception as e:
            print(f"   ⚠️ Auto-backup failed: {e}")

    @app.route("/api/admin/backup-db")
    @login_required
    def backup_db():
        """Download a SQLite backup of the unified database. Admin only."""
        uid = get_current_user_id()
        from auth import get_db
        conn = get_db()
        user = conn.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
        if not user or not user["is_admin"]:
            return jsonify({"error": "Admin access required"}), 403

        from flask import send_file as _send_file
        backup_path, backup_name = _create_backup()
        return _send_file(
            str(backup_path),
            as_attachment=True,
            download_name=backup_name,
            mimetype="application/octet-stream"
        )
