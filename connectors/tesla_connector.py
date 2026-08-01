#!/usr/bin/env python3
"""Tesla Connector — stub for future implementation using teslajsonpy."""

from typing import List, Dict
from .base import BaseConnector


class TeslaConnector(BaseConnector):

    @property
    def brand(self) -> str:
        return "tesla"

    @property
    def display_name(self) -> str:
        return "Tesla"

    @property
    def icon(self) -> str:
        return "🚀"

    @property
    def credential_fields(self) -> List[Dict]:
        return [
            {"key": "email", "label": "Tesla account e-mail", "type": "email", "required": True, "placeholder": "you@example.com"},
            {"key": "password", "label": "Tesla wachtwoord", "type": "password", "required": True},
            {"key": "client_id", "label": "API Client ID (optioneel)", "type": "text", "required": False},
            {"key": "client_secret", "label": "API Client Secret (optioneel)", "type": "password", "required": False},
        ]

    @property
    def is_available(self) -> bool:
        try:
            import teslajsonpy  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def install_hint(self) -> str:
        return "pip install teslajsonpy"

    def test_connection(self) -> Dict:
        if not self.is_available:
            return {"status": "error", "message": f"Niet geïnstalleerd: {self.install_hint}"}
        return {"status": "error", "message": "Tesla connector nog niet geïmplementeerd — komende release"}

    def sync(self) -> List[Dict]:
        raise NotImplementedError("Tesla sync nog niet geïmplementeerd. Gebruik Excel upload of ABRP API.")
