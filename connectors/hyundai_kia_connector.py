#!/usr/bin/env python3
"""Hyundai/Kia Connector — stub for future implementation using hyundai_kia_connect_api."""

from typing import List, Dict
from .base import BaseConnector


class HyundaiKiaConnector(BaseConnector):

    @property
    def brand(self) -> str:
        return "hyundai_kia"

    @property
    def display_name(self) -> str:
        return "Hyundai / Kia Connect"

    @property
    def icon(self) -> str:
        return "🟦"

    @property
    def credential_fields(self) -> List[Dict]:
        return [
            {"key": "username", "label": "Hyundai/Kia e-mail", "type": "email", "required": True, "placeholder": "you@example.com"},
            {"key": "password", "label": "Wachtwoord", "type": "password", "required": True},
            {"key": "brand", "label": "Merk", "type": "select", "required": True, "options": ["hyundai", "kia"], "default": "hyundai"},
            {"key": "region", "label": "Regio", "type": "select", "required": True, "options": ["europe", "usa", "canada", "australia"], "default": "europe"},
        ]

    @property
    def is_available(self) -> bool:
        try:
            import hyundai_kia_connect_api  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def install_hint(self) -> str:
        return "pip install hyundai-kia-connect-api"

    def test_connection(self) -> Dict:
        if not self.is_available:
            return {"status": "error", "message": f"Niet geïnstalleerd: {self.install_hint}"}
        return {"status": "error", "message": "Hyundai/Kia connector nog niet geïmplementeerd — komende release"}

    def sync(self) -> List[Dict]:
        raise NotImplementedError("Hyundai/Kia sync nog niet geïmplementeerd. Gebruik Excel upload of ABRP API.")
