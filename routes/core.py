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
        cache_key = f"data_{uid}"
        cached = _cache.get(cache_key)
        if cached and time.time() - cached["time"] < CACHE_TTL:
            return jsonify(cached["data"])

        data_file = get_data_file(user_dir)
        if not data_file:
            return jsonify([])
        if str(data_file).endswith(".json"):
            try:
                with open(data_file) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                return jsonify([])
        elif str(data_file).endswith(".xlsx"):
            data = parse_excel_to_records(data_file)
            with open(user_dir / "activities.json", "w") as f:
                json.dump(data, f, ensure_ascii=False)
        else:
            data = []
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
        all_records = []
        uploaded = 0
        for file in files:
            if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
                continue
            # C1: sanitize filename to prevent path traversal
            fname = secure_filename(file.filename)
            if not fname:
                continue
            filepath = user_dir / fname
            file.save(filepath)
            try:
                parsed = parse_excel_to_records(filepath)
                all_records.extend(parsed)
                uploaded += 1
            except Exception as e:
                # Don't let one bad file kill the whole upload
                pass
        if uploaded == 0:
            return jsonify({"error": "No valid Excel files uploaded"}), 400
        total = merge_and_save_records(user_dir, all_records)
        _cache.pop(f"data_{uid}", None)
        return jsonify({
            "status": "ok",
            "uploaded": uploaded,
            "total_records": total,
            "message": f"{uploaded} file(s) processed, {total} total records"
        })

    @app.route("/api/status")
    @login_required
    def status():
        uid = get_current_user_id()
        user_dir = get_user_data_dir(uid)
        json_file = user_dir / "activities.json"
        record_count = 0
        if json_file.exists():
            try:
                with open(json_file) as f:
                    record_count = len(json.load(f))
            except (json.JSONDecodeError, IOError):
                pass
        connected = []
        for b in ["vw", "tesla", "bmw", "hyundai_kia", "mercedes"]:
            if (user_dir / f"connector_{b}.json").exists():
                connected.append(b)
        data_file = get_data_file(user_dir)
        return jsonify({
            "status": "running",
            "data_source": str(data_file) if data_file else "none",
            "excel_files": len(list(user_dir.glob("*.xlsx"))),
            "total_records": record_count,
            "connectors": connected,
            "user": get_current_username(),
        })
