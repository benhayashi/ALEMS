"""Configuration settings for Aerial Lead Exposure Monitoring System (ALEMS)."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
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

    # ADS-B Receiver Configuration (readsb on Pi 4)
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

config = Settings()
config.load_persisted()
config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
