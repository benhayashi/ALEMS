"""Configuration settings for Aerial Lead Exposure Monitoring System (ALEMS)."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "config.json"

class Settings(BaseModel):
    # Monitored Property: Address, Lat/Lon, Elevation
    HOME_ADDRESS: str = os.getenv("HOME_ADDRESS", "44081 Beaver Creek Dr, California, MD 20619")
    HOME_LAT: float = float(os.getenv("HOME_LAT", "38.27200"))
    HOME_LON: float = float(os.getenv("HOME_LON", "-76.49500"))
    HOME_ELEV_MSL_FT: float = float(os.getenv("HOME_ELEV_FT", "110.0"))

    # Nearby Airfield: Identifier, Coordinates, Runways
    AIRPORT_ID: str = os.getenv("AIRPORT_ID", "2W6")
    AIRPORT_NAME: str = os.getenv("AIRPORT_NAME", "Captain Walter Francis Duke Regional Airport")
    AIRPORT_LAT: float = float(os.getenv("AIRPORT_LAT", "38.315355"))
    AIRPORT_LON: float = float(os.getenv("AIRPORT_LON", "-76.550116"))
    AIRPORT_ELEV_MSL_FT: float = float(os.getenv("AIRPORT_ELEV_FT", "142.0"))
    AIRPORT_RUNWAY_HEADING_11: float = float(os.getenv("AIRPORT_RUNWAY_1", "110.0"))
    AIRPORT_RUNWAY_HEADING_29: float = float(os.getenv("AIRPORT_RUNWAY_2", "290.0"))
    AIRPORT_RUNWAY_LENGTH_FT: float = float(os.getenv("AIRPORT_RUNWAY_LEN", "5350.0"))

    # Geofence & Proximity Thresholds
    ACTIVE_MONITOR_RADIUS_NM: float = float(os.getenv("MONITOR_RADIUS_NM", "3.5"))  # Active tracking range
    FLYOVER_EVENT_RADIUS_NM: float = float(os.getenv("EVENT_RADIUS_NM", "1.5"))    # Event trigger proximity
    MAX_TRACK_AGE_SECONDS: int = int(os.getenv("TRACK_AGE_SEC", "30"))             # Inactivity timeout

    # ADS-B Telemetry Source Configuration
    # Options: "readsb_local" (local SDR service), "adsb_lol" (free public API), "opensky" (OpenSky public API), "custom_url"
    ADSB_PROVIDER: str = os.getenv("ADSB_PROVIDER", "readsb_local")
    ADSB_CUSTOM_URL: str = os.getenv("ADSB_CUSTOM_URL", "")
    READSB_URL: str = os.getenv("READSB_URL", "http://raspberrypi.local/tar1090/data/aircraft.json")
    READSB_HOST: str = os.getenv("READSB_HOST", "")
    READSB_PORT: int = int(os.getenv("READSB_PORT", "80"))
    READSB_PATH: str = os.getenv("READSB_PATH", "/tar1090/data/aircraft.json")
    READSB_POLL_INTERVAL_SEC: float = float(os.getenv("READSB_POLL_INTERVAL", "1.5"))

    # Weather Source & Hardware Configuration
    # Options: "ecowitt_local", "ecowitt_push", "homeassistant", "aerodrome"
    WEATHER_PROVIDER: str = os.getenv("WEATHER_PROVIDER", "aerodrome")
    
    # Direct Ecowitt Gateway Local IP (GW1000/GW1100/GW2000/Wittboy)
    ECOWITT_IP: str = os.getenv("ECOWITT_IP", "")
    ECOWITT_PORT: int = int(os.getenv("ECOWITT_PORT", "80"))

    # Home Assistant (Alternative Ecowitt Integration)
    HASS_URL: str = os.getenv("HASS_URL", "http://homeassistant.local:8123")
    HASS_TOKEN: str = os.getenv("HASS_TOKEN", "")
    HASS_WIND_SPEED_ENTITY: str = os.getenv("HASS_WIND_SPEED", "sensor.ecowitt_wind_speed")
    HASS_WIND_DIR_ENTITY: str = os.getenv("HASS_WIND_DIR", "sensor.ecowitt_wind_direction")
    HASS_WIND_GUST_ENTITY: str = os.getenv("HASS_WIND_GUST", "sensor.ecowitt_wind_gust")
    HASS_TEMP_ENTITY: str = os.getenv("HASS_TEMP", "sensor.ecowitt_temperature")

    # NOAA / AviationWeather Aerodrome Stations
    METAR_STATIONS: str = os.getenv("METAR_STATIONS", "KNHK,2W6")
    METAR_POLL_INTERVAL_SEC: float = float(os.getenv("METAR_POLL_INTERVAL", "300.0"))

    # Physical / Chemical Emission Defaults (100LL AvGas)
    LEAD_CONTENT_GRAMS_PER_GALLON: float = 2.12  # ~0.56 g Pb / Liter
    PLUME_DISPERSION_HALF_ANGLE_DEG: float = 35.0 # Lateral plume dispersion corridor

    # Storage Paths
    DATABASE_PATH: Path = DATA_DIR / "alems.db"
    ICAO_DB_PATH: Path = DATA_DIR / "icao_types.json"
    EXPORTS_DIR: Path = BASE_DIR / "exports"

    # Web Server
    HOST: str = os.getenv("ALEMS_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("ALEMS_PORT", "8085"))

    def load_persisted(self) -> None:
        """Load user customized settings from data/config.json if present."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if hasattr(self, k) and v is not None:
                            setattr(self, k, v)
            except Exception as e:
                print(f"Warning: Failed to load {CONFIG_FILE}: {e}")

    def save_persisted(self, updates: Dict[str, Any]) -> None:
        """Update and persist settings to data/config.json."""
        current = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    current = json.load(f)
            except Exception:
                pass

        for k, v in updates.items():
            if hasattr(self, k) and v is not None:
                setattr(self, k, v)
                current[k] = v

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2)
        except Exception as e:
            print(f"Error persisting configuration: {e}")

    def to_clean_dict(self) -> Dict[str, Any]:
        """Return exportable dictionary of configuration settings."""
        keys = [
            "HOME_ADDRESS", "HOME_LAT", "HOME_LON", "HOME_ELEV_MSL_FT",
            "AIRPORT_ID", "AIRPORT_NAME", "AIRPORT_LAT", "AIRPORT_LON", "AIRPORT_ELEV_MSL_FT",
            "AIRPORT_RUNWAY_HEADING_11", "AIRPORT_RUNWAY_HEADING_29", "AIRPORT_RUNWAY_LENGTH_FT",
            "ACTIVE_MONITOR_RADIUS_NM", "FLYOVER_EVENT_RADIUS_NM", "MAX_TRACK_AGE_SECONDS",
            "READSB_URL", "READSB_HOST", "READSB_PORT", "READSB_PATH", "READSB_POLL_INTERVAL_SEC",
            "WEATHER_PROVIDER", "ECOWITT_IP", "ECOWITT_PORT",
            "HASS_URL", "HASS_TOKEN", "HASS_WIND_SPEED_ENTITY", "HASS_WIND_DIR_ENTITY", "HASS_WIND_GUST_ENTITY", "HASS_TEMP_ENTITY",
            "METAR_STATIONS", "METAR_POLL_INTERVAL_SEC",
            "LEAD_CONTENT_GRAMS_PER_GALLON", "PLUME_DISPERSION_HALF_ANGLE_DEG"
        ]
        return {k: getattr(self, k) for k in keys if hasattr(self, k)}

    def load_from_dict(self, data: Dict[str, Any]) -> List[str]:
        """Apply and persist dictionary of settings. Returns list of updated keys."""
        updated = []
        clean_updates = {}
        for k, v in data.items():
            key_upper = k.upper()
            if hasattr(self, key_upper) and v is not None:
                target_val = getattr(self, key_upper)
                target_type = type(target_val) if target_val is not None else str
                try:
                    casted = target_type(v)
                    clean_updates[key_upper] = casted
                    updated.append(key_upper)
                except Exception:
                    clean_updates[key_upper] = v
                    updated.append(key_upper)

        if clean_updates:
            self.save_persisted(clean_updates)
        return updated

config = Settings()
config.load_persisted()
config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
