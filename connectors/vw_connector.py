#!/usr/bin/env python3
"""
Volkswagen WeConnect Connector
Uses the CarConnectivity library (successor to WeConnect-python).
Free — requires only a VW account (email + password).

CarConnectivity supports: Volkswagen, Skoda, Seat/Cupra, Audi, Tronity.
"""

import tempfile
import json
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
            from carconnectivity.carconnectivity import CarConnectivity  # noqa: F401
            from carconnectivity_connectors.volkswagen.connector import Connector  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def install_hint(self) -> str:
        return "pip install carconnectivity carconnectivity-connector-volkswagen"

    def _create_cc(self):
        """Create a CarConnectivity instance with stored credentials."""
        from carconnectivity.carconnectivity import CarConnectivity

        username = self.credentials.get("username", "")
        password = self.credentials.get("password", "")
        spin = self.credentials.get("spin") or ""
        token_file = self.credentials.get("_token_file")

        config = {
            "carConnectivity": {
                "connectors": [{
                    "type": "volkswagen",
                    "config": {
                        "username": username,
                        "password": password,
                    }
                }],
                "plugins": []
            }
        }

        cc = CarConnectivity(
            config=config,
            tokenstore_file=token_file or tempfile.mktemp(suffix=".json"),
        )
        return cc

    def _connect(self) -> Dict:
        """
        Attempt to connect and fetch all data.
        Returns {"status": "ok", "cc": cc} or {"status": "error", "message": "..."}.
        """
        if not self.is_available:
            return {"status": "error", "message": f"Bibliotheek niet geïnstalleerd: {self.install_hint}"}

        try:
            cc = self._create_cc()
            cc.fetch_all()
            return {"status": "ok", "cc": cc}
        except Exception as e:
            msg = str(e)
            if "400" in msg or "login page was not successful" in msg:
                return {"status": "error", "message": "Login mislukt — controleer e-mail en wachtwoord"}
            if "401" in msg or "Unauthorized" in msg:
                return {"status": "error", "message": "Login mislukt — controleer e-mail en wachtwoord"}
            if "403" in msg or "Forbidden" in msg or "BFF" in msg:
                return {"status": "error",
                        "message": "VW authenticatie tijdelijk niet beschikbaar. Volkswagen wijzigt de WeConnect login (sinds mei 2026). "
                                   "Gebruik ondertussen Excel upload."}
            if "terms" in msg.lower():
                return {"status": "error", "message": "Accepteer de WeConnect voorwaarden in de VW app eerst"}
            return {"status": "error", "message": msg[:200]}

    def test_connection(self) -> Dict:
        result = self._connect()
        if result["status"] != "ok":
            return {"status": "error", "message": result["message"]}

        cc = result["cc"]
        try:
            garage = cc.get_garage()
            vehicles = garage.list_vehicles() if garage else []
            cc.shutdown()
            return {"status": "ok", "vehicles": len(vehicles),
                    "message": f"Verbinding OK — {len(vehicles)} voertuig(en) gevonden"}
        except Exception as e:
            try:
                cc.shutdown()
            except:
                pass
            return {"status": "error", "message": f"Voertuigen ophalen mislukt: {str(e)[:150]}"}

    def sync(self) -> List[Dict]:
        result = self._connect()
        if result["status"] != "ok":
            raise RuntimeError(result["message"])

        cc = result["cc"]
        records = []

        try:
            garage = cc.get_garage()
            if not garage:
                return records

            for vehicle in garage.list_vehicles():
                vehicle_name = getattr(vehicle, 'name', None) or vehicle.id or 'VW'

                # ─── Drives (trips) ───
                try:
                    drives = vehicle.get_by_path("drives") if hasattr(vehicle, 'get_by_path') else None
                    if drives:
                        for drive_id in drives.children:
                            drive = drives.children[drive_id]
                            drive_dict = drive.as_dict() if hasattr(drive, 'as_dict') else {}

                            distance_km = None
                            if 'distance' in drive_dict:
                                dist = drive_dict['distance']
                                if isinstance(dist, dict):
                                    distance_km = dist.get('value', dist.get('km', 0))
                                elif isinstance(dist, (int, float)):
                                    distance_km = dist

                            start_ts = str(drive_dict.get('startTime', drive_dict.get('start', '')))
                            end_ts = str(drive_dict.get('endTime', drive_dict.get('end', '')))

                            # Use end timestamp for the record date
                            ts = end_ts or start_ts
                            if not ts:
                                continue

                            records.append(self.make_record(
                                date=ts[:10],
                                time=ts[11:16] if len(ts) > 11 else '',
                                datetime=ts.replace(' ', 'T')[:16],
                                activity="Rijd",
                                duration=str(drive_dict.get('duration', '')),
                                distance_km=float(distance_km) if distance_km else None,
                                start_soc=self._safe_pct(drive_dict.get('startSoc')),
                                end_soc=self._safe_pct(drive_dict.get('endSoc')),
                                vehicle=str(vehicle_name),
                            ))
                except Exception:
                    pass

                # ─── Charging sessions ───
                try:
                    charging = vehicle.get_by_path("charging") if hasattr(vehicle, 'get_by_path') else None
                    if charging:
                        charge_dict = charging.as_dict() if hasattr(charging, 'as_dict') else {}

                        # Check for charging sessions (history)
                        sessions = charge_dict.get('sessions', {})
                        if isinstance(sessions, dict):
                            for sess_id, sess in sessions.items():
                                sess_dict = sess.as_dict() if hasattr(sess, 'as_dict') else (sess if isinstance(sess, dict) else {})
                                ts = str(sess_dict.get('endTime', sess_dict.get('start', '')))
                                if ts:
                                    records.append(self.make_record(
                                        date=ts[:10],
                                        time=ts[11:16] if len(ts) > 11 else '',
                                        datetime=ts.replace(' ', 'T')[:16],
                                        activity="Laad op",
                                        energy_kwh=float(sess_dict.get('chargedEnergy', 0)) or None,
                                        start_soc=self._safe_pct(sess_dict.get('startSoc')),
                                        end_soc=self._safe_pct(sess_dict.get('endSoc')),
                                        charge_location=sess_dict.get('location', ''),
                                        vehicle=str(vehicle_name),
                                    ))
                except Exception:
                    pass

            cc.shutdown()
        except Exception:
            try:
                cc.shutdown()
            except:
                pass

        return records

    def get_vehicle_info(self) -> List[Dict]:
        """Fetch static vehicle information."""
        result = self._connect()
        if result["status"] != "ok":
            return []

        cc = result["cc"]
        vehicles_info = []

        try:
            garage = cc.get_garage()
            if garage:
                for vehicle in garage.list_vehicles():
                    info = {
                        "vin": vehicle.id or '',
                        "nickname": getattr(vehicle, 'name', None) or vehicle.id or 'VW',
                        "model": '',
                        "capabilities": [],
                    }

                    # Get vehicle attributes
                    try:
                        attrs = vehicle.get_attributes() if hasattr(vehicle, 'get_attributes') else {}
                        if attrs:
                            info['model'] = attrs.get('model', attrs.get('name', ''))
                    except:
                        pass

                    # Get odometer from drives
                    try:
                        drives = vehicle.get_by_path("drives") if hasattr(vehicle, 'get_by_path') else None
                        if drives:
                            drive_dict = drives.as_dict() if hasattr(drives, 'as_dict') else {}
                            odo = drive_dict.get('mileage', drive_dict.get('odometer', 0))
                            if isinstance(odo, dict):
                                info['odometer_km'] = odo.get('value', odo.get('km', 0))
                            elif isinstance(odo, (int, float)):
                                info['odometer_km'] = odo
                    except:
                        pass

                    # Get battery/charging status
                    try:
                        charging = vehicle.get_by_path("charging") if hasattr(vehicle, 'get_by_path') else None
                        if charging:
                            charge_dict = charging.as_dict() if hasattr(charging, 'as_dict') else {}
                            soc = charge_dict.get('batteryLevel', {})
                            if isinstance(soc, dict):
                                info['battery_soc'] = soc.get('value')
                            elif isinstance(soc, (int, float)):
                                info['battery_soc'] = soc
                            state = charge_dict.get('state', '')
                            if isinstance(state, dict):
                                info['charging_state'] = state.get('value', str(state))
                            else:
                                info['charging_state'] = str(state) if state else None
                    except:
                        pass

                    vehicles_info.append(info)

            cc.shutdown()
        except:
            try:
                cc.shutdown()
            except:
                pass

        return vehicles_info

    @staticmethod
    def _safe_pct(val):
        """Convert a 0-100 or 0-1 value to integer percentage."""
        if val is None:
            return None
        try:
            f = float(val)
            if f <= 1.0:
                return round(f * 100)
            return round(f)
        except (ValueError, TypeError):
            return None
