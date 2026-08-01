#!/usr/bin/env python3
"""
ABRP EV Dashboard Server — entry point
Modular design: config, excel_parser, connectors/, routes/
Designed for Raspberry Pi 4/5.
"""

import os
import json
import sys
from pathlib import Path

# Ensure local modules are importable
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
from config import DATA_DIR, get_pi_model
from excel_parser import parse_excel_to_records

app = Flask(__name__)

# Register all route modules
from routes.core import register as register_core
from routes.abrp import register as register_abrp
from routes.connectors import register as register_connectors

register_core(app)
register_abrp(app)
register_connectors(app)


def startup_import():
    """Auto-import Excel files from data/ on startup."""
    excel_files = list(DATA_DIR.glob("*.xlsx"))
    if not excel_files:
        return 0
    print(f"   Found {len(excel_files)} Excel file(s), importing...")
    all_records = []
    for ef in excel_files:
        recs = parse_excel_to_records(ef)
        all_records.extend(recs)
        print(f"   → {ef.name}: {len(recs)} records")
    seen = set()
    deduped = []
    for r in all_records:
        k = f"{r['datetime']}|{r['activity']}"
        if k not in seen:
            seen.add(k)
            deduped.append(r)
    deduped.sort(key=lambda x: x["datetime"])
    with open(DATA_DIR / "activities.json", "w") as f:
        json.dump(deduped, f, ensure_ascii=False)
    print(f"   ✅ {len(deduped)} records loaded")
    return len(deduped)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"🚗 ABRP Dashboard starting on http://{host}:{port}")
    print(f"   Pi: {get_pi_model()}")
    print(f"   Data: {DATA_DIR}")
    startup_import()
    app.run(host=host, port=port, debug=False)
