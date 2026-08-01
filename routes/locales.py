"""Language/locale routes — serve built-in translations, accept custom uploads."""

import json
from pathlib import Path
from flask import request, jsonify, send_file
from config import BASE_DIR

LOCALES_DIR = BASE_DIR / "locales"
CUSTOM_LOCALES_DIR = BASE_DIR / "data" / "locales"
CUSTOM_LOCALES_DIR.mkdir(parents=True, exist_ok=True)


def register(app):
    @app.route("/api/locales")
    def locales_list():
        """List all available languages (built-in + custom)."""
        languages = []
        seen_codes = set()

        # Built-in languages
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
            except Exception:
                pass

        # Custom uploaded languages
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
            except Exception:
                pass

        return jsonify(languages)

    @app.route("/api/locales/<code>")
    def locale_get(code):
        """Get a specific language file."""
        # Check built-in first
        builtin = LOCALES_DIR / f"{code}.json"
        if builtin.exists():
            return send_file(builtin, mimetype="application/json")

        # Check custom
        custom = CUSTOM_LOCALES_DIR / f"{code}.json"
        if custom.exists():
            return send_file(custom, mimetype="application/json")

        return jsonify({"error": "Language not found"}), 404

    @app.route("/api/locales/template")
    def locale_template():
        """Download the English file as a template for translation."""
        template = LOCALES_DIR / "en.json"
        if template.exists():
            return send_file(template, mimetype="application/json",
                             as_attachment=True, download_name="abrp-dashboard-language-template.json")
        return jsonify({"error": "Template not found"}), 404

    @app.route("/api/locales/upload", methods=["POST"])
    def locale_upload():
        """Upload a custom language file."""
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if not file.filename or not file.filename.endswith(".json"):
            return jsonify({"error": "Must be a .json file"}), 400

        # Parse and validate
        try:
            content = file.read().decode("utf-8")
            data = json.loads(content)
        except Exception as e:
            return jsonify({"error": f"Invalid JSON: {str(e)[:100]}"}), 400

        meta = data.get("meta", {})
        code = meta.get("code", "").strip().lower()
        if not code or len(code) > 10:
            return jsonify({"error": "meta.code must be a short language code (e.g. 'es', 'pt')"}), 400

        # Prevent overwriting built-in languages
        if (LOCALES_DIR / f"{code}.json").exists():
            return jsonify({"error": f"Language '{code}' is built-in and cannot be overwritten. Use a different code."}), 409

        # Save to custom locales
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
    def locale_delete(code):
        """Delete a custom language file."""
        # Only allow deleting custom languages
        custom = CUSTOM_LOCALES_DIR / f"{code}.json"
        builtin = LOCALES_DIR / f"{code}.json"

        if builtin.exists():
            return jsonify({"error": "Cannot delete built-in language"}), 403

        if custom.exists():
            custom.unlink()
            return jsonify({"status": "ok", "message": f"Language '{code}' deleted"})

        return jsonify({"error": "Language not found"}), 404
