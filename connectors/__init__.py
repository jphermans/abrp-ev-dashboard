#!/usr/bin/env python3
"""
Connector Plugin Registry
All vehicle data connectors are registered here.
To add a new brand: create a connector file and add it to CONNECTORS.
"""

from .base import BaseConnector
from .vw_connector import VolkswagenConnector
from .tesla_connector import TeslaConnector
from .bmw_connector import BMWConnector
from .hyundai_kia_connector import HyundaiKiaConnector
from .mercedes_connector import MercedesConnector

# ─── Registry ────────────────────────────────────────────────────
# Each entry: brand_id → connector class
CONNECTORS = {
    "vw":           VolkswagenConnector,
    "tesla":        TeslaConnector,
    "bmw":          BMWConnector,
    "hyundai_kia":  HyundaiKiaConnector,
    "mercedes":     MercedesConnector,
}


def get_connector_class(brand: str):
    """Get a connector class by brand id. Returns None if not found."""
    return CONNECTORS.get(brand)


def list_connectors():
    """List all registered connector metadata for the settings panel."""
    result = []
    for brand_id, cls in CONNECTORS.items():
        instance = cls()
        result.append({
            "brand": brand_id,
            "display_name": instance.display_name,
            "icon": instance.icon,
            "available": instance.is_available,
            "install_hint": instance.install_hint,
            "credential_fields": instance.credential_fields,
        })
    return result


def create_connector(brand: str, credentials: dict = None):
    """Create a connector instance with credentials."""
    cls = get_connector_class(brand)
    if not cls:
        raise ValueError(f"Unknown connector: {brand}")
    return cls(credentials=credentials)
