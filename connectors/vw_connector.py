#!/usr/bin/env python3
"""
Volkswagen WeConnect Connector
Fetches trip and charging data from VW servers using the weconnect library.
Free — requires only a VW account (email + password).
"""

from typing import List, Dict
from .base import BaseConnector


class VolkswagenConnector(BaseConnector):

    @property
    def brand(self) -> str:
        return "vw"

    @property
    def display_name(self) -> str:
        return "Volkswagen WeConnect"

    @property
    def icon(self) -> str:
        return "🚗"

    @property
    def credential_fields(self) -> List[Dict]:
        return [
            {"key": "username", "label": "VW account e-mail", "type": "email", "required": True, "placeholder": "you@example.com"},
            {"key": "password", "label": "VW wachtwoord", "type": "password", "required": True, "placeholder": ""},
            {"key": "spin", "label": "S-PIN (optioneel)", "type": "password", "required": False, "placeholder": ""},
        ]

    @property
    def is_available(self) -> bool:
        try:
            import weconnect  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def install_hint(self) -> str:
        return "pip install weconnect"

    def test_connection(self) -> Dict:
        if not self.is_available:
            return {"status": "error", "message": f"Library niet geïnstalleerd: {self.install_hint}"}

        try:
            from weconnect import WeConnect
            from weconnect.domain import Domain

            wc = WeConnect(
                username=self.credentials.get("username", ""),
                password=self.credentials.get("password", ""),
                spin=self.credentials.get("spin") or None,
                updateAfterLogin=False,
                loginOnInit=True,
                updatePictures=False,
                timeout=15,
                numRetries=1,
            )
            vehicles = list(wc.vehicles.keys())
            wc.disconnect()
            return {"status": "ok", "vehicles": len(vehicles), "message": f"Verbinding OK — {len(vehicles)} voertuig(en) gevonden"}
        except Exception as e:
            msg = str(e)
            if "401" in msg or "Unauthorized" in msg:
                return {"status": "error", "message": "Login mislukt — controleer e-mail en wachtwoord"}
            if "terms" in msg.lower():
                return {"status": "error", "message": "Accepteer de WeConnect voorwaarden in de VW app eerst"}
            return {"status": "error", "message": msg[:200]}

    def sync(self) -> List[Dict]:
        if not self.is_available:
            raise RuntimeError(f"weconnect library not installed: {self.install_hint}")

        from weconnect import WeConnect
        from weconnect.domain import Domain

        token_file = self.credentials.get("_token_file")

        wc = WeConnect(
            username=self.credentials.get("username", ""),
            password=self.credentials.get("password", ""),
            spin=self.credentials.get("spin") or None,
            tokenfile=token_file,
            updateAfterLogin=True,
            loginOnInit=True,
            updatePictures=False,
            maxAge=300,
            timeout=30,
            numRetries=2,
            selective=[Domain.TRIPS, Domain.CHARGING, Domain.MEASUREMENTS, Domain.BATTERY_SUPPORT],
        )

        records = []

        for vin, vehicle in wc.vehicles.items():
            vehicle_name = getattr(vehicle, 'nickname', None) or vin

            # ─── Trips ───
            try:
                if vehicle.statusExists("trips"):
                    trips_dict = vehicle.getByAddressString("trips", allowEmpty=True)
                    if trips_dict:
                        for trip_id, trip in trips_dict.items():
                            trip_data = trip.asDict() if hasattr(trip, 'asDict') else {}
                            distance_km = (trip_data.get('mileage_km', 0) or 0) - (trip_data.get('startMileage_km', 0) or 0)
                            if distance_km < 0:
                                distance_km = trip_data.get('mileage_km', 0) or 0

                            end_ts = str(trip_data.get('tripEndTimestamp', ''))
                            records.append(self.make_record(
                                date=end_ts[:10],
                                time=end_ts[11:16],
                                datetime=end_ts.replace(' ', 'T')[:16],
                                activity="Rijd",
                                duration=f"{trip_data.get('travelTime', 0)} sec",
                                distance_km=distance_km if distance_km else None,
                                start_odo_km=trip_data.get('startMileage_km'),
                                end_odo_km=trip_data.get('mileage_km'),
                                vehicle=str(vehicle_name),
                            ))
            except Exception:
                pass

            # ─── Current charging status ───
            try:
                if vehicle.statusExists("charging"):
                    charging = vehicle.getByAddressString("charging", allowEmpty=True)
                    if charging:
                        charge_data = charging.asDict() if hasattr(charging, 'asDict') else {}
                        soc = charge_data.get('batteryStatus', {}).get('currentSOC_pct', 0) if charge_data.get('batteryStatus') else None
                        charge_type = charge_data.get('chargingStatus', {}).get('chargeType', '') if charge_data.get('chargingStatus') else None
                        records.append(self.make_record(
                            activity="Laad op",
                            start_soc=round(soc) if soc else None,
                            charge_location=charge_type,
                            vehicle=str(vehicle_name),
                        ))
            except Exception:
                pass

        wc.disconnect()
        return records
