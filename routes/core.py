"""Core routes: serve dashboard, data API, Excel upload."""

import json
import time
from flask import send_file, request, jsonify
from config import DATA_DIR, DASHBOARD_HTML, _cache, CACHE_TTL
from excel_parser import parse_excel_to_records, get_data_file


def register(app):
    @app.route("/")
    def index():
        return send_file(DASHBOARD_HTML)

    @app.route("/api/data")
    def get_data():
        cached = _cache.get("all_data")
        if cached and time.time() - cached["time"] < CACHE_TTL:
            return jsonify(cached["data"])
        data_file = get_data_file(DATA_DIR)
        if not data_file:
            return jsonify([])
        if str(data_file).endswith(".json"):
            with open(data_file) as f:
                data = json.load(f)
        elif str(data_file).endswith(".xlsx"):
            data = parse_excel_to_records(data_file)
            with open(DATA_DIR / "activities.json", "w") as f:
                json.dump(data, f, ensure_ascii=False)
        else:
            data = []
        _cache["all_data"] = {"time": time.time(), "data": data}
        return jsonify(data)

    @app.route("/api/upload", methods=["POST"])
    def upload_excel():
        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400
        files = request.files.getlist("files")
        all_records = []
        existing_json = DATA_DIR / "activities.json"
        if existing_json.exists():
            with open(existing_json) as f:
                all_records = json.load(f)
        uploaded = 0
        for file in files:
            if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
                continue
            filepath = DATA_DIR / file.filename
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
        _cache.clear()
        return jsonify({
            "status": "ok",
            "uploaded": uploaded,
            "total_records": len(deduped),
            "message": f"{uploaded} file(s) processed, {len(deduped)} total records"
        })

    @app.route("/api/status")
    def status():
        data_file = get_data_file(DATA_DIR)
        json_file = DATA_DIR / "activities.json"
        record_count = 0
        if json_file.exists():
            try:
                with open(json_file) as f:
                    record_count = len(json.load(f))
            except:
                pass
        connected = []
        for b in ["vw", "tesla", "bmw", "hyundai_kia", "mercedes"]:
            if (DATA_DIR / f"connector_{b}.json").exists():
                connected.append(b)
        return jsonify({
            "status": "running",
            "data_source": str(data_file) if data_file else "none",
            "excel_files": len(list(DATA_DIR.glob("*.xlsx"))),
            "total_records": record_count,
            "connectors": connected,
            "vw_connected": "vw" in connected,
        })
