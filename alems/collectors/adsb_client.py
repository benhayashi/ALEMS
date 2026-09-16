"""ADS-B Telemetry Collector for ALEMS.
Polls readsb / tar1090 JSON feeds from a Raspberry Pi 4 receiver.
"""

import time
import requests
from typing import List, Dict, Any, Optional
from alems.config import config
from alems.geodesy import distance_nm, distance_ft, initial_bearing

import re
import struct
import urllib.parse

def decode_varint(buf: bytes, pos: int):
    res = 0
    shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        res |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            break
    return res, pos

def to_signed(val: int) -> int:
    if val >= (1 << 63):
        return val - (1 << 64)
    if val >= (1 << 31) and val < (1 << 32):
        return val - (1 << 32)
    return val

def decode_readsb_protobuf(buf: bytes) -> List[Dict[str, Any]]:
    """Decode Mictronics readsb /data/aircraft.pb protobuf stream."""
    pos = 0
    aircraft: List[Dict[str, Any]] = []

    def decode_aircraft_meta(meta_buf: bytes, p: int, end_p: int) -> Dict[str, Any]:
        ac: Dict[str, Any] = {}
        while p < end_p:
            key, p = decode_varint(meta_buf, p)
            tag = key >> 3
            wire = key & 0x7
            if wire == 0:  # varint
                val, p = decode_varint(meta_buf, p)
                if tag == 1:
                    ac['hex'] = hex(val & 0xFFFFFF)[2:].lower()
                elif tag == 3:
                    ac['squawk'] = str(val)
                elif tag == 5:
                    # signed altitude
                    s_alt = float(to_signed(val))
                    ac['alt_baro'] = s_alt
                    ac['altitude'] = s_alt
                elif tag == 20:
                    ac['alt_geom'] = float(to_signed(val))
                elif tag == 21:
                    ac['baro_rate'] = float(to_signed(val))
                elif tag == 23:
                    ac['gs'] = float(val)
                    ac['speed'] = float(val)
                elif tag == 27:
                    ac['track'] = float(val)
            elif wire == 1:  # 64-bit double
                val = struct.unpack('<d', meta_buf[p:p+8])[0]
                p += 8
                if tag == 8:
                    ac['lat'] = round(val, 6)
                elif tag == 9:
                    ac['lon'] = round(val, 6)
            elif wire == 2:  # length-delimited string
                length, p = decode_varint(meta_buf, p)
                data_bytes = meta_buf[p:p+length]
                p += length
                if tag == 2:
                    ac['flight'] = data_bytes.decode('utf-8', errors='ignore').strip()
            elif wire == 5:  # 32-bit float
                val = struct.unpack('<f', meta_buf[p:p+4])[0]
                p += 4
                if tag == 12:
                    ac['rssi'] = round(val, 1)
            else:
                break
        return ac

    while pos < len(buf):
        try:
            key, pos = decode_varint(buf, pos)
            tag = key >> 3
            wire = key & 0x7
            if wire == 0:
                val, pos = decode_varint(buf, pos)
            elif wire == 2:
                length, pos = decode_varint(buf, pos)
                if tag == 15:  # AircraftMeta
                    ac = decode_aircraft_meta(buf, pos, pos + length)
                    if ac.get('hex'):
                        aircraft.append(ac)
                pos += length
            else:
                break
        except Exception:
            break

    return aircraft

def normalize_readsb_url(url_or_host: str) -> str:
    """Normalize user input (IP, IP:port, IP/port, or URL) into a valid readsb endpoint."""
    if not url_or_host or not url_or_host.strip():
        return ""
    s = url_or_host.strip()
    if not s.startswith("http://") and not s.startswith("https://") and not s.startswith("file://") and not s.startswith("/"):
        s = f"http://{s}"
    # Convert slash-port e.g. http://192.168.1.216/8081 to http://192.168.1.216:8081
    m = re.match(r"^(https?://[^/:]+)/(\d{2,5})(/.*)?$", s)
    if m:
        base, port, rest = m.group(1), m.group(2), m.group(3) or ""
        s = f"{base}:{port}{rest}"
    # If no path specified, append standard path
    if s.startswith("http://") or s.startswith("https://"):
        parsed = urllib.parse.urlparse(s)
        if not parsed.path or parsed.path == "/":
            s = urllib.parse.urljoin(s, "/data/aircraft.pb")
    return s

