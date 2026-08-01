#!/usr/bin/env python3
"""Mercedes-Benz Connector — stub for future implementation using mercedes-jsonio."""

from typing import List, Dict
from .base import BaseConnector


class MercedesConnector(BaseConnector):

    @property
    def brand(self) -> str:
        return "mercedes"

    @property
    def display_name(self) -> str:
        return "Mercedes-Benz (Mercedes me)"

    @property
    def icon(self) -> str:
        return "⭐"

    @property
    def credential_fields(self) -> List[Dict]:
        return [
            {"key": "username", "label": "Mercedes me e-mail", "type": "email", "required": True, "placeholder": "you@example.com"},
            {"key": "password", "label": "Wachtwoord", "type": "password", "required": True},
        ]

    @property
    def is_available(self) -> bool:
        try:
            import mercedes_jsonio  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def install_hint(self) -> str:
        return "pip install mercedes-jsonio"

    def test_connection(self) -> Dict:
        if not self.is_available:
            return {"status": "error", "message": f"Niet geïnstalleerd: {self.install_hint}"}
        return {"status": "error", "message": "Mercedes connector nog niet geïmplementeerd — komende release"}

    def sync(self) -> List[Dict]:
        raise NotImplementedError("Mercedes sync nog niet geïmplementeerd. Gebruik Excel upload of ABRP API.")
