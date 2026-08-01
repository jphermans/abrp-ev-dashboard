"""Generic connector plugin routes — handles all vehicle manufacturers."""

import json
import sys
from pathlib import Path
from datetime import datetime
from flask import request, jsonify

sys.path.insert(0, str(Path(__file__).parent.parent))
from connectors import list_connectors, get_connector_class
from config import DATA_DIR, rate_limited, _cache


def _merge_records(records, data_dir):
    """Merge new records into activities.json with dedup."""
    existing_json = data_dir / "activities.json"
    all_records = []
    if existing_json.exists():
        with open(existing_json) as f:
            all_records = json.load(f)
    all_records.extend(records)
    seen = set()
    deduped = []
    for r in all_records:
        key = f"{r.get('datetime', '')}|{r.get('activity', '')}"
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
    deduped.sort(key=lambda x: x.get("datetime", ""))
    with open(existing_json, "w") as f:
        json.dump(deduped, f, ensure_ascii=False)
    return len(deduped)


def register(app):
    @app.route("/api/connectors")
    def connectors_list():
        return jsonify(list_connectors())

    @app.route("/api/connector/<brand>/config", methods=["POST"])
    def connector_config(brand):
        cls = get_connector_class(brand)
        if not cls:
            return jsonify({"error": f"Unknown connector: {brand}"}), 404
        data = request.json or {}
        action = data.get("action", "save")
        config_file = DATA_DIR / f"connector_{brand}.json"
        if action == "delete":
            config_file.unlink(missing_ok=True)
            (DATA_DIR / f"token_{brand}.json").unlink(missing_ok=True)
            name = cls().display_name
            return jsonify({"status": "ok", "message": f"{name} credentials deleted"})
        credentials = {}
        instance = cls()
        for field in instance.credential_fields:
            key = field["key"]
            if key in data:
                credentials[key] = data[key]
        if not credentials:
            return jsonify({"error": "No credentials provided"}), 400
        for field in instance.credential_fields:
            if field.get("required") and not credentials.get(field["key"]):
                return jsonify({"error": f"Missing required field: {field['label']}"}), 400
        with open(config_file, "w") as f:
            json.dump({"credentials": credentials, "last_sync": None}, f, ensure_ascii=False)
        name = cls().display_name
        return jsonify({"status": "ok", "message": f"{name} credentials saved"})

    @app.route("/api/connector/<brand>/status", methods=["GET"])
    def connector_status(brand):
        cls = get_connector_class(brand)
        if not cls:
            return jsonify({"error": f"Unknown connector: {brand}"}), 404
        config_file = DATA_DIR / f"connector_{brand}.json"
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
            creds = config.get("credentials", {})
            instance = cls()
            masked = {}
            for field in instance.credential_fields:
                key = field["key"]
                val = creds.get(key, "")
                masked[key] = bool(val) if field["type"] == "password" else val
            return jsonify({"configured": True, "credentials": masked, "last_sync": config.get("last_sync")})
        return jsonify({"configured": False})

    @app.route("/api/connector/<brand>/test", methods=["POST"])
    def connector_test(brand):
        cls = get_connector_class(brand)
        if not cls:
            return jsonify({"error": f"Unknown connector: {brand}"}), 404
        data = request.json or {}
        credentials = data.get("credentials", {})
        if not credentials:
            config_file = DATA_DIR / f"connector_{brand}.json"
            if config_file.exists():
                with open(config_file) as f:
                    credentials = json.load(f).get("credentials", {})
        if not credentials:
            return jsonify({"error": "No credentials configured"}), 400
        rate_limited()
        return jsonify(cls(credentials=credentials).test_connection())

    @app.route("/api/connector/<brand>/sync", methods=["POST"])
    def connector_sync(brand):
        cls = get_connector_class(brand)
        if not cls:
            return jsonify({"error": f"Unknown connector: {brand}"}), 404
        config_file = DATA_DIR / f"connector_{brand}.json"
        credentials = {}
        config_data = None
        if config_file.exists():
            with open(config_file) as f:
                config_data = json.load(f)
                credentials = config_data.get("credentials", {})
        else:
            credentials = (request.json or {}).get("credentials", {})
        if not credentials:
            return jsonify({"error": "No credentials configured. Save settings first."}), 400
        rate_limited()
        credentials["_token_file"] = str(DATA_DIR / f"token_{brand}.json")
        try:
            records = cls(credentials=credentials).sync()
        except NotImplementedError as e:
            return jsonify({"error": str(e)}), 501
        except Exception as e:
            msg = str(e)
            if "401" in msg or "Unauthorized" in msg:
                return jsonify({"error": "Login failed — check credentials"}), 401
            return jsonify({"error": msg[:500]}), 500
        if not records:
            return jsonify({"status": "ok", "message": "Login OK but no trip data found.", "fetched": 0, "total": 0})
        total = _merge_records(records, DATA_DIR)
        if config_data is None:
            config_data = {"credentials": credentials}
        config_data["last_sync"] = datetime.now().isoformat()
        with open(config_file, "w") as f:
            json.dump(config_data, f, ensure_ascii=False)
        _cache.clear()
        return jsonify({
            "status": "ok",
            "message": f"{cls().display_name} sync: {len(records)} records fetched, {total} total",
            "fetched": len(records),
            "total": total
        })

    # Legacy VW routes (backward compat)
    @app.route("/api/vw/sync", methods=["POST"])
    def vw_sync_legacy():
        return connector_sync("vw")

    @app.route("/api/vw/status", methods=["GET"])
    def vw_status_legacy():
        return connector_status("vw")

    @app.route("/api/vw/config", methods=["POST"])
    def vw_config_legacy():
        return connector_config("vw")
