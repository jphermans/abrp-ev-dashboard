"""Language/locale routes — serve built-in translations, accept custom uploads."""

import json
import re
from pathlib import Path
from flask import request, jsonify, send_from_directory
from config import BASE_DIR
from auth import login_required, get_current_user_id, get_user_data_dir

LOCALES_DIR = BASE_DIR / "locales"
CUSTOM_LOCALES_DIR = BASE_DIR / "data" / "locales"
CUSTOM_LOCALES_DIR.mkdir(parents=True, exist_ok=True)

# C2: Strict validation of language codes — only 2-10 lowercase letters
_CODE_RE = re.compile(r'^[a-z]{2,10}$')


def register(app):
    @app.route("/api/locales")
    def locales_list():
        """List all available languages (built-in + custom)."""
        languages = []
        seen_codes = set()

        for f in sorted(LOCALES_DIR.glob("*.json")):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                meta = data.get("meta", {})
                code = meta.get("code", f.stem)
                if code not in seen_codes:
                    seen_codes.add(code)
                    languages.append({
                        "code": code,
                        "name": meta.get("language", f.stem),
                        "author": meta.get("author", ""),
                        "custom": False,
                        "builtin": True,
                    })
            except (json.JSONDecodeError, IOError):
                pass

        for f in sorted(CUSTOM_LOCALES_DIR.glob("*.json")):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                meta = data.get("meta", {})
                code = meta.get("code", f.stem)
                if code not in seen_codes:
                    seen_codes.add(code)
                    languages.append({
                        "code": code,
                        "name": meta.get("language", f.stem),
                        "author": meta.get("author", ""),
                        "custom": True,
                        "builtin": False,
                    })
            except (json.JSONDecodeError, IOError):
                pass

        return jsonify(languages)

    @app.route("/api/locales/<code>")
    def locale_get(code):
        """Get a specific language file. C2: validate code against regex."""
        if not _CODE_RE.match(code):
            return jsonify({"error": "Invalid language code"}), 400

        builtin = LOCALES_DIR / f"{code}.json"
        if builtin.exists():
            return send_from_directory(str(LOCALES_DIR), f"{code}.json", mimetype="application/json")

        custom = CUSTOM_LOCALES_DIR / f"{code}.json"
        if custom.exists():
            return send_from_directory(str(CUSTOM_LOCALES_DIR), f"{code}.json", mimetype="application/json")

        return jsonify({"error": "Language not found"}), 404

    @app.route("/api/locales/template")
    def locale_template():
        """Download the English file as a template for translation."""
        template = LOCALES_DIR / "en.json"
        if template.exists():
            return send_from_directory(str(LOCALES_DIR), "en.json", mimetype="application/json",
                                       as_attachment=True, download_name="abrp-dashboard-language-template.json")
        return jsonify({"error": "Template not found"}), 404

    @app.route("/api/locales/upload", methods=["POST"])
    @login_required
    def locale_upload():
        """Upload a custom language file (per-user)."""
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if not file.filename or not file.filename.endswith(".json"):
            return jsonify({"error": "Must be a .json file"}), 400

        try:
            content = file.read().decode("utf-8")
            data = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return jsonify({"error": f"Invalid JSON: {str(e)[:100]}"}), 400

        meta = data.get("meta", {})
        code = meta.get("code", "").strip().lower()
        if not _CODE_RE.match(code):
            return jsonify({"error": "meta.code must be 2-10 lowercase letters (e.g. 'es', 'pt')"}), 400

        if (LOCALES_DIR / f"{code}.json").exists():
            return jsonify({"error": f"Language '{code}' is built-in and cannot be overwritten. Use a different code."}), 409

        filepath = CUSTOM_LOCALES_DIR / f"{code}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return jsonify({
            "status": "ok",
            "code": code,
            "name": meta.get("language", code),
            "message": f"Language '{meta.get('language', code)}' uploaded successfully"
        })

    @app.route("/api/locales/<code>", methods=["DELETE"])
    @login_required
    def locale_delete(code):
        """Delete a custom language file. C2+C3: auth required + code validated."""
        if not _CODE_RE.match(code):
            return jsonify({"error": "Invalid language code"}), 400

        builtin = LOCALES_DIR / f"{code}.json"
        if builtin.exists():
            return jsonify({"error": "Cannot delete built-in language"}), 403

        custom = CUSTOM_LOCALES_DIR / f"{code}.json"
        if custom.exists():
            custom.unlink()
            return jsonify({"status": "ok", "message": f"Language '{code}' deleted"})

        return jsonify({"error": "Language not found"}), 404
