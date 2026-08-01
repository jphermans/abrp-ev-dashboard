"""Config, paths, rate limiter and cache."""

import os
import time
import threading
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DASHBOARD_HTML = BASE_DIR / "templates" / "dashboard.html"

API_RATE_LIMIT = 0.5
_last_api_call = [0.0]
_api_lock = threading.Lock()
_cache = {}
CACHE_TTL = 300


def rate_limited():
    with _api_lock:
        elapsed = time.time() - _last_api_call[0]
        if elapsed < API_RATE_LIMIT:
            time.sleep(API_RATE_LIMIT - elapsed)
        _last_api_call[0] = time.time()


def get_pi_model():
    try:
        with open("/proc/device-tree/model") as f:
            return f.read().strip().strip("\x00")
    except:
        return "unknown"