class ADSBClient:
    """Client for reading live ADS-B telemetry from local receivers (readsb) or public community APIs."""

    def __init__(self, endpoint_url: Optional[str] = None, provider: Optional[str] = None):
        self._provider = provider
        self._endpoint_url = endpoint_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ALEMS-Lead-Monitor/1.0 (https://github.com/benhayashi/ALEMS)"})
        self.last_fetch_time: float = 0.0
        self.is_connected: bool = False
        self.last_error: Optional[str] = None

    @property
    def provider(self) -> str:
        return self._provider or config.ADSB_PROVIDER

    @provider.setter
    def provider(self, val: str):
        self._provider = val

    @property
    def endpoint_url(self) -> str:
        if self._endpoint_url:
            return normalize_readsb_url(self._endpoint_url) if self.provider == "readsb_local" else self._endpoint_url
        raw_url = config.ADSB_CUSTOM_URL if self.provider == "custom_url" else config.READSB_URL
        return normalize_readsb_url(raw_url) if self.provider == "readsb_local" else raw_url

    @endpoint_url.setter
    def endpoint_url(self, val: Optional[str]):
        self._endpoint_url = val

    def fetch_raw_aircraft(self) -> List[Dict[str, Any]]:
        """Fetch latest aircraft data from configured provider."""
        provider = self.provider

        if provider == "adsb_lol":
            return self._fetch_adsb_lol()
        elif provider == "opensky":
            return self._fetch_opensky()
        elif provider == "custom_url":
            return self._fetch_custom_url()
        else:
            return self._fetch_readsb_local()

    def _fetch_readsb_local(self) -> List[Dict[str, Any]]:
        """Fetch from local readsb/tar1090 service (Protobuf or JSON)."""
        target_url = self.endpoint_url
        if not target_url:
            self.is_connected = False
            self.last_error = "No readsb endpoint URL configured"
            return []

        if target_url.startswith("file://") or target_url.startswith("/"):
            path = target_url.replace("file://", "")
            try:
                import json
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.is_connected = True
                self.last_error = None
                self.last_fetch_time = time.time()
                return data.get("aircraft", [])
            except Exception as e:
                self.is_connected = False
                self.last_error = str(e)
                return []

        try:
            resp = self.session.get(target_url, timeout=3.0)

            # If 404, try automatic fallback across all standard readsb / tar1090 paths
            if resp.status_code == 404:
                parsed = urllib.parse.urlparse(target_url)
                base = f"{parsed.scheme}://{parsed.netloc}"
                candidates = [
                    f"{base}/data/aircraft.pb",
                    f"{base}/data/aircraft.json",
                    f"{base}/tar1090/data/aircraft.json",
                    f"{base}/aircraft.json",
                    f"{base}/dump1090-fa/data/aircraft.json"
                ]
                for fb_url in candidates:
                    if fb_url == target_url:
                        continue
                    try:
                        fb_resp = self.session.get(fb_url, timeout=2.0)
                        if fb_resp.status_code == 200:
                            resp = fb_resp
                            target_url = fb_url
                            self._endpoint_url = fb_url
                            config.save_persisted({"READSB_URL": fb_url})
                            break
                    except Exception:
                        continue

            resp.raise_for_status()

            # Check if Protobuf or JSON
            content_type = resp.headers.get("Content-Type", "")
            if "protobuf" in content_type or target_url.endswith(".pb") or (resp.content and resp.content[:2] in (b'\x08\x01', b'\x08\x00', b'\x08\x02')):
                aircraft_list = decode_readsb_protobuf(resp.content)
            else:
                data = resp.json()
                aircraft_list = data.get("aircraft", [])

            self.is_connected = True
            self.last_error = None
            self.last_fetch_time = time.time()
            return aircraft_list
        except Exception as e:
            self.is_connected = False
            self.last_error = str(e)
            return []

    def _fetch_adsb_lol(self) -> List[Dict[str, Any]]:
        """Fetch from community adsb.lol API (Free / Zero Hardware)."""
        try:
            radius = max(25.0, config.ACTIVE_MONITOR_RADIUS_NM * 3)
            url = f"https://api.adsb.lol/v2/point/{config.HOME_LAT}/{config.HOME_LON}/{int(radius)}"
            self.endpoint_url = url
            resp = self.session.get(url, timeout=4.0)
            resp.raise_for_status()
            data = resp.json()
            aircraft_list = data.get("ac", []) or data.get("aircraft", [])
            self.is_connected = True
            self.last_error = None
            self.last_fetch_time = time.time()
            return aircraft_list
        except Exception as e:
            self.is_connected = False
            self.last_error = f"adsb.lol: {e}"
            return []

    def _fetch_opensky(self) -> List[Dict[str, Any]]:
        """Fetch from OpenSky Network Public API (Free / Zero Hardware)."""
        try:
            lat = config.HOME_LAT
            lon = config.HOME_LON
            delta = max(0.5, config.ACTIVE_MONITOR_RADIUS_NM / 60.0 * 3.0)
            url = f"https://opensky-network.org/api/states/all?lamin={round(lat - delta, 4)}&lomin={round(lon - delta, 4)}&lamax={round(lat + delta, 4)}&lomax={round(lon + delta, 4)}"
            self.endpoint_url = url
            resp = self.session.get(url, timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            states = data.get("states", []) or []
            aircraft_list = []
            for s in states:
                if not s or len(s) < 12 or s[5] is None or s[6] is None:
                    continue
                aircraft_list.append({
                    "hex": (s[0] or "").lower(),
                    "flight": (s[1] or "").strip(),
                    "lon": float(s[5]),
                    "lat": float(s[6]),
                    "alt_baro": round(float(s[7]) * 3.28084, 0) if s[7] is not None else None,
                    "altitude": round(float(s[7]) * 3.28084, 0) if s[7] is not None else None,
                    "gs": round(float(s[9]) * 1.94384, 1) if s[9] is not None else None,
                    "speed": round(float(s[9]) * 1.94384, 1) if s[9] is not None else None,
                    "track": round(float(s[10]), 1) if s[10] is not None else None,
                    "baro_rate": round(float(s[11]) * 196.85, 0) if s[11] is not None else None
                })
            self.is_connected = True
            self.last_error = None
            self.last_fetch_time = time.time()
            return aircraft_list
        except Exception as e:
            self.is_connected = False
            self.last_error = f"OpenSky: {e}"
            return []

    def _fetch_custom_url(self) -> List[Dict[str, Any]]:
        """Fetch from a custom user-defined ADS-B API URL."""
        try:
            url = config.ADSB_CUSTOM_URL or self.endpoint_url
            if not url:
                self.is_connected = False
                self.last_error = "No custom ADS-B URL specified"
                return []
            radius = max(25.0, config.ACTIVE_MONITOR_RADIUS_NM * 3)
            formatted_url = url.replace("{lat}", str(config.HOME_LAT)).replace("{lon}", str(config.HOME_LON)).replace("{radius}", str(int(radius))).replace("{dist}", str(int(radius)))
            self.endpoint_url = formatted_url
            resp = self.session.get(formatted_url, timeout=4.0)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                aircraft_list = data
            elif isinstance(data, dict):
                aircraft_list = data.get("aircraft") or data.get("ac") or data.get("states") or []
            else:
                aircraft_list = []
            self.is_connected = True
            self.last_error = None
            self.last_fetch_time = time.time()
            return aircraft_list
        except Exception as e:
            self.is_connected = False
            self.last_error = f"Custom URL: {e}"
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
