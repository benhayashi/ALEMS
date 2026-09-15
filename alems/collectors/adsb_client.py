"""ADS-B Telemetry Collector for ALEMS.
Polls readsb / tar1090 JSON feeds from a Raspberry Pi 4 receiver.
"""

import time
import requests
from typing import List, Dict, Any, Optional
from alems.config import config
from alems.geodesy import distance_nm, distance_ft, initial_bearing

class ADSBClient:
    """Client for reading live ADS-B data from readsb on Raspberry Pi."""

    def __init__(self, endpoint_url: Optional[str] = None):
        self.endpoint_url = endpoint_url or config.READSB_URL
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ALEMS-Lead-Monitor/1.0"})
        self.last_fetch_time: float = 0.0
        self.is_connected: bool = False
        self.last_error: Optional[str] = None

    def fetch_raw_aircraft(self) -> List[Dict[str, Any]]:
        """Fetch latest aircraft.json from readsb receiver."""
        try:
            # Supports both http:// URLs and local file:/// paths
            if self.endpoint_url.startswith("file://") or self.endpoint_url.startswith("/"):
                path = self.endpoint_url.replace("file://", "")
                import json
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                resp = self.session.get(self.endpoint_url, timeout=3.0)
                resp.raise_for_status()
                data = resp.json()

            self.is_connected = True
            self.last_error = None
            self.last_fetch_time = time.time()
            return data.get("aircraft", [])
        except Exception as e:
            self.is_connected = False
            self.last_error = str(e)
            return []

    def get_aircraft_in_range(
        self,
        home_lat: float = config.HOME_LAT,
        home_lon: float = config.HOME_LON,
        home_elev_ft: float = config.HOME_ELEV_MSL_FT,
        radius_nm: float = config.ACTIVE_MONITOR_RADIUS_NM
    ) -> List[Dict[str, Any]]:
        """Fetch and filter aircraft strictly within proximity of monitored house."""
        raw_list = self.fetch_raw_aircraft()
        filtered: List[Dict[str, Any]] = []

        now_ts = time.time()

        for ac in raw_list:
            lat = ac.get("lat")
            lon = ac.get("lon")
            if lat is None or lon is None:
                continue

            dist_nm_val = distance_nm(lat, lon, home_lat, home_lon)
            if dist_nm_val <= radius_nm:
                dist_ft_val = distance_ft(lat, lon, home_lat, home_lon)
                alt_msl = float(ac.get("alt_geom") or ac.get("alt_baro") or 1000.0)
                alt_agl = max(0.0, alt_msl - home_elev_ft)
                bearing = initial_bearing(home_lat, home_lon, lat, lon)

                augmented = dict(ac)
                augmented["dist_nm"] = round(dist_nm_val, 2)
                augmented["dist_ft"] = round(dist_ft_val, 0)
                augmented["alt_msl_ft"] = round(alt_msl, 0)
                augmented["alt_agl_ft"] = round(alt_agl, 0)
                augmented["bearing_from_house"] = round(bearing, 1)
                augmented["timestamp_epoch"] = now_ts
                filtered.append(augmented)

        # Sort by closest distance
        filtered.sort(key=lambda x: x["dist_ft"])
        return filtered

adsb_client = ADSBClient()
