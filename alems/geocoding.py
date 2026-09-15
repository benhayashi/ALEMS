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
        """Geocode an address to latitude and longitude using:
        1. US Census Bureau Geocoder (100% free, official US gov API, highly accurate for US addresses)
        2. OpenStreetMap Nominatim with intelligent query relaxation.
        Zero API key required.
        """
        if not address or not address.strip():
            return None

        clean_addr = address.strip()

        # Tier 1: US Census Bureau Geocoder (Best for US street addresses)
        try:
            census_url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
            params = {
                "address": clean_addr,
                "benchmark": "Public_AR_Current",
                "format": "json"
            }
            resp = self.session.get(census_url, params=params, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                matches = data.get("result", {}).get("addressMatches", [])
                if matches:
                    first = matches[0]
                    coords = first.get("coordinates", {})
                    lat = float(coords.get("y"))
                    lon = float(coords.get("x"))
                    matched = first.get("matchedAddress", clean_addr)
                    return {
                        "address": matched,
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "source": "US Census Bureau Geocoder"
                    }
        except Exception as e:
            print(f"US Census geocoding attempt failed: {e}")

        # Tier 2: OpenStreetMap Nominatim with query relaxation
        queries_to_try = [
            clean_addr,
            # If address has comma, try without middle elements or just street + zip
        ]
        parts = [p.strip() for p in clean_addr.split(",") if p.strip()]
        if len(parts) >= 3:
            # e.g. "44081 Beaver Creek Dr, MD 20619"
            queries_to_try.append(f"{parts[0]}, {parts[-1]}")
            # e.g. "44081 Beaver Creek Dr"
            queries_to_try.append(parts[0])

        for q in queries_to_try:
            try:
                encoded = urllib.parse.quote(q)
                url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"
                resp = self.session.get(url, timeout=4.0)
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
                print(f"Nominatim attempt '{q}' failed: {e}")

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
