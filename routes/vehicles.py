"""Vehicle management routes — multi-vehicle and fleet support."""

import time
from pathlib import Path
from flask import request, jsonify, session
from werkzeug.utils import secure_filename
from config import _cache
from auth import (
    login_required, get_current_user_id,
    get_user_vehicles, get_vehicle_by_id, create_vehicle, delete_vehicle,
    is_fleet_manager, get_connection as _auth_conn
)
from db import import_excel, get_activities, get_connection


def register(app):
    @app.route("/api/vehicles")
    @login_required
    def vehicles_list():
        uid = get_current_user_id()
        vehicles = get_user_vehicles(uid)
        conn = get_connection()
        for v in vehicles:
            count = conn.execute(
                "SELECT COUNT(*) FROM activities WHERE user_id = ? AND vehicle_id = ?",
                (uid, v["id"])
            ).fetchone()[0]
            v["record_count"] = count
        conn.close()
        return jsonify(vehicles)

    @app.route("/api/vehicles", methods=["POST"])
    @login_required
    def vehicle_create():
        uid = get_current_user_id()
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Vehicle name is required"}), 400
        vid = create_vehicle(
            uid, name,
            brand=data.get("brand"), model=data.get("model"),
            vin=data.get("vin"), license_plate=data.get("license_plate"),
            connector_brand=data.get("connector_brand"),
        )
        return jsonify({"status": "ok", "vehicle_id": vid, "message": f"Vehicle '{name}' created"})

    @app.route("/api/vehicles/<int:vid>", methods=["DELETE"])
    @login_required
    def vehicle_delete(vid):
        uid = get_current_user_id()
        vehicle = get_vehicle_by_id(vid, uid)
        if not vehicle:
            return jsonify({"error": "Vehicle not found"}), 404
        # Delete activities for this vehicle
        conn = get_connection()
        conn.execute("DELETE FROM activities WHERE user_id = ? AND vehicle_id = ?", (uid, vid))
        conn.commit()
        conn.close()
        delete_vehicle(vid, uid)
        _cache.pop(f"data_{uid}", None)
        _cache.pop(f"data_{uid}_{vid}", None)
        return jsonify({"status": "ok", "message": f"Vehicle '{vehicle['name']}' deleted"})

    @app.route("/api/vehicles/<int:vid>/data")
    @login_required
    def vehicle_data(vid):
        uid = get_current_user_id()
        vehicle = get_vehicle_by_id(vid, uid)
        if not vehicle:
            return jsonify({"error": "Vehicle not found"}), 404
        cache_key = f"data_{uid}_{vid}"
        cached = _cache.get(cache_key)
        if cached and time.time() - cached["time"] < 300:
            return jsonify(cached["data"])
        data = get_activities(uid, vehicle_id=vid)
        _cache[cache_key] = {"time": time.time(), "data": data}
        return jsonify(data)

    @app.route("/api/vehicles/<int:vid>/upload", methods=["POST"])
    @login_required
    def vehicle_upload(vid):
        uid = get_current_user_id()
        vehicle = get_vehicle_by_id(vid, uid)
        if not vehicle:
            return jsonify({"error": "Vehicle not found"}), 404
        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400
        files = request.files.getlist("files")
        from auth import get_vehicle_data_dir
        vdir = get_vehicle_data_dir(uid, vid)
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
                import_excel(uid, filepath, vehicle_id=vid, source_name=fname)
                uploaded += 1
            except Exception:
                pass
        if uploaded == 0:
            return jsonify({"error": "No valid Excel files uploaded"}), 400
        _cache.pop(f"data_{uid}_{vid}", None)
        total = len(get_activities(uid, vehicle_id=vid))
        return jsonify({
            "status": "ok",
            "uploaded": uploaded,
            "total_records": total,
            "message": f"{uploaded} file(s) processed, {total} total records for '{vehicle['name']}'"
        })

    # ─── Fleet Overview ────────────────────────────────────────────
    @app.route("/api/fleet")
    @login_required
    def fleet_overview():
        if not is_fleet_manager() and not session.get("is_admin"):
            return jsonify({"error": "Fleet manager access required"}), 403

        conn = get_connection()
        users = conn.execute("""
            SELECT DISTINCT u.id, u.username, u.display_name, u.is_fleet_manager
            FROM users u
            INNER JOIN vehicles v ON v.user_id = u.id
            ORDER BY u.display_name
        """).fetchall()

        fleet = []
        for user in users:
            vehicles = conn.execute(
                "SELECT * FROM vehicles WHERE user_id = ? ORDER BY created_at",
                (user["id"],)
            ).fetchall()

            user_vehicles = []
            for v in vehicles:
                acts = conn.execute(
                    "SELECT * FROM activities WHERE user_id = ? AND vehicle_id = ?",
                    (user["id"], v["id"])
                ).fetchall()
                records = [dict(a) for a in acts]
                total_km = sum(r.get("distance_km", 0) or 0 for r in records)
                last_odo = max((r["end_odo_mi"] * 1.609344 for r in records if r.get("end_odo_mi")), default=0)
                last_soc = next((r["end_soc"] for r in reversed(records)
                                 if r.get("activity") == "Laad op" and r.get("end_soc") is not None), None)

                user_vehicles.append({
                    "id": v["id"], "name": v["name"], "brand": v["brand"],
                    "model": v["model"], "vin": v["vin"],
                    "license_plate": v["license_plate"],
                    "connector_brand": v["connector_brand"],
                    "records": len(records), "total_km": round(total_km),
                    "odometer_km": round(last_odo), "battery_soc": last_soc,
                })

            fleet.append({
                "user_id": user["id"], "username": user["username"],
                "display_name": user["display_name"] or user["username"],
                "vehicles": user_vehicles,
            })

        conn.close()
        return jsonify({"fleet": fleet})
