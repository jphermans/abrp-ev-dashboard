"""Core routes: serve dashboard, per-user data API, Excel upload, login gate."""

import json
import time
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import send_file, send_from_directory, request, jsonify, session
from config import DATA_DIR, DASHBOARD_HTML, _cache, CACHE_TTL
from excel_parser import parse_excel_to_records, get_data_file
from auth import login_required, get_current_user_id, get_current_username, get_user_data_dir
from data_utils import merge_and_save_records
from db import get_db_path, init_db, import_excel_to_db, get_all_activities, get_charge_summary, get_kpi_summary

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

    # PWA static files (manifest, service worker, icons)
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
        user_dir = get_user_data_dir(uid)
        db_path = get_db_path(user_dir)

        cache_key = f"data_{uid}"
        cached = _cache.get(cache_key)
        if cached and time.time() - cached["time"] < CACHE_TTL:
            return jsonify(cached["data"])

        if not db_path.exists():
            return jsonify([])

        data = get_all_activities(db_path)
        _cache[cache_key] = {"time": time.time(), "data": data}
        return jsonify(data)

    @app.route("/api/upload", methods=["POST"])
    @login_required
    def upload_excel():
        uid = get_current_user_id()
        user_dir = get_user_data_dir(uid)
        db_path = get_db_path(user_dir)

        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400

        init_db(db_path)

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
                result = import_excel_to_db(db_path, filepath, fname)
                total_imported += result["imported"]
                total_dups += result["duplicates"]
                if result["imported"] > 0 or result["duplicates"] > 0:
                    uploaded += 1
            except Exception:
                pass

        if uploaded == 0:
            return jsonify({"error": "No valid Excel files uploaded"}), 400

        _cache.pop(f"data_{uid}", None)

        # Get final total from DB
        from db import get_all_activities
        all_data = get_all_activities(db_path)
        total = len(all_data)

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
        db_path = get_db_path(user_dir)

        record_count = 0
        if db_path.exists():
            all_data = get_all_activities(db_path)
            record_count = len(all_data)

        connected = []
        for b in ["vw", "tesla", "bmw", "hyundai_kia", "mercedes"]:
            if (user_dir / f"connector_{b}.json").exists():
                connected.append(b)

        return jsonify({
            "status": "running",
            "data_source": str(db_path) if db_path.exists() else "none",
            "excel_files": len(list(user_dir.glob("*.xlsx"))),
            "total_records": record_count,
            "connectors": connected,
            "user": get_current_username(),
        })

    @app.route("/api/charge-summary")
    @login_required
    def charge_summary():
        """Get charge provider summary from the DB."""
        uid = get_current_user_id()
        user_dir = get_user_data_dir(uid)
        db_path = get_db_path(user_dir)
        if not db_path.exists():
            return jsonify([])
        return jsonify(get_charge_summary(db_path))
