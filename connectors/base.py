#!/usr/bin/env python3
"""
ABRP EV Dashboard — Base Connector Plugin
Subclass this to add support for a new vehicle manufacturer.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class BaseConnector(ABC):
    """
    Abstract base class for vehicle data connectors.

    To add a new brand:
    1. Create a file in connectors/<brand>_connector.py
    2. Subclass BaseConnector
    3. Implement: brand, display_name, credential_fields, test_connection(), sync()
    4. Register in connectors/__init__.py

    The sync() method must return a list of records in the dashboard format:
    {
        "date": "2026-07-01",
        "time": "08:30",
        "datetime": "2026-07-01T08:30",
        "weekday": "Dinsdag",
        "activity": "Rijd" | "Laad op",
        "duration": "30 min",
        "distance_km": 45.2,
        "distance_mi": 28.1,
        "start_soc": 80,
        "end_soc": 60,
        "energy_kwh": None,
        "start_odo_mi": None,
        "end_odo_mi": None,
        "vehicle": "Brand Model",
        "charge_provider": "ProviderName",
        "charge_location": "Location",
    }
    """

    def __init__(self, credentials: Optional[Dict] = None):
        self.credentials = credentials or {}

    # ─── Identity (subclasses must override) ──────────────────────

    @property
    @abstractmethod
    def brand(self) -> str:
        """Short identifier used in API URLs: 'vw', 'tesla', 'bmw', etc."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the settings panel: 'Volkswagen WeConnect'"""
        pass

    @property
    @abstractmethod
    def icon(self) -> str:
        """Emoji icon for the settings panel: '🚗', '🚀', etc."""
        pass

    @property
    @abstractmethod
    def credential_fields(self) -> List[Dict]:
        """
        Define what input fields the settings panel should show.
        Returns a list of field definitions:
        [
            {"key": "username", "label": "E-mail", "type": "email", "required": True, "placeholder": "you@example.com"},
            {"key": "password", "label": "Wachtwoord", "type": "password", "required": True},
            {"key": "spin", "label": "S-PIN", "type": "password", "required": False},
        ]
        """
        pass

    @property
    def is_available(self) -> bool:
        """Check if the required Python library is installed."""
        return True

    @property
    def install_hint(self) -> str:
        """Pip install command shown if library is missing."""
        return ""

    # ─── Methods (subclasses must override) ───────────────────────

    @abstractmethod
    def test_connection(self) -> Dict:
        """
        Test if the credentials are valid.
        Returns: {"status": "ok"} or {"status": "error", "message": "..."}
        """
        pass

    @abstractmethod
    def sync(self) -> List[Dict]:
        """
        Fetch trips and charging data from the manufacturer's servers.
        Returns a list of dashboard-format records (see class docstring).
        """
        pass

    # ─── Shared helpers ───────────────────────────────────────────

    WEEKDAYS_NL = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]

    @staticmethod
    def km_to_mi(km: float) -> float:
        """Convert kilometers to miles."""
        return round(km / 1.609344, 1) if km is not None else None

    @staticmethod
    def mi_to_km(mi: float) -> float:
        """Convert miles to kilometers."""
        return round(mi * 1.609344, 1) if mi is not None else None

    @staticmethod
    def make_record(
        date: str = "",
        time: str = "",
        datetime: str = "",
        activity: str = "Rijd",
        duration: str = "",
        distance_km: float = None,
        start_soc: int = None,
        end_soc: int = None,
        energy_kwh: float = None,
        start_odo_km: float = None,
        end_odo_km: float = None,
        vehicle: str = "EV",
        charge_provider: str = None,
        charge_location: str = None,
    ) -> Dict:
        """Create a dashboard-format record with auto-conversions."""
        # Compute weekday from date if provided
        weekday = ""
        if date:
            try:
                from datetime import datetime as _dt
                d = _dt.strptime(date[:10], "%Y-%m-%d")
                weekday = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"][d.weekday()]
            except (ValueError, IndexError):
                pass
        return {
            "date": date,
            "time": time,
            "datetime": datetime,
            "weekday": weekday,
            "activity": activity,
            "duration": duration,
            "distance_km": round(distance_km, 1) if distance_km is not None else None,
            "distance_mi": round(distance_km / 1.609344, 1) if distance_km is not None else None,
            "start_soc": start_soc,
            "end_soc": end_soc,
            "energy_kwh": energy_kwh,
            "start_odo_mi": round(start_odo_km / 1.609344, 1) if start_odo_km is not None else None,
            "end_odo_mi": round(end_odo_km / 1.609344, 1) if end_odo_km is not None else None,
            "vehicle": vehicle,
            "charge_provider": charge_provider,
            "charge_location": charge_location,
        }
