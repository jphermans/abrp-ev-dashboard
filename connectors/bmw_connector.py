#!/usr/bin/env python3
"""BMW Connector — stub for future implementation using bimmer_connected."""

from typing import List, Dict
from .base import BaseConnector


class BMWConnector(BaseConnector):

    @property
    def brand(self) -> str:
        return "bmw"

    @property
    def display_name(self) -> str:
        return "BMW Connected Drive"

    @property
    def icon(self) -> str:
        return "🔵"

    @property
    def credential_fields(self) -> List[Dict]:
        return [
            {"key": "username", "label": "BMW e-mail", "type": "email", "required": True, "placeholder": "you@example.com"},
            {"key": "password", "label": "BMW wachtwoord", "type": "password", "required": True},
            {"key": "region", "label": "Regio", "type": "select", "required": True, "options": ["rest_of_world", "north_america", "china"], "default": "rest_of_world"},
        ]

    @property
    def is_available(self) -> bool:
        try:
            import bimmer_connected  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def install_hint(self) -> str:
        return "pip install bimmer-connected"

    def test_connection(self) -> Dict:
        if not self.is_available:
            return {"status": "error", "message": f"Niet geïnstalleerd: {self.install_hint}"}
        return {"status": "error", "message": "BMW connector nog niet geïmplementeerd — komende release"}

    def sync(self) -> List[Dict]:
        raise NotImplementedError("BMW sync nog niet geïmplementeerd. Gebruik Excel upload of ABRP API.")
