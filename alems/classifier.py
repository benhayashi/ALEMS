"""Aircraft engine and fuel classification engine for ALEMS.
Identifies 100LL leaded-avgas-burning piston aircraft vs unleaded turbine/military traffic.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from alems.config import config

class AircraftClassifier:
    """Classifies aircraft by type, engine technology, and fuel lead emissions."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.ICAO_DB_PATH
        self.icao_db: Dict[str, Any] = {}
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
        """Load ICAO aircraft specifications database."""
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

    @staticmethod
    def hex_to_n_number(hex_code: str) -> Optional[str]:
        """Convert a standard US 24-bit ICAO Mode-S Hex to FAA N-number.
        US registrations occupy hex range A00001 to ADF7C7.
        """
        if not hex_code:
            return None
        hex_clean = hex_code.strip().upper()
        try:
            val = int(hex_clean, 16)
        except ValueError:
            return None

        # US civilian range
        base = 0xA00001
        max_val = 0xADF7C7
        if val < base or val > max_val:
            # Could be military or non-US
            if hex_clean.startswith("AE"):
                return "MIL-" + hex_clean
            return None

        offset = val - base

        # Digits and characters encoding per FAA Mode S algorithm
        CHAR_SET = "ABCDEFGHJKLMNPQRSTUVWXYZ" # 24 chars (no I or O)
        DIGIT_CHAR_SET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ" # 34 chars (no I, O)

        d1 = offset // 101711
        rem1 = offset % 101711
        digit1 = d1 + 1

        if rem1 == 0:
            return f"N{digit1}"

        rem1 -= 1
        d2 = rem1 // 10111
        rem2 = rem1 % 10111
        if d2 == 0:
            # 2nd position is empty
            pass

        # Full decoding table
        c1 = rem1 // 10111
        rem1 %= 10111
        if c1 == 0:
            c2 = rem1 // 951
            rem1 %= 951
            if c2 == 0:
                c3 = rem1 // 35
                rem1 %= 35
                if c3 == 0:
                    c4 = rem1
                    return f"N{digit1}{AircraftClassifier._char_or_empty(c4)}"
                return f"N{digit1}{AircraftClassifier._char_or_digit(c3)}{AircraftClassifier._char_or_empty(rem1)}"
            return f"N{digit1}{AircraftClassifier._char_or_digit(c2)}"

        # General algorithmic reconstruction
        # Fallback to standard offset breakdown
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

    @staticmethod
    def _char_or_empty(idx: int) -> str:
        CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        if 1 <= idx <= len(CHARS):
            return CHARS[idx - 1]
        return ""

    @staticmethod
    def _char_or_digit(idx: int) -> str:
        CHARS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        if 0 <= idx < len(CHARS):
            return CHARS[idx]
        return ""

    def classify(self, aircraft_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Classify aircraft given an ADS-B telemetry record."""
        icao_type = (aircraft_dict.get("t") or aircraft_dict.get("type") or "").strip().upper()
        flight = (aircraft_dict.get("flight") or "").strip().upper()
        reg = (aircraft_dict.get("r") or aircraft_dict.get("reg") or "").strip().upper()
        hex_code = (aircraft_dict.get("hex") or "").strip().upper()
        category = (aircraft_dict.get("category") or "").strip().upper()
        desc = (aircraft_dict.get("desc") or "").strip()

        # Derive tail number if missing
        if not reg and hex_code:
            derived_n = self.hex_to_n_number(hex_code)
            if derived_n:
                reg = derived_n

        # If callsign looks like an N-number
        if not reg and flight.startswith("N") and len(flight) <= 6:
            reg = flight

        # Check ICAO Database
        entry = self.icao_db.get(icao_type)
        if entry:
            res = dict(entry)
            res["icao_type"] = icao_type
            res["tail_number"] = reg
            res["hex"] = hex_code
            res["classification_source"] = "icao_database_exact"
            return res

        # Heuristic rules based on ADS-B category and description
        is_piston = False
        is_leaded = False
        engine_type = "Unknown"
        fuel_type = "Unknown"
        burn_rate = 10.0
        lead_content = 0.0

        # Military or high performance jet
        if hex_code.startswith("AE") or "MIL" in desc.upper() or category in ["A4", "A5"]:
            engine_type = "Jet / Military"
            fuel_type = "Jet-A"
            is_leaded = False
            burn_rate = 300.0
            classification_source = "military_jet_heuristic"
        # Light aircraft category (A1)
        elif category == "A1" or not category:
            # Common prefix heuristics:
            # C1 = Cessna Piston (C172, C182, C152), PA = Piper Piston, BE3/BE5 = Beech Piston, SR = Cirrus
            if any(icao_type.startswith(p) for p in ["C1", "PA2", "PA3", "SR2", "BE3", "BE5", "AA5", "RV", "M20"]):
                engine_type = "Piston"
                fuel_type = "100LL"
                is_leaded = True
                burn_rate = 11.0
                lead_content = config.LEAD_CONTENT_GRAMS_PER_GALLON
                classification_source = "type_prefix_piston_heuristic"
            elif any(icao_type.startswith(p) for p in ["PC", "BE2", "B35", "C208"]):
                engine_type = "Turboprop"
                fuel_type = "Jet-A"
                is_leaded = False
                burn_rate = 60.0
                classification_source = "type_prefix_turboprop_heuristic"
            elif any(icao_type.startswith(p) for p in ["C5", "C6", "E5", "LJ", "CL"]):
                engine_type = "Jet"
                fuel_type = "Jet-A"
                is_leaded = False
                burn_rate = 180.0
                classification_source = "type_prefix_jet_heuristic"
            else:
                # Default for unlisted local GA at small field: assume piston 100LL
                engine_type = "Piston"
                fuel_type = "100LL"
                is_leaded = True
                burn_rate = 10.0
                lead_content = config.LEAD_CONTENT_GRAMS_PER_GALLON
                classification_source = "ga_default_piston_assumption"
        else:
            engine_type = "Turbine/Commercial"
            fuel_type = "Jet-A"
            is_leaded = False
            burn_rate = 150.0
            classification_source = "category_turbine_heuristic"

        return {
            "icao_type": icao_type or "GA-PISTON",
            "model_name": desc or (f"{icao_type} Aircraft" if icao_type else "Light Aircraft"),
            "manufacturer": "General Aviation",
            "engine_type": engine_type,
            "engine_count": 1,
            "fuel_type": fuel_type,
            "burn_rate_gph": burn_rate,
            "is_leaded": is_leaded,
            "lead_content_g_per_gal": lead_content,
            "tail_number": reg,
            "hex": hex_code,
            "classification_source": classification_source
        }

classifier = AircraftClassifier()
