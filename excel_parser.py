"""ABRP Excel export parser — converts .xlsx to dashboard records."""

import os
from datetime import datetime
from pathlib import Path

PROVIDERS = [
    ("DATS 24", ["dats 24", "dats24"]),
    ("Fastned", ["fastned"]),
    ("Allego", ["allego"]),
    ("Shell Recharge", ["shell recharge", "shell"]),
    ("Ionity", ["ionity"]),
    ("PluginCompany", ["plugincompany", "plugin company"]),
    ("T-Line", ["t-line"]),
    ("Electra", ["electra"]),
    ("EVBox", ["evbox"]),
    ("Lidl", ["lidl"]),
]


def _extract_provider(text):
    if not text:
        return None
    low = text.lower()
    for name, patterns in PROVIDERS:
        for p in patterns:
            if p in low:
                return name
    return None


def _extract_location(loc_text):
    if not loc_text:
        return None
    parts = str(loc_text).strip().split("\n", 1)
    if len(parts) > 1:
        return parts[1].strip().strip("()")
    return None


def parse_excel_to_records(filepath):
    """Parse ABRP Excel export to dashboard records."""
    try:
        import openpyxl
    except ImportError:
        os.system("pip3 install openpyxl")
        import openpyxl

    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active
    records = []

    for row in ws.iter_rows(min_row=4, max_row=ws.max_row, values_only=True):
        if not row[0]:
            continue
        activity = row[0]
        start_raw = row[1]

        if isinstance(start_raw, datetime):
            dt = start_raw
        elif isinstance(start_raw, str):
            try:
                dt = datetime.strptime(start_raw, "%m/%d/%Y %H:%M")
            except ValueError:
                continue
        else:
            continue

        distance_mi = row[4]
        distance_km = round(float(distance_mi) * 1.609344, 1) if distance_mi else None
        energy = float(row[9]) if row[9] else None
        all_loc = f"{row[5] or ''} {row[6] or ''}"

        records.append({
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M"),
            "datetime": dt.strftime("%Y-%m-%dT%H:%M"),
            "weekday": ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"][dt.weekday()],
            "activity": activity,
            "duration": row[3] or "",
            "distance_km": distance_km,
            "distance_mi": float(distance_mi) if distance_mi else None,
            "start_soc": round(float(row[7]) * 100) if row[7] is not None else None,
            "end_soc": round(float(row[8]) * 100) if row[8] is not None else None,
            "energy_kwh": energy,
            "start_odo_mi": float(row[10]) if row[10] else None,
            "end_odo_mi": float(row[11]) if row[11] else None,
            "vehicle": row[12] or "EV",
            "charge_provider": _extract_provider(all_loc) if activity == "Laad op" else None,
            "charge_location": _extract_location(row[5] or row[6]) if activity == "Laad op" else None,
        })
    return records


def get_data_file(data_dir: Path):
    """Return path to merged JSON or most recent Excel."""
    json_file = data_dir / "activities.json"
    if json_file.exists():
        return json_file
    excels = sorted(data_dir.glob("*.xlsx"))
    if excels:
        return excels[-1]
    return None
