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
        """Return composite wind state containing both ground and aerodrome readings."""
        ecowitt = self.fetch_home_assistant_ecowitt()
        aerodrome = self.fetch_aerodrome_metar()

        # Effective wind for plume steering:
        # Use aerodrome direction (free of tree-line distortion) and Ecowitt speed (or blend)
        return {
            "ecowitt": ecowitt,
            "aerodrome": aerodrome,
            # Effective values used for real-time dispersion model:
            "effective_wind_speed_mph": ecowitt.get("wind_speed_mph", 5.0),
            "effective_wind_dir_deg": aerodrome.get("wind_dir_deg", ecowitt.get("wind_dir_deg", 110.0)),
            "effective_gust_mph": ecowitt.get("wind_gust_mph", 6.0)
        }

weather_collector = WeatherCollector()
