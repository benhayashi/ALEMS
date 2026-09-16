"""Dual-layer weather collector for ALEMS.
Integrates local Ecowitt weather station via Home Assistant (ground microclimate)
and official aerodrome METAR from 2W6 / KNHK (winds aloft above the tree line).
"""

import time
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from alems.config import config

def degrees_to_cardinal(deg: Optional[Any]) -> str:
    """Convert degrees to standard 16-wind compass cardinal direction string."""
    if deg is None or str(deg).strip().upper() in ("VRB", "CALM", "NONE", ""):
        return "VRB"
    try:
        deg_flt = float(deg) % 360.0
        val = int((deg_flt / 22.5) + 0.5)
        arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
               "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        return arr[(val % 16)]
    except (ValueError, TypeError):
        return "VRB"

class WeatherCollector:
    """Manages dual-source atmospheric wind and temperature telemetry."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ALEMS-Lead-Monitor/1.0"})

        # Cached state - explicitly mark Ecowitt unconfigured if no hardware connected
        self.last_ecowitt: Dict[str, Any] = {
            "source": "ecowitt",
            "wind_speed_mph": None,
            "wind_dir_deg": None,
            "wind_gust_mph": None,
            "temp_f": None,
            "humidity": None,
            "timestamp_utc": None,
            "status": "not_configured"
        }

        self.last_aerodrome: Dict[str, Any] = {
            "source": "aerodrome_metar",
            "station": "KNHK",
            "station_name": "Patuxent River NAS",
            "wind_speed_kts": 0.0,
            "wind_speed_mph": 0.0,
            "wind_gust_kts": 0.0,
            "wind_gust_mph": 0.0,
            "wind_dir_deg": 0.0,
            "wind_dir_text": "0°",
            "temp_c": 20.0,
            "temp_f": 68.0,
            "altimeter": None,
            "raw_metar": "",
            "flt_cat": "VFR",
            "report_time": "",
            "timestamp_utc": None,
            "status": "initial_waiting"
        }

        self.last_aerodrome_poll: float = 0.0

    def fetch_home_assistant_ecowitt(self) -> Dict[str, Any]:
        """Fetch real-time microclimate from Home Assistant Ecowitt entities."""
        if not config.HASS_TOKEN:
            # No token configured; keep existing cached/fallback state
            self.last_ecowitt["status"] = "unconfigured_token"
            return self.last_ecowitt

        headers = {
            "Authorization": f"Bearer {config.HASS_TOKEN}",
            "Content-Type": "application/json"
        }

        base_url = config.HASS_URL.rstrip("/")
        try:
            # Wind speed
            speed_val = self._query_hass_state(base_url, config.HASS_WIND_SPEED_ENTITY, headers)
            dir_val = self._query_hass_state(base_url, config.HASS_WIND_DIR_ENTITY, headers)
            gust_val = self._query_hass_state(base_url, config.HASS_WIND_GUST_ENTITY, headers)
            temp_val = self._query_hass_state(base_url, config.HASS_TEMP_ENTITY, headers)

            self.last_ecowitt = {
                "source": "ecowitt_home_assistant",
                "wind_speed_mph": float(speed_val) if speed_val is not None else self.last_ecowitt["wind_speed_mph"],
                "wind_dir_deg": float(dir_val) if dir_val is not None else self.last_ecowitt["wind_dir_deg"],
                "wind_gust_mph": float(gust_val) if gust_val is not None else self.last_ecowitt["wind_gust_mph"],
                "temp_f": float(temp_val) if temp_val is not None else self.last_ecowitt["temp_f"],
                "humidity": 55.0,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "status": "live"
            }
        except Exception as e:
            self.last_ecowitt["status"] = f"error: {e}"

        return self.last_ecowitt

    def fetch_ecowitt_local_ip(self) -> Dict[str, Any]:
        """Directly query Ecowitt gateway (GW1000/1100/2000/Wittboy) on local network.
        Zero cloud, zero Home Assistant, zero API key required.
        """
        if not config.ECOWITT_IP:
            self.last_ecowitt["status"] = "unconfigured_ip"
            return self.last_ecowitt

        port = config.ECOWITT_PORT or 80
        url = f"http://{config.ECOWITT_IP}:{port}/get_livedata_info"
        try:
            resp = self.session.get(url, timeout=2.5)
            if resp.status_code == 200:
                data = resp.json()
                # Parse standard Ecowitt JSON payload
                # Gateway returns arrays like common_list, wh65, or wh25
                wh65 = data.get("wh65", [{}])[0] if data.get("wh65") else {}
                wh25 = data.get("wh25", [{}])[0] if data.get("wh25") else {}
                
                # Check for wind speed & direction in wh65 or root
                wind_speed_raw = wh65.get("windspeed") or data.get("windspeed")
                wind_dir_raw = wh65.get("winddir") or data.get("winddir")
                wind_gust_raw = wh65.get("gustspeed") or data.get("windgust")
                temp_raw = wh65.get("temp") or wh25.get("intemp")
                hum_raw = wh65.get("humidity") or wh25.get("inhum")

                if wind_speed_raw is not None:
                    # Clean units like 'mph', 'm/s' or 'km/h' if strings
                    try:
                        spd = float(str(wind_speed_raw).replace("mph", "").replace("m/s", "").replace("km/h", "").strip())
                    except ValueError:
                        spd = self.last_ecowitt["wind_speed_mph"]

                    try:
                        wdir = float(str(wind_dir_raw).replace("°", "").strip())
                    except (ValueError, TypeError):
                        wdir = self.last_ecowitt["wind_dir_deg"]

                    try:
                        gust = float(str(wind_gust_raw).replace("mph", "").strip())
                    except (ValueError, TypeError):
                        gust = spd * 1.3

                    try:
                        temp = float(str(temp_raw).replace("°F", "").replace("F", "").strip())
                    except (ValueError, TypeError):
                        temp = self.last_ecowitt["temp_f"]

                    try:
                        hum = float(str(hum_raw).replace("%", "").strip())
                    except (ValueError, TypeError):
                        hum = 55.0

                    self.last_ecowitt = {
                        "source": "ecowitt_direct_local_ip",
                        "ip": config.ECOWITT_IP,
                        "wind_speed_mph": round(spd, 1),
                        "wind_dir_deg": round(wdir, 1),
                        "wind_gust_mph": round(gust, 1),
                        "temp_f": round(temp, 1),
                        "humidity": round(hum, 1),
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "status": "live"
                    }
            else:
                self.last_ecowitt["status"] = f"http_{resp.status_code}"
        except Exception as e:
            self.last_ecowitt["status"] = f"offline: {e}"

        return self.last_ecowitt

    def handle_ecowitt_push_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Ingest real-time payload pushed by Ecowitt gateway via Customized Weather Service."""
        try:
            # Ecowitt push parameters:
            # winddir, windspeedmph, windgustmph, tempf, humidity, stationtype
            wdir = params.get("winddir")
            wspd = params.get("windspeedmph") or params.get("windspeed")
            wgust = params.get("windgustmph") or params.get("windgust")
            temp = params.get("tempf") or params.get("temp")
            humidity = params.get("humidity")

            if wspd is not None and wdir is not None:
                self.last_ecowitt = {
                    "source": "ecowitt_local_push",
                    "station_type": params.get("stationtype", "Ecowitt"),
                    "wind_speed_mph": float(wspd),
                    "wind_dir_deg": float(wdir),
                    "wind_gust_mph": float(wgust) if wgust is not None else float(wspd) * 1.25,
                    "temp_f": float(temp) if temp is not None else 72.0,
                    "humidity": float(humidity) if humidity is not None else 50.0,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "status": "live"
                }
        except Exception as e:
            print(f"Error handling Ecowitt push: {e}")

        return self.last_ecowitt

    def _query_hass_state(self, base_url: str, entity_id: str, headers: Dict[str, str]) -> Optional[float]:
        try:
            url = f"{base_url}/api/states/{entity_id}"
            resp = self.session.get(url, headers=headers, timeout=2.5)
            if resp.status_code == 200:
                data = resp.json()
                state = data.get("state")
                if state not in ("unknown", "unavailable", None):
                    return float(state)
        except Exception:
            pass
        return None

    def fetch_aerodrome_metar(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch official aerodrome METAR observation from NOAA AviationWeather API."""
        now = time.time()
        # Rate limit aerodrome polling unless forced or uninitialized
        if not force_refresh and (now - self.last_aerodrome_poll < config.METAR_POLL_INTERVAL_SEC) and self.last_aerodrome.get("raw_metar"):
            return self.last_aerodrome

        # Prioritize airport ID and configured stations
        candidates = []
        if config.AIRPORT_ID:
            aid = config.AIRPORT_ID.strip().upper()
            if len(aid) == 4 and aid.isalpha():
                candidates.append(aid)
            elif len(aid) == 3 and aid.isalpha():
                candidates.append(f"K{aid}")
        for s in config.METAR_STATIONS.split(","):
            s_clean = s.strip().upper()
            if s_clean and s_clean not in candidates:
                candidates.append(s_clean)

        url = f"https://aviationweather.gov/api/data/metar?ids={','.join(candidates)}&format=json"

        try:
            resp = self.session.get(url, timeout=4.0)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    # Pick first valid station observation
                    ob = data[0]
                    wdir_raw = ob.get("wdir")
                    wspd_raw = ob.get("wspd", 0)
                    wgst_raw = ob.get("wgst")
                    temp_raw = ob.get("temp")

                    wspd_kts = float(wspd_raw) if wspd_raw is not None else 0.0
                    wspd_mph = round(wspd_kts * 1.15078, 1)

                    if wgst_raw is not None:
                        wgst_kts = float(wgst_raw)
                        wgst_mph = round(wgst_kts * 1.15078, 1)
                    else:
                        wgst_kts = round(wspd_kts * 1.25, 1) if wspd_kts > 0 else 0.0
                        wgst_mph = round(wspd_mph * 1.25, 1) if wspd_mph > 0 else 0.0

                    if wdir_raw is not None and str(wdir_raw).upper() != "VRB":
                        try:
                            wdir_deg = float(wdir_raw)
                            wdir_text = f"{int(wdir_deg)}°"
                        except (ValueError, TypeError):
                            wdir_deg = 0.0
                            wdir_text = "VRB"
                    else:
                        wdir_deg = None
                        wdir_text = "VRB"

                    if temp_raw is not None:
                        try:
                            temp_c = float(temp_raw)
                            temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1)
                        except (ValueError, TypeError):
                            temp_c = None
                            temp_f = None
                    else:
                        temp_c = None
                        temp_f = None

                    self.last_aerodrome = {
                        "source": "aerodrome_metar",
                        "station": ob.get("icaoId", "KNHK"),
                        "station_name": ob.get("name", "Aerodrome"),
                        "wind_speed_kts": wspd_kts,
                        "wind_speed_mph": wspd_mph,
                        "wind_gust_kts": wgst_kts,
                        "wind_gust_mph": wgst_mph,
                        "wind_dir_deg": wdir_deg,
                        "wind_dir_text": wdir_text,
                        "temp_c": temp_c,
                        "temp_f": temp_f,
                        "altimeter": ob.get("altim"),
                        "raw_metar": ob.get("rawOb", ""),
                        "flt_cat": ob.get("fltCat", "VFR"),
                        "report_time": ob.get("reportTime", ""),
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "status": "live"
                    }
                    self.last_aerodrome_poll = now
            else:
                self.last_aerodrome["status"] = f"http_{resp.status_code}"
        except Exception as e:
            self.last_aerodrome["status"] = f"error: {e}"

        return self.last_aerodrome

    def get_effective_wind(self, force_metar_refresh: bool = False) -> Dict[str, Any]:
        """Return composite wind state containing ground and aerodrome readings."""
        provider = config.WEATHER_PROVIDER
        has_live_ecowitt = False
        ecowitt = self.last_ecowitt

        if provider == "ecowitt_local":
            if config.ECOWITT_IP:
                ecowitt = self.fetch_ecowitt_local_ip()
                has_live_ecowitt = (ecowitt.get("status") == "live" and ecowitt.get("wind_speed_mph") is not None)
            else:
                ecowitt = {**self.last_ecowitt, "status": "unconfigured_ip"}
        elif provider == "ecowitt_push":
            has_live_ecowitt = (ecowitt.get("status") == "live" and ecowitt.get("wind_speed_mph") is not None)
            if not has_live_ecowitt:
                ecowitt = {**self.last_ecowitt, "status": "waiting_for_push"}
        elif provider == "homeassistant":
            if config.HASS_TOKEN:
                ecowitt = self.fetch_home_assistant_ecowitt()
                has_live_ecowitt = (ecowitt.get("status") == "live" and ecowitt.get("wind_speed_mph") is not None)
            else:
                ecowitt = {**self.last_ecowitt, "status": "unconfigured_token"}
        else:
            # "aerodrome" selected - Ecowitt is not active
            ecowitt = {**self.last_ecowitt, "status": "not_configured"}

        aerodrome = self.fetch_aerodrome_metar(force_refresh=force_metar_refresh)

        # Authoritative wind calculation:
        # If ground Ecowitt station is live and producing valid data, use its local ground speed
        # with aloft aerodrome direction (above tree line).
        # If Ecowitt is not configured or offline, strictly use Aerodrome METAR!
        if has_live_ecowitt:
            active_source = "ecowitt_ground"
            wind_spd = float(ecowitt["wind_speed_mph"])
            if aerodrome.get("status") == "live" and aerodrome.get("wind_dir_deg") is not None:
                wind_dir = float(aerodrome["wind_dir_deg"])
            else:
                wind_dir = float(ecowitt.get("wind_dir_deg") or 0.0)
            wind_gust = float(ecowitt.get("wind_gust_mph") or round(wind_spd * 1.25, 1))
            temp_f = float(ecowitt.get("temp_f") or aerodrome.get("temp_f") or 70.0)
        else:
            active_source = "aerodrome_metar"
            wind_spd = float(aerodrome.get("wind_speed_mph") or 0.0)
            wind_dir = float(aerodrome.get("wind_dir_deg") or 0.0)
            wind_gust = float(aerodrome.get("wind_gust_mph") or round(wind_spd * 1.25, 1))
            temp_f = float(aerodrome.get("temp_f") or 70.0)

        plume_dir_deg = round((wind_dir + 180.0) % 360.0, 1)
        wind_cardinal = degrees_to_cardinal(wind_dir)
        plume_cardinal = degrees_to_cardinal(plume_dir_deg)

        return {
            "ecowitt": ecowitt,
            "aerodrome": aerodrome,
            "provider": provider,
            "active_source": active_source,
            "is_ecowitt_connected": has_live_ecowitt,
            "effective_wind_speed_mph": round(wind_spd, 1),
            "effective_wind_dir_deg": round(wind_dir, 1),
            "effective_wind_cardinal": wind_cardinal,
            "effective_gust_mph": round(wind_gust, 1),
            "effective_temp_f": round(temp_f, 1),
            "plume_drift_dir_deg": plume_dir_deg,
            "plume_drift_cardinal": plume_cardinal
        }

weather_collector = WeatherCollector()
