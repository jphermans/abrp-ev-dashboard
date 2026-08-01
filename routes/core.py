"""Core routes: serve dashboard, per-user data API, Excel upload, login gate."""

import json
import time
from pathlib import Path
from flask import send_file, request, jsonify, session
from config import DATA_DIR, DASHBOARD_HTML, _cache, CACHE_TTL
from excel_parser import parse_excel_to_records, get_data_file
from auth import login_required, get_current_user_id, get_current_username, get_user_data_dir

LOGIN_HTML = Path(__file__).parent.parent / "templates" / "login.html"


def register(app):
    @app.route("/")
    def index():
        """Gate: show dashboard if logged in, else redirect to login."""
        if "user_id" not in session:
            return send_file(LOGIN_HTML)
        return send_file(DASHBOARD_HTML)

    @app.route("/login")
    def login_page():
        return send_file(LOGIN_HTML)

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
            with open(data_file) as f:
                data = json.load(f)
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
        existing_json = user_dir / "activities.json"
        if existing_json.exists():
            with open(existing_json) as f:
                all_records = json.load(f)
        uploaded = 0
        for file in files:
            if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
                continue
            filepath = user_dir / file.filename
            file.save(filepath)
            all_records.extend(parse_excel_to_records(filepath))
            uploaded += 1
        seen = set()
        deduped = []
        for r in all_records:
            key = f"{r['datetime']}|{r['activity']}"
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        deduped.sort(key=lambda x: x["datetime"])
        with open(existing_json, "w") as f:
            json.dump(deduped, f, ensure_ascii=False)
        _cache.pop(f"data_{uid}", None)
        return jsonify({
            "status": "ok",
            "uploaded": uploaded,
            "total_records": len(deduped),
            "message": f"{uploaded} file(s) processed, {len(deduped)} total records"
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
            except:
                pass
        connected = []
        for b in ["vw", "tesla", "bmw", "hyundai_kia", "mercedes"]:
            if (user_dir / f"connector_{b}.json").exists():
                connected.append(b)
        return jsonify({
            "status": "running",
            "data_source": str(get_data_file(user_dir)) if get_data_file(user_dir) else "none",
            "excel_files": len(list(user_dir.glob("*.xlsx"))),
            "total_records": record_count,
            "connectors": connected,
            "user": get_current_username(),
        })
