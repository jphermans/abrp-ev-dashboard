#!/usr/bin/env python3
"""
Volkswagen WeConnect Connector
Fetches trip and charging data from VW servers using the weconnect library.
Free — requires only a VW account (email + password).

Note: As of May 2026, VW deprecated the BFF auth endpoints. The library
may fail with 'location' KeyError during auth. We catch this gracefully.
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
            from weconnect.weconnect import WeConnect  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def install_hint(self) -> str:
        return "pip install weconnect"

    def _safe_connect(self) -> Dict:
        """
        Attempt to connect to VW WeConnect.
        Returns {"status": "ok", "wc": wc, "vehicles": [...]} or {"status": "error", "message": "..."}.
        """
        from weconnect.weconnect import WeConnect
        from weconnect.domain import Domain

        token_file = self.credentials.get("_token_file")

        try:
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
            return {"status": "ok", "wc": wc}
        except KeyError as e:
            if "location" in str(e):
                return {"status": "error",
                        "message": "VW authenticatie mislukt — Volkswagen heeft de WeConnect login veranderd (mei 2026). "
                                   "De library wordt momenteel bijgewerkt. Gebruik ondertussen Excel upload."}
            return {"status": "error", "message": f"VW connectie fout: {str(e)[:150]}"}
        except Exception as e:
            msg = str(e)
            if "401" in msg or "Unauthorized" in msg:
                return {"status": "error", "message": "Login mislukt — controleer e-mail en wachtwoord"}
            if "terms" in msg.lower():
                return {"status": "error", "message": "Accepteer de WeConnect voorwaarden in de VW app eerst"}
            if "location" in msg:
                return {"status": "error",
                        "message": "VW authenticatie mislukt — Volkswagen heeft de WeConnect login veranderd (mei 2026). "
                                   "Gebruik ondertussen Excel upload."}
            return {"status": "error", "message": msg[:200]}

    def test_connection(self) -> Dict:
        if not self.is_available:
            return {"status": "error", "message": f"Library niet geïnstalleerd: {self.install_hint}"}

        result = self._safe_connect()
        if result["status"] != "ok":
            return {"status": "error", "message": result["message"]}

        wc = result["wc"]
        try:
            vehicles = list(wc.vehicles.keys())
            wc.disconnect()
            return {"status": "ok", "vehicles": len(vehicles),
                    "message": f"Verbinding OK — {len(vehicles)} voertuig(en) gevonden"}
        except Exception as e:
            try:
                wc.disconnect()
            except:
                pass
            return {"status": "error", "message": f"Voertuigen ophalen mislukt: {str(e)[:150]}"}

    def sync(self) -> List[Dict]:
        if not self.is_available:
            raise RuntimeError(f"weconnect library not installed: {self.install_hint}")

        result = self._safe_connect()
        if result["status"] != "ok":
            raise RuntimeError(result["message"])

        wc = result["wc"]
        records = []

        for vin, vehicle in wc.vehicles.items():
            vehicle_name = getattr(vehicle, 'nickname', None) or vin
            vehicle_model = getattr(vehicle, 'model', None) or ''

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
                                vehicle=f"{vehicle_name}" + (f" ({vehicle_model})" if vehicle_model else ""),
                            ))
            except (KeyError, Exception):
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
                            vehicle=f"{vehicle_name}" + (f" ({vehicle_model})" if vehicle_model else ""),
                        ))
            except (KeyError, Exception):
                pass

        try:
            wc.disconnect()
        except:
            pass
        return records

    def get_vehicle_info(self) -> List[Dict]:
        """
        Fetch static vehicle information (model, VIN, odometer, battery capacity).
        Returns a list of vehicle info dicts.
        """
        if not self.is_available:
            return []

        result = self._safe_connect()
        if result["status"] != "ok":
            return []

        wc = result["wc"]
        vehicles_info = []

        for vin, vehicle in wc.vehicles.items():
            info = {
                "vin": vin,
                "nickname": getattr(vehicle, 'nickname', None) or vin,
                "model": getattr(vehicle, 'model', None) or 'Unknown',
                "capabilities": [],
            }
            # Try to get odometer
            try:
                if vehicle.statusExists("measurements"):
                    meas = vehicle.getByAddressString("measurements", allowEmpty=True)
                    if meas:
                        meas_data = meas.asDict() if hasattr(meas, 'asDict') else {}
                        info["odometer_km"] = meas_data.get('odometer_km') or meas_data.get('mileage_km')
                        # Convert from miles if needed
                        if info.get("odometer_km") and info["odometer_km"] < 100000:
                            # Might be in miles
                            pass
            except (KeyError, Exception):
                pass

            # Try to get battery info
            try:
                if vehicle.statusExists("charging"):
                    charging = vehicle.getByAddressString("charging", allowEmpty=True)
                    if charging:
                        charge_data = charging.asDict() if hasattr(charging, 'asDict') else {}
                        bs = charge_data.get('batteryStatus', {})
                        if bs:
                            info["battery_soc"] = bs.get('currentSOC_pct')
                        cs = charge_data.get('chargingStatus', {})
                        if cs:
                            info["charging_state"] = cs.get('chargingState')
                            info["charge_type"] = cs.get('chargeType')
            except (KeyError, Exception):
                pass

            # Capabilities
            try:
                caps = vehicle.capabilities
                if caps:
                    info["capabilities"] = [getattr(c, 'id', str(c)) for c in caps] if hasattr(caps, '__iter__') else []
            except (KeyError, Exception):
                pass

            vehicles_info.append(info)

        try:
            wc.disconnect()
        except:
            pass
        return vehicles_info
