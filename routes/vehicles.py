"""Vehicle management routes — multi-vehicle and fleet support."""

import json
import time
from pathlib import Path
from flask import request, jsonify, session
from config import DATA_DIR
from auth import (
    login_required, get_current_user_id, get_current_username,
    get_user_data_dir, get_vehicle_data_dir,
    get_user_vehicles, get_vehicle_by_id, create_vehicle, delete_vehicle,
    is_fleet_manager
)
from data_utils import merge_and_save_records
from excel_parser import parse_excel_to_records, get_data_file
from config import _cache


def register(app):
    @app.route("/api/vehicles")
    @login_required
    def vehicles_list():
        """List all vehicles for the current user."""
        uid = get_current_user_id()
        vehicles = get_user_vehicles(uid)
        # Add data stats per vehicle
        for v in vehicles:
            vdir = get_vehicle_data_dir(uid, v["id"])
            json_file = vdir / "activities.json"
            v["record_count"] = 0
            if json_file.exists():
                try:
                    with open(json_file) as f:
                        v["record_count"] = len(json.load(f))
                except (json.JSONDecodeError, IOError):
                    pass
            v["excel_files"] = len(list(vdir.glob("*.xlsx")))
        return jsonify(vehicles)

    @app.route("/api/vehicles", methods=["POST"])
    @login_required
    def vehicle_create():
        """Create a new vehicle."""
        uid = get_current_user_id()
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Vehicle name is required"}), 400
        vid = create_vehicle(
            uid, name,
            brand=data.get("brand"),
            model=data.get("model"),
            vin=data.get("vin"),
            license_plate=data.get("license_plate"),
            connector_brand=data.get("connector_brand"),
        )
        return jsonify({"status": "ok", "vehicle_id": vid, "message": f"Vehicle '{name}' created"})

    @app.route("/api/vehicles/<int:vid>", methods=["DELETE"])
    @login_required
    def vehicle_delete(vid):
        """Delete a vehicle and all its data."""
        uid = get_current_user_id()
        vehicle = get_vehicle_by_id(vid, uid)
        if not vehicle:
            return jsonify({"error": "Vehicle not found"}), 404
        delete_vehicle(vid, uid)
        _cache.pop(f"data_{uid}_{vid}", None)
        return jsonify({"status": "ok", "message": f"Vehicle '{vehicle['name']}' deleted"})

    @app.route("/api/vehicles/<int:vid>/data")
    @login_required
    def vehicle_data(vid):
        """Get activity data for a specific vehicle."""
        uid = get_current_user_id()
        vehicle = get_vehicle_by_id(vid, uid)
        if not vehicle:
            return jsonify({"error": "Vehicle not found"}), 404
        vdir = get_vehicle_data_dir(uid, vid)
        cache_key = f"data_{uid}_{vid}"
        import time as _time
        cached = _cache.get(cache_key)
        if cached and _time.time() - cached["time"] < 300:
            return jsonify(cached["data"])
        data_file = get_data_file(vdir)
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
            with open(vdir / "activities.json", "w") as f:
                json.dump(data, f, ensure_ascii=False)
        else:
            data = []
        _cache[cache_key] = {"time": _time.time(), "data": data}
        return jsonify(data)

    @app.route("/api/vehicles/<int:vid>/upload", methods=["POST"])
    @login_required
    def vehicle_upload(vid):
        """Upload Excel files for a specific vehicle."""
        from werkzeug.utils import secure_filename
        uid = get_current_user_id()
        vehicle = get_vehicle_by_id(vid, uid)
        if not vehicle:
            return jsonify({"error": "Vehicle not found"}), 404
        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400
        vdir = get_vehicle_data_dir(uid, vid)
        files = request.files.getlist("files")
        all_records = []
        uploaded = 0
        for file in files:
            if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
                continue
            fname = secure_filename(file.filename)
            if not fname:
                continue
            filepath = vdir / fname
            file.save(filepath)
            try:
                parsed = parse_excel_to_records(filepath)
                all_records.extend(parsed)
                uploaded += 1
            except Exception:
                pass
        if uploaded == 0:
            return jsonify({"error": "No valid Excel files uploaded"}), 400
        total = merge_and_save_records(vdir, all_records)
        _cache.pop(f"data_{uid}_{vid}", None)
        return jsonify({
            "status": "ok",
            "uploaded": uploaded,
            "total_records": total,
            "message": f"{uploaded} file(s) processed, {total} total records for '{vehicle['name']}'"
        })

    # ─── Fleet Overview (fleet managers only) ────────────────────

    @app.route("/api/fleet")
    @login_required
    def fleet_overview():
        """Fleet overview: all vehicles across all users (fleet managers only)."""
        if not is_fleet_manager() and not session.get("is_admin"):
            return jsonify({"error": "Fleet manager access required"}), 403

        import sqlite3
        from auth import DB_PATH
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Get all users with vehicles
        users_with_vehicles = conn.execute("""
            SELECT DISTINCT u.id, u.username, u.display_name, u.is_fleet_manager
            FROM users u
            INNER JOIN vehicles v ON v.user_id = u.id
            ORDER BY u.display_name
        """).fetchall()

        fleet = []
        for user in users_with_vehicles:
            vehicles = conn.execute(
                "SELECT * FROM vehicles WHERE user_id = ? ORDER BY created_at",
                (user["id"],)
            ).fetchall()

            user_vehicles = []
            for v in vehicles:
                vdir = Path(__file__).parent.parent / "data" / "users" / str(user["id"]) / "vehicles" / str(v["id"])
                record_count = 0
                json_file = vdir / "activities.json"
                if json_file.exists():
                    try:
                        with open(json_file) as f:
                            record_count = len(json.load(f))
                    except (json.JSONDecodeError, IOError):
                        pass

                # Calculate basic stats from the data
                total_km = 0
                last_odometer = 0
                last_charge_soc = None
                if record_count > 0:
                    try:
                        with open(json_file) as f:
                            records = json.load(f)
                        for r in records:
                            if r.get("distance_km"):
                                total_km += r["distance_km"]
                            if r.get("end_odo_mi"):
                                km = r["end_odo_mi"] * 1.609344
                                if km > last_odometer:
                                    last_odometer = km
                            if r.get("activity") == "Laad op" and r.get("end_soc") is not None:
                                last_charge_soc = r["end_soc"]
                    except (json.JSONDecodeError, IOError):
                        pass

                user_vehicles.append({
                    "id": v["id"],
                    "name": v["name"],
                    "brand": v["brand"],
                    "model": v["model"],
                    "vin": v["vin"],
                    "license_plate": v["license_plate"],
                    "connector_brand": v["connector_brand"],
                    "records": record_count,
                    "total_km": round(total_km),
                    "odometer_km": round(last_odometer),
                    "battery_soc": last_charge_soc,
                })

            fleet.append({
                "user_id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"] or user["username"],
                "vehicles": user_vehicles,
            })

        conn.close()
        return jsonify({"fleet": fleet})
