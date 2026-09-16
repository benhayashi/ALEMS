"""Aircraft engine and fuel classification engine for ALEMS.
Identifies 100LL leaded-avgas-burning piston aircraft vs unleaded turbine/military traffic.
Incorporates 440,000+ Mode-S hex registry lookups, 2,700+ ICAO aircraft type definitions,
and aerodynamic/physical flight level invariants (altitude, airspeed, airline callsigns).
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
from alems.config import config, DATA_DIR
from alems.storage.db import db

# Commercial airline flight number pattern (e.g. AAL2641, DAL123, SWA1904, JIA5124, RPA4512)
AIRLINE_FLIGHT_PATTERN = re.compile(r"^[A-Z]{3}\d{1,4}[A-Z]?$")

# Military / Government callsign prefixes
MIL_CALLSIGN_PATTERN = re.compile(
    r"^(PAT|NAVY|RCH|REACH|TOPCAT|SCORE|WATER|TEST|AF|AIRFORCE|GUARD|CG|JEDI|DOOM|SNIPER|VADER|DEATH|WIZARD|ATTACK|BOMBER)\d*",
    re.IGNORECASE
)

class AircraftClassifier:
    """Classifies aircraft by type, engine technology, and fuel lead emissions."""

    def __init__(self, db_path: Optional[Path] = None, readsb_types_path: Optional[Path] = None):
        self.db_path = db_path or (DATA_DIR / "icao_types.json")
        self.readsb_types_path = readsb_types_path or (DATA_DIR / "readsb_types.json")
        self.icao_db: Dict[str, Any] = {}
        self.readsb_types: Dict[str, list] = {}
        self._hex_cache: Dict[str, Optional[Dict[str, str]]] = {}

        self.default_piston = {
            "engine_type": "Piston",
            "engine_count": 1,
            "fuel_type": "100LL",
            "burn_rate_gph": 10.5,
            "is_leaded": True,
            "lead_content_g_per_gal": config.LEAD_CONTENT_GRAMS_PER_GALLON
        }
        self.default_turboprop = {
            "engine_type": "Turboprop",
            "engine_count": 1,
            "fuel_type": "Jet-A",
            "burn_rate_gph": 50.0,
            "is_leaded": False,
            "lead_content_g_per_gal": 0.0
        }
        self.default_jet = {
            "engine_type": "Jet",
            "engine_count": 2,
            "fuel_type": "Jet-A",
            "burn_rate_gph": 180.0,
            "is_leaded": False,
            "lead_content_g_per_gal": 0.0
        }
        self._load_database()

    def _load_database(self) -> None:
        """Load ICAO aircraft specifications database and readsb type definitions."""
        if self.db_path and self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.icao_db = data.get("aircraft", {})
                    self.default_piston = data.get("default_piston", self.default_piston)
                    self.default_turboprop = data.get("default_turboprop", self.default_turboprop)
                    self.default_jet = data.get("default_jet", self.default_jet)
            except Exception as e:
                print(f"Warning: Failed to load ICAO database from {self.db_path}: {e}")

        if self.readsb_types_path and self.readsb_types_path.exists():
            try:
                with open(self.readsb_types_path, "r", encoding="utf-8") as f:
                    self.readsb_types = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load readsb types from {self.readsb_types_path}: {e}")

    @staticmethod
    def hex_to_n_number(hex_code: str) -> Optional[str]:
        """Convert a standard US 24-bit ICAO Mode-S Hex to FAA N-number."""
        if not hex_code:
            return None
        hex_clean = hex_code.strip().upper()
        try:
            val = int(hex_clean, 16)
        except ValueError:
            return None

        base = 0xA00001
        max_val = 0xADF7C7
        if val < base or val > max_val:
            if hex_clean.startswith("AE"):
                return "MIL-" + hex_clean
            return None

        offset = val - base
        d1 = offset // 101711
        rem1 = offset % 101711
        digit1 = d1 + 1

        if rem1 == 0:
            return f"N{digit1}"

        rem1 -= 1
        n_num = f"N{digit1}"
        d2 = rem1 // 10111
        rem2 = rem1 % 10111
        n_num += str(d2)

        d3 = rem2 // 951
        rem3 = rem2 % 951
        if rem3 == 0:
            return n_num + (str(d3) if d3 < 10 else "")

        d4 = rem3 // 35
        rem4 = rem3 % 35
        if d3 < 10:
            n_num += str(d3)
        if d4 < 10:
            n_num += str(d4)
        return n_num

    def classify(self, aircraft_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Classify aircraft given an ADS-B telemetry record."""
        icao_type = (aircraft_dict.get("t") or aircraft_dict.get("type") or aircraft_dict.get("aircraft_type") or "").strip().upper()
        flight = (aircraft_dict.get("flight") or "").strip().upper()
        reg = (aircraft_dict.get("r") or aircraft_dict.get("reg") or aircraft_dict.get("tail_number") or "").strip().upper()
        hex_code = (aircraft_dict.get("hex") or "").strip().upper()
        category = (aircraft_dict.get("category") or "").strip().upper()
        desc = (aircraft_dict.get("desc") or aircraft_dict.get("model_name") or "").strip()

        # Telemetry dynamics for physical verification
        alt = aircraft_dict.get("alt_msl_ft") or aircraft_dict.get("alt_geom") or aircraft_dict.get("alt_baro") or aircraft_dict.get("cpa_alt_msl_ft")
        try:
            alt_val = float(alt) if alt is not None else None
        except (ValueError, TypeError):
            alt_val = None

        gs = aircraft_dict.get("gs") or aircraft_dict.get("cpa_ground_speed_kts")
        try:
            gs_val = float(gs) if gs is not None else None
        except (ValueError, TypeError):
            gs_val = None

        # 1. Mode-S Hex Database Lookup (Local SQLite Registry)
        if hex_code and (not reg or not icao_type or reg.startswith("MIL-") or reg.startswith("N")):
            if hex_code in self._hex_cache:
                rec = self._hex_cache[hex_code]
            else:
                rec = db.lookup_aircraft_hex(hex_code)
                self._hex_cache[hex_code] = rec

            if rec:
                if rec.get("reg") and (not reg or reg.startswith("MIL-") or len(reg) < len(rec["reg"])):
                    reg = rec["reg"].strip().upper()
                if rec.get("icao_type") and not icao_type:
                    icao_type = rec["icao_type"].strip().upper()

        # Fallback tail number heuristics
        if not reg and hex_code:
            derived_n = self.hex_to_n_number(hex_code)
            if derived_n:
                reg = derived_n

        if not reg and flight.startswith("N") and len(flight) <= 6:
            reg = flight

        # Classification fields to resolve
        model_name = desc
        manufacturer = "General Aviation"
        engine_type = None
        engine_count = 1
        fuel_type = None
        burn_rate = None
        is_leaded = None
        lead_content = 0.0
        classification_source = "unknown"

        # 2. Check Curated ICAO Database (detailed GA parameters)
        if icao_type and icao_type in self.icao_db:
            entry = dict(self.icao_db[icao_type])
            model_name = entry.get("model_name", model_name)
            manufacturer = entry.get("manufacturer", manufacturer)
            engine_type = entry.get("engine_type")
            engine_count = entry.get("engine_count", 1)
            fuel_type = entry.get("fuel_type")
            burn_rate = entry.get("burn_rate_gph")
            is_leaded = entry.get("is_leaded")
            lead_content = entry.get("lead_content_g_per_gal", 0.0)
            classification_source = "curated_icao_database"

        # 3. Check Comprehensive readsb Types Database (2,700+ standard ICAO types)
        elif icao_type and icao_type in self.readsb_types:
            type_info = self.readsb_types[icao_type]
            # Format: [full_name, engine_code (e.g. 'L2J', 'L1P', 'L2T', 'H1T'), wake_turb]
            model_name = type_info[0]
            eng_code = type_info[1] if len(type_info) > 1 else ""

            eng_kind = eng_code[2].upper() if len(eng_code) >= 3 else (eng_code[-1].upper() if eng_code else "P")
            eng_cnt = int(eng_code[1]) if len(eng_code) >= 2 and eng_code[1].isdigit() else 1
            engine_count = eng_cnt

            if eng_kind == "P":
                engine_type = "Piston"
                fuel_type = "100LL"
                is_leaded = True
                burn_rate = 10.5 * eng_cnt
                lead_content = config.LEAD_CONTENT_GRAMS_PER_GALLON
            elif eng_kind == "T":
                engine_type = "Turboprop"
                fuel_type = "Jet-A"
                is_leaded = False
                burn_rate = 45.0 * eng_cnt
                lead_content = 0.0
            elif eng_kind == "J":
                engine_type = "Jet"
                fuel_type = "Jet-A"
                is_leaded = False
                burn_rate = 120.0 * eng_cnt
                lead_content = 0.0
            elif eng_kind == "E":
                engine_type = "Electric"
                fuel_type = "Electric"
                is_leaded = False
                burn_rate = 0.0
                lead_content = 0.0
            else:
                engine_type = "Turbine"
                fuel_type = "Jet-A"
                is_leaded = False
                burn_rate = 100.0
                lead_content = 0.0

            classification_source = "readsb_types_database"

        # 4. Invariant Physical & Operational Overrides (Aeronautical Rules)

        # Rule A: Extreme Altitude Override (Physics Invariant)
        # Reciprocating GA piston aircraft do not operate above FL250 (25,000 ft).
        if alt_val is not None and alt_val > 25000.0:
            engine_type = "Jet / High-Altitude Turbine"
            fuel_type = "Jet-A"
            is_leaded = False
            lead_content = 0.0
            burn_rate = max(burn_rate or 0.0, 180.0)
            if not icao_type:
                icao_type = "HIGH-ALT-JET"
                model_name = f"High-Altitude Jet ({flight or hex_code})"
            classification_source = "physics_high_altitude_override"

        # Rule B: High Speed Override
        # Piston aircraft cannot sustain cruise speeds > 240 kts.
        elif gs_val is not None and gs_val > 240.0 and (is_leaded is True or is_leaded is None):
            engine_type = "Turbine / High-Speed"
            fuel_type = "Jet-A"
            is_leaded = False
            lead_content = 0.0
            burn_rate = max(burn_rate or 0.0, 120.0)
            if not icao_type:
                icao_type = "TURBINE-JET"
                model_name = f"High-Speed Turbine ({flight or hex_code})"
            classification_source = "physics_high_speed_override"

        # Rule C: Commercial Airline Callsign Pattern
        elif flight and AIRLINE_FLIGHT_PATTERN.match(flight) and (is_leaded is True or is_leaded is None):
            engine_type = "Jet / Commercial Airline"
            fuel_type = "Jet-A"
            is_leaded = False
            lead_content = 0.0
            burn_rate = max(burn_rate or 0.0, 150.0)
            if not icao_type:
                icao_type = "AIRLINER"
                model_name = f"Commercial Airline ({flight})"
            classification_source = "airline_callsign_heuristic"

        # Rule D: Military Callsigns and US Military Hex Range
        elif hex_code.startswith("AE") or (flight and MIL_CALLSIGN_PATTERN.match(flight)) or "MIL" in desc.upper() or category in ["A4", "A5"]:
            engine_type = "Jet / Military Turbine"
            fuel_type = "Jet-A"
            is_leaded = False
            lead_content = 0.0
            burn_rate = max(burn_rate or 0.0, 250.0)
            if not icao_type:
                icao_type = "MIL-TURBINE"
                model_name = f"Military Aircraft ({flight or hex_code})"
            classification_source = "military_heuristic"

        # 5. Type Prefix Heuristics (if type code exists but wasn't in databases)
        if engine_type is None:
            if any(icao_type.startswith(p) for p in ["C1", "PA2", "PA3", "SR2", "BE3", "BE5", "AA5", "RV", "M20", "DA4", "DA2"]):
                engine_type = "Piston"
                fuel_type = "100LL"
                is_leaded = True
                burn_rate = 11.0
                lead_content = config.LEAD_CONTENT_GRAMS_PER_GALLON
                classification_source = "type_prefix_piston_heuristic"
            elif any(icao_type.startswith(p) for p in ["PC", "BE2", "B35", "C208", "DH8", "AT7"]):
                engine_type = "Turboprop"
                fuel_type = "Jet-A"
                is_leaded = False
                burn_rate = 60.0
                classification_source = "type_prefix_turboprop_heuristic"
            elif any(icao_type.startswith(p) for p in ["C5", "C6", "E5", "LJ", "CL", "B7", "A3", "E1", "E7", "CRJ", "FA"]):
                engine_type = "Jet"
                fuel_type = "Jet-A"
                is_leaded = False
                burn_rate = 180.0
                classification_source = "type_prefix_jet_heuristic"

        # 6. Fallback for Unlisted Aircraft
        if engine_type is None:
            # Only assume 100LL GA Piston if flying low and slow (typical GA operating envelope)
            if (alt_val is None or alt_val <= 14000.0) and (gs_val is None or gs_val <= 200.0):
                engine_type = "Piston"
                fuel_type = "100LL"
                is_leaded = True
                burn_rate = 10.5
                lead_content = config.LEAD_CONTENT_GRAMS_PER_GALLON
                classification_source = "ga_low_slow_piston_assumption"
                if not icao_type:
                    icao_type = "GA-PISTON"
                if not model_name:
                    model_name = "Light GA Aircraft"
            else:
                engine_type = "Turbine"
                fuel_type = "Jet-A"
                is_leaded = False
                lead_content = 0.0
                burn_rate = 150.0
                classification_source = "enroute_turbine_assumption"
                if not icao_type:
                    icao_type = "TURBINE"
                if not model_name:
                    model_name = f"Turbine Aircraft ({flight or hex_code})"

        return {
            "icao_type": icao_type or "UNKNOWN",
            "model_name": model_name or (f"{icao_type} Aircraft" if icao_type else "Aircraft"),
            "manufacturer": manufacturer,
            "engine_type": engine_type,
            "engine_count": engine_count,
            "fuel_type": fuel_type,
            "burn_rate_gph": burn_rate or 10.5,
            "is_leaded": bool(is_leaded),
            "lead_content_g_per_gal": lead_content,
            "tail_number": reg or hex_code,
            "hex": hex_code,
            "classification_source": classification_source
        }

classifier = AircraftClassifier()
