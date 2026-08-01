"""Shared helpers for data operations."""

import json
import os
import tempfile
from pathlib import Path


def merge_and_save_records(user_dir: Path, new_records: list) -> int:
    """
    Merge new records into the user's activities.json with deduplication.
    Atomic write: writes to .tmp then os.replace() (prevents corruption on crash).
    """
    json_file = user_dir / "activities.json"

    # Load existing records
    existing = []
    if json_file.exists():
        try:
            with open(json_file) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = []

    # Merge + deduplicate
    all_records = existing + new_records
    seen = set()
    deduped = []
    for r in all_records:
        key = f"{r.get('datetime', '')}|{r.get('activity', '')}"
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
    deduped.sort(key=lambda x: x.get("datetime", ""))

    # Atomic write: write to temp file, then replace
    tmp = json_file.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(deduped, f, ensure_ascii=False)
    os.replace(str(tmp), str(json_file))

    return len(deduped)
