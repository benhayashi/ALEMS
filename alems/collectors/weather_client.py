"""Dual-layer weather collector for ALEMS.
Integrates local Ecowitt weather station via Home Assistant (ground microclimate)
and official aerodrome METAR from 2W6 / KNHK (winds aloft above the tree line).
"""

import time
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from alems.config import config

class WeatherCollector:
    """Manages dual-source atmospheric wind and temperature telemetry."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ALEMS-Lead-Monitor/1.0"})

        # Cached state
        self.last_ecowitt: Dict[str, Any] = {
            "source": "ecowitt",
            "wind_speed_mph": 4.5,
            "wind_dir_deg": 120.0,
            "wind_gust_mph": 6.0,
            "temp_f": 72.0,
            "humidity": 60.0,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "initial_default"
        }

        self.last_aerodrome: Dict[str, Any] = {
            "source": "aerodrome_metar",
            "station": "KNHK",
            "wind_speed_kts": 6.0,
            "wind_speed_mph": 6.9,
            "wind_dir_deg": 110.0,
            "temp_c": 22.0,
            "temp_f": 71.6,
            "altimeter": 30.12,
            "raw_metar": "",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "initial_default"
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

    def fetch_aerodrome_metar(self) -> Dict[str, Any]:
        """Fetch official aerodrome METAR observation from KNHK / 2W6 via AviationWeather.gov API."""
        now = time.time()
        # Rate limit aerodrome polling (every 3-5 mins is standard for METAR)
        if now - self.last_aerodrome_poll < config.METAR_POLL_INTERVAL_SEC and self.last_aerodrome.get("raw_metar"):
            return self.last_aerodrome

        stations = config.METAR_STATIONS.split(",")
        # AviationWeather.gov JSON API
        url = f"https://aviationweather.gov/api/data/metar?ids={','.join(stations)}&format=json"

        try:
            resp = self.session.get(url, timeout=4.0)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    ob = data[0] # Priority first station (e.g. KNHK)
                    wdir = ob.get("wdir")
                    wspd_kts = ob.get("wspd", 0)
                    temp_c = ob.get("temp", 20.0)

                    self.last_aerodrome = {
                        "source": "aerodrome_metar",
                        "station": ob.get("icaoId", "KNHK"),
                        "wind_speed_kts": float(wspd_kts) if wspd_kts is not None else 5.0,
                        "wind_speed_mph": round(float(wspd_kts) * 1.15078, 1) if wspd_kts is not None else 5.8,
                        "wind_dir_deg": float(wdir) if wdir is not None else 110.0,
                        "temp_c": temp_c,
                        "temp_f": round(temp_c * 9.0 / 5.0 + 32.0, 1) if temp_c is not None else 70.0,
                        "raw_metar": ob.get("rawOb", ""),
                        "timestamp_utc": ob.get("reportTime", datetime.now(timezone.utc).isoformat()),
                        "status": "live"
                    }
                    self.last_aerodrome_poll = now
        except Exception as e:
            self.last_aerodrome["status"] = f"error: {e}"

        return self.last_aerodrome

    def get_effective_wind(self) -> Dict[str, Any]:
        """Return composite wind state containing ground and aerodrome readings."""
        # Query ground microclimate depending on configured source
        provider = config.WEATHER_PROVIDER
        if provider == "ecowitt_local" and config.ECOWITT_IP:
            ecowitt = self.fetch_ecowitt_local_ip()
        elif provider == "ecowitt_push":
            ecowitt = self.last_ecowitt
        elif provider == "homeassistant" and config.HASS_TOKEN:
            ecowitt = self.fetch_home_assistant_ecowitt()
        elif config.ECOWITT_IP:
            ecowitt = self.fetch_ecowitt_local_ip()
        elif config.HASS_TOKEN:
            ecowitt = self.fetch_home_assistant_ecowitt()
        else:
            ecowitt = self.last_ecowitt

        aerodrome = self.fetch_aerodrome_metar()

        # Effective wind for plume steering:
        # If ground station is live, use ground speed and aerodrome direction (aloft above trees)
        wind_spd = ecowitt.get("wind_speed_mph", 5.0)
        wind_dir = aerodrome.get("wind_dir_deg", ecowitt.get("wind_dir_deg", 110.0))
        wind_gust = ecowitt.get("wind_gust_mph", wind_spd * 1.3)

        return {
            "ecowitt": ecowitt,
            "aerodrome": aerodrome,
            "provider": provider,
            "effective_wind_speed_mph": wind_spd,
            "effective_wind_dir_deg": wind_dir,
            "effective_gust_mph": wind_gust
        }

weather_collector = WeatherCollector()
