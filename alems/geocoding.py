"""Geocoding and Airport Lookup Services for ALEMS.
Provides OpenStreetMap Nominatim address geocoding and global airport identification.
"""

import json
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any
import requests
from alems.config import config, DATA_DIR

AIRPORTS_FILE = DATA_DIR / "airports.json"

class GeocodingService:
    """Handles address-to-coordinate resolution and airport database lookups."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ALEMS-Lead-Exposure-Monitor/1.0"})
        self.local_airports: Dict[str, Any] = {}
        self._load_local_airports()

    def _load_local_airports(self) -> None:
        if AIRPORTS_FILE.exists():
            try:
                with open(AIRPORTS_FILE, "r", encoding="utf-8") as f:
                    self.local_airports = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load local airports database: {e}")

    def geocode_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Geocode an address to latitude and longitude using OpenStreetMap Nominatim.
        Zero API key required.
        """
        if not address or not address.strip():
            return None

        clean_addr = address.strip()
        encoded = urllib.parse.quote(clean_addr)
        url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"

        try:
            resp = self.session.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    first = data[0]
                    lat = float(first["lat"])
                    lon = float(first["lon"])
                    display_name = first.get("display_name", clean_addr)
                    return {
                        "address": display_name,
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "source": "OpenStreetMap Nominatim"
                    }
        except Exception as e:
            print(f"Geocoding error for '{address}': {e}")

        return None

    def lookup_airport(self, code: str) -> Optional[Dict[str, Any]]:
        """Lookup airport coordinates, elevation, and runway geometry by ICAO/FAA code.
        Zero API key required.
        """
        if not code or not code.strip():
            return None

        code_clean = code.strip().upper()

        # 1. Check local airports database
        if code_clean in self.local_airports:
            return dict(self.local_airports[code_clean])

        # Check with or without 'K' prefix for US airports (e.g. 2W6 vs K2W6, RHV vs KRHV)
        if len(code_clean) == 3 and f"K{code_clean}" in self.local_airports:
            return dict(self.local_airports[f"K{code_clean}"])
        if code_clean.startswith("K") and code_clean[1:] in self.local_airports:
            return dict(self.local_airports[code_clean[1:]])

        # 2. Query AviationWeather.gov Station Info API
        try:
            url = f"https://aviationweather.gov/api/data/metar?ids={code_clean}&format=json"
            resp = self.session.get(url, timeout=4.0)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    st = data[0]
                    lat = float(st.get("lat", 0.0))
                    lon = float(st.get("lon", 0.0))
                    elev_m = float(st.get("elev", 0.0))
                    elev_ft = round(elev_m * 3.28084, 0)
                    name = st.get("name") or f"Airport {code_clean}"

                    return {
                        "id": code_clean,
                        "icao": code_clean,
                        "name": name,
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "elev_msl_ft": elev_ft,
                        "primary_runway": "Runway",
                        "runway_heading_1": 90.0,
                        "runway_heading_2": 270.0,
                        "runway_length_ft": 5000.0,
                        "metar_station": code_clean,
                        "source": "AviationWeather API"
                    }
        except Exception as e:
            print(f"AviationWeather lookup failed for {code_clean}: {e}")

        # 3. Fallback to OpenStreetMap Nominatim search for aerodrome
        try:
            query = f"{code_clean} airport"
            enc = urllib.parse.quote(query)
            url = f"https://nominatim.openstreetmap.org/search?q={enc}&format=json&limit=1"
            resp = self.session.get(url, timeout=4.0)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    first = data[0]
                    return {
                        "id": code_clean,
                        "icao": code_clean,
                        "name": first.get("display_name", f"Airport {code_clean}").split(",")[0],
                        "lat": round(float(first["lat"]), 6),
                        "lon": round(float(first["lon"]), 6),
                        "elev_msl_ft": 100.0,
                        "primary_runway": "Runway",
                        "runway_heading_1": 90.0,
                        "runway_heading_2": 270.0,
                        "runway_length_ft": 5000.0,
                        "metar_station": code_clean,
                        "source": "OpenStreetMap Nominatim"
                    }
        except Exception as e:
            print(f"OSM airport lookup failed for {code_clean}: {e}")

        return None

geocoding_service = GeocodingService()
