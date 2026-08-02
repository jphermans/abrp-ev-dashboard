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
            {"key": "abrp_token", "label": "ABRP Live Data token (optioneel)", "type": "text", "required": False, "placeholder": "van abetterrouteplanner.com → Live Data → Generic"},
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
        """Create a CarConnectivity instance with stored credentials.
        Optionally includes the ABRP plugin for live data forwarding."""
        from carconnectivity.carconnectivity import CarConnectivity

        username = self.credentials.get("username", "")
        password = self.credentials.get("password", "")
        spin = self.credentials.get("spin") or ""
        token_file = self.credentials.get("_token_file")
        abrp_token = self.credentials.get("abrp_token", "")

        connectors = [{
            "type": "volkswagen",
            "config": {
                "username": username,
                "password": password,
            }
        }]

        plugins = []
        # If user provided an ABRP user token, enable the ABRP plugin
        # to forward live vehicle data (SoC, GPS, charging) to ABRP
        if abrp_token:
            # We need the VIN for the mapping, but we don't know it yet
            # The plugin accepts a VIN→token mapping. We'll use '*' as wildcard
            # and the plugin will match by the first vehicle.
            # Actually, the plugin needs exact VIN→token mapping.
            # We'll configure it with the token and let it auto-detect.
            plugins.append({
                "type": "abrp",
                "config": {
                    "tokens": {},  # Will be filled after first vehicle discovery
                    "interval": 60,
                }
            })

        config = {
            "carConnectivity": {
                "connectors": connectors,
                "plugins": plugins,
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
            if "Login failed with status code: 400" in msg:
                return {"status": "error", "message": "Login mislukt — controleer e-mail en wachtwoord in je VW account"}
            if "Login failed with status code: 401" in msg or "401" in msg:
                return {"status": "error", "message": "Login mislukt — controleer e-mail en wachtwoord"}
            if "Login failed with status code: 403" in msg:
                return {"status": "error", "message": "VW account geblokkeerd — controleer je account in de VW app"}
            if "terms" in msg.lower() or "consent" in msg.lower():
                return {"status": "error", "message": "Accepteer de WeConnect voorwaarden in de VW app eerst"}
            if "400" in msg or "login page was not successful" in msg:
                return {"status": "error", "message": "Login mislukt — controleer e-mail en wachtwoord"}
            if "403" in msg or "Forbidden" in msg or "BFF" in msg:
                return {"status": "error",
                        "message": "VW authenticatie tijdelijk niet beschikbaar. Gebruik ondertussen Excel upload."}
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
        """Fetch comprehensive vehicle information from CarConnectivity."""
        result = self._connect()
        if result["status"] != "ok":
            return []

        cc = result["cc"]
        vehicles_info = []

        try:
            garage = cc.get_garage()
            if garage:
                for vehicle in garage.list_vehicles():
                    info = self._extract_vehicle_data(vehicle)
                    if info:
                        vehicles_info.append(info)
            cc.shutdown()
        except Exception:
            try:
                cc.shutdown()
            except:
                pass

        return vehicles_info

    def _extract_vehicle_data(self, vehicle) -> Dict:
        """Extract all available data from a CarConnectivity vehicle object."""
        def get_attr(obj, attr_name, default=None):
            """Safely get an attribute value from a CarConnectivity object."""
            try:
                attr = getattr(obj, attr_name, None)
                if attr is None:
                    return default
                # CarConnectivity attributes have .value
                if hasattr(attr, 'value'):
                    v = attr.value
                    return v if v is not None else default
                # Some are EnumAttribute — get the name
                if hasattr(attr, 'name') and not isinstance(attr, str):
                    return str(attr)
                return attr
            except Exception:
                return default

        def get_child_dict(obj, path):
            """Safely get a child object and convert to dict."""
            try:
                child = obj.get_by_path(path) if hasattr(obj, 'get_by_path') else None
                if child:
                    return child.as_dict() if hasattr(child, 'as_dict') else {}
            except Exception:
                pass
            return {}

        info = {
            "vin": str(getattr(vehicle, 'id', '') or ''),
            "nickname": str(get_attr(vehicle, 'name', '') or ''),
            "manufacturer": str(get_attr(vehicle, 'manufacturer', '') or ''),
            "model": str(get_attr(vehicle, 'model', '') or ''),
            "model_year": get_attr(vehicle, 'model_year'),
            "license_plate": str(get_attr(vehicle, 'license_plate', '') or ''),
            "type": str(get_attr(vehicle, 'type', '') or ''),
            "state": str(get_attr(vehicle, 'state', '') or ''),
            "connection_state": str(get_attr(vehicle, 'connection_state', '') or ''),
        }

        # Odometer
        info["odometer_km"] = get_attr(vehicle, 'odometer')

        # Parking brake
        info["parking_brake"] = get_attr(vehicle, 'parking_brake')

        # Charging & Battery
        try:
            charging = getattr(vehicle, 'charging', None)
            if charging:
                info["battery_soc"] = get_attr(charging, 'battery_level')
                info["charging_state"] = str(get_attr(charging, 'state', '') or '')
                info["charge_type"] = str(get_attr(charging, 'charge_type', '') or '')
                info["charge_power_kw"] = get_attr(charging, 'charge_power')
                info["charge_rate_kmh"] = get_attr(charging, 'charge_rate')
                info["remaining_charge_time"] = get_attr(charging, 'remaining_charging_time')
        except Exception:
            pass

        # Range
        try:
            # Electric vehicles have range
            if hasattr(vehicle, 'range'):
                info["range_km"] = get_attr(vehicle, 'range')
        except Exception:
            pass

        # Climatization
        try:
            climatization = getattr(vehicle, 'climatization', None)
            if climatization:
                info["climatisation_state"] = str(get_attr(climatization, 'state', '') or '')
                info["target_temperature"] = get_attr(climatization, 'target_temperature')
                info["remaining_climatisation_time"] = get_attr(climatization, 'remaining_time')
        except Exception:
            pass

        # Outside temperature
        info["outside_temperature"] = get_attr(vehicle, 'outside_temperature')

        # Doors
        try:
            doors = getattr(vehicle, 'doors', None)
            if doors:
                doors_dict = doors.as_dict() if hasattr(doors, 'as_dict') else {}
                door_list = []
                for door_id, door_data in doors_dict.items():
                    if isinstance(door_data, dict):
                        door_list.append({
                            "name": door_id,
                            "open": door_data.get('open', door_data.get('locked', '')),
                            "locked": door_data.get('locked', ''),
                        })
                if door_list:
                    info["doors"] = door_list
        except Exception:
            pass

        # Windows
        try:
            windows = getattr(vehicle, 'windows', None)
            if windows:
                windows_dict = windows.as_dict() if hasattr(windows, 'as_dict') else {}
                win_list = []
                for win_id, win_data in windows_dict.items():
                    if isinstance(win_data, dict):
                        win_list.append({
                            "name": win_id,
                            "open": win_data.get('open', win_data.get('state', '')),
                        })
                if win_list:
                    info["windows"] = win_list
        except Exception:
            pass

        # Position
        try:
            position = getattr(vehicle, 'position', None)
            if position:
                pos_dict = position.as_dict() if hasattr(position, 'as_dict') else {}
                if pos_dict:
                    info["position"] = {
                        "latitude": pos_dict.get('latitude', pos_dict.get('lat')),
                        "longitude": pos_dict.get('longitude', pos_dict.get('lng', pos_dict.get('lon'))),
                        "timestamp": pos_dict.get('timestamp', pos_dict.get('time', '')),
                    }
        except Exception:
            pass

        # Software
        try:
            software = getattr(vehicle, 'software', None)
            if software:
                info["software_version"] = str(get_attr(software, 'version', '') or '')
                info["software_update_available"] = get_attr(software, 'update_available')
        except Exception:
            pass

        # Maintenance
        try:
            maintenance = getattr(vehicle, 'maintenance', None)
            if maintenance:
                info["maintenance_inspection_km"] = get_attr(maintenance, 'inspection_due_km')
                info["maintenance_inspection_days"] = get_attr(maintenance, 'inspection_due_days')
                info["maintenance_oil_service_km"] = get_attr(maintenance, 'oil_service_due_km')
        except Exception:
            pass

        # Lights
        try:
            lights = getattr(vehicle, 'lights', None)
            if lights:
                lights_dict = lights.as_dict() if hasattr(lights, 'as_dict') else {}
                if lights_dict:
                    info["lights"] = {k: str(v) for k, v in lights_dict.items() if v}
        except Exception:
            pass

        # Window heatings
        try:
            wh = getattr(vehicle, 'window_heatings', None)
            if wh:
                wh_dict = wh.as_dict() if hasattr(wh, 'as_dict') else {}
                if wh_dict:
                    info["window_heating"] = {k: str(v) for k, v in wh_dict.items() if v}
        except Exception:
            pass

        # Specification
        try:
            spec = getattr(vehicle, 'specification', None)
            if spec:
                spec_dict = spec.as_dict() if hasattr(spec, 'as_dict') else {}
                if spec_dict:
                    info["specification"] = spec_dict
        except Exception:
            pass

        return info

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

    def send_telemetry_to_abrp(self, vehicle_info: Dict) -> Dict:
        """
        Send live vehicle data to ABRP via the /tlm/send endpoint.
        Requires an ABRP user token (from abetterrouteplanner.com → Live Data → Generic).
        Uses the CarConnectivity built-in identifier for authentication.
        """
        abrp_token = self.credentials.get("abrp_token", "")
        if not abrp_token:
            return {"status": "skipped", "message": "No ABRP token configured"}

        import requests
        from datetime import datetime, timezone

        # Build telemetry payload from vehicle info
        tlm = {}
        if vehicle_info.get("battery_soc") is not None:
            tlm["soc"] = vehicle_info["battery_soc"]
        if vehicle_info.get("odometer_km") is not None:
            tlm["odometer"] = vehicle_info["odometer_km"]
        if vehicle_info.get("range_km") is not None:
            tlm["est_battery_range"] = vehicle_info["range_km"]
        if vehicle_info.get("outside_temperature") is not None:
            tlm["ext_temp"] = vehicle_info["outside_temperature"]
        if vehicle_info.get("charging_state"):
            state = str(vehicle_info["charging_state"]).lower()
            tlm["is_charging"] = "charg" in state or "conserv" in state
        if vehicle_info.get("charge_power_kw") is not None:
            tlm["power"] = -float(vehicle_info["charge_power_kw"])
        if vehicle_info.get("position"):
            pos = vehicle_info["position"]
            if pos.get("latitude") is not None:
                tlm["lat"] = pos["latitude"]
            if pos.get("longitude") is not None:
                tlm["lon"] = pos["longitude"]
        tlm["utc"] = datetime.now(timezone.utc).timestamp()
        tlm["is_parked"] = True  # Default assumption

        try:
            resp = requests.post(
                "https://api.iternio.com/1/tlm/send",
                params={"token": abrp_token},
                json={"tlm": tlm},
                headers={
                    "Authorization": "APIKEY 6225724a-65fb-4d4c-9ac5-d7dff2b78c1d",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok":
                return {"status": "ok", "message": "Telemetry sent to ABRP"}
            return {"status": "error", "message": data.get("status", "Unknown error")}
        except Exception as e:
            return {"status": "error", "message": str(e)[:150]}
