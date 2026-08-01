"""ABRP API proxy routes (requires premium API key)."""

import json
from flask import request, jsonify
from config import rate_limited
from auth import login_required


def register(app):
    @app.route("/api/abrp/login", methods=["POST"])
    @login_required
    def abrp_login():
        data = request.json or {}
        email = data.get("email", "")
        password = data.get("password", "")
        api_key = data.get("api_key", "")
        if not email or not password or not api_key:
            return jsonify({"error": "email, password, and api_key are required"}), 400
        try:
            import urllib.request, urllib.error
            rate_limited()
            login_body = json.dumps({"username": email, "password": password}).encode()
            req = urllib.request.Request("https://api.iternio.com/2/auth/login", data=login_body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("X-API-KEY", api_key)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    login_resp = json.loads(resp.read())
            except urllib.error.HTTPError as e:
                return jsonify({"error": f"ABRP login failed (HTTP {e.code})", "details": e.read().decode()[:500]}), 502
            token = login_resp.get("access_token")
            if not token:
                return jsonify({"error": "No access_token in response"}), 502
            return jsonify({"status": "ok", "session_token": token})
        except Exception as e:
            return jsonify({"error": str(e)[:200]}), 500
