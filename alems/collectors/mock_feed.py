"""Realistic 2W6 traffic pattern flight and weather simulator for ALEMS.
Simulates piston aircraft (C172, PA28, BE58) flying 2W6 Runway 11/29 patterns over Beaver Creek Dr,
alongside unleaded turbine controls (PC-12).
"""

import math
import time
from typing import List, Dict, Any
from alems.config import config

class MockFlightSimulator:
    """Generates realistic ADS-B kinematics for local 2W6 traffic."""

    def __init__(self):
        self.step_counter = 0
        # Simulated aircraft instances with distinct flight plans
        self.flights = [
            {
                "hex": "A1B2C3",
                "flight": "N172SP",
                "r": "N172SP",
                "t": "C172",
                "desc": "Cessna 172S Skyhawk",
                "category": "A1",
                "phase": "pattern_touch_and_go",
                "speed_kts": 105.0,
                "alt_base": 1100.0,
                "radius_nm": 1.2,
                "center_lat": 38.293,
                "center_lon": -76.522,
                "angle_deg": 0.0,
                "delta_angle": 1.8
            },
            {
                "hex": "A4D89E",
                "flight": "N2842W",
                "r": "N2842W",
                "t": "PA28",
                "desc": "Piper PA-28-181 Archer III",
                "category": "A1",
                "phase": "runway_11_departure",
                "lat": 38.315,
                "lon": -76.550,
                "alt": 150.0,
                "climb_rate": 650.0,
                "speed_kts": 85.0,
                "heading": 112.0
            },
            {
                "hex": "A79F21",
                "flight": "N120PC",
                "r": "N120PC",
                "t": "PC12",
                "desc": "Pilatus PC-12 NG (Turboprop)",
                "category": "A2",
                "phase": "straight_in_approach",
                "lat": 38.240,
                "lon": -76.450,
                "alt": 1800.0,
                "descent_rate": -500.0,
                "speed_kts": 140.0,
                "heading": 292.0
            }
        ]

    def get_aircraft_snapshot(self) -> List[Dict[str, Any]]:
        """Advance simulated flights by 1 second and return readsb formatted objects."""
        self.step_counter += 1
        now_ts = time.time()
        active_aircraft: List[Dict[str, Any]] = []

        # 1. C172 flying standard pattern (elliptical orbit traversing near Beaver Creek Dr)
        f1 = self.flights[0]
        f1["angle_deg"] = (f1["angle_deg"] + f1["delta_angle"]) % 360.0
        rad = math.radians(f1["angle_deg"])
        # Elliptical pattern aligned with Runway 11/29 (110 deg)
        semi_major = 0.035
        semi_minor = 0.015
        f1_lat = f1["center_lat"] + semi_minor * math.sin(rad)
        f1_lon = f1["center_lon"] + semi_major * math.cos(rad)
        f1_track = (f1["angle_deg"] + 90.0) % 360.0
        alt_variation = 1000.0 + 80.0 * math.sin(rad * 2)

        active_aircraft.append({
            "hex": f1["hex"],
            "flight": f1["flight"],
            "r": f1["r"],
            "t": f1["t"],
            "desc": f1["desc"],
            "category": f1["category"],
            "lat": round(f1_lat, 6),
            "lon": round(f1_lon, 6),
            "alt_baro": round(alt_variation, 0),
            "alt_geom": round(alt_variation + 25.0, 0),
            "gs": f1["speed_kts"],
            "track": round(f1_track, 1),
            "baro_rate": round(50.0 * math.cos(rad), 0),
            "seen": 0.1,
            "rssi": -14.2
        })

        # 2. PA-28 climbing out from Runway 11 right past Beaver Creek Dr
        f2 = self.flights[1]
        dt_hrs = 1.0 / 3600.0
        dist_nm = f2["speed_kts"] * dt_hrs
        hdg_rad = math.radians(f2["heading"])
        dlat = (dist_nm / 60.0) * math.cos(hdg_rad)
        dlon = (dist_nm / (60.0 * math.cos(math.radians(f2["lat"])))) * math.sin(hdg_rad)
        f2["lat"] += dlat
        f2["lon"] += dlon
        f2["alt"] += (f2["climb_rate"] / 60.0)

        # Reset departure flight once it clears out past 4 NM
        if f2["alt"] > 2500.0 or f2["lon"] > -76.44:
            f2["lat"] = 38.315
            f2["lon"] = -76.550
            f2["alt"] = 150.0

        active_aircraft.append({
            "hex": f2["hex"],
            "flight": f2["flight"],
            "r": f2["r"],
            "t": f2["t"],
            "desc": f2["desc"],
            "category": f2["category"],
            "lat": round(f2["lat"], 6),
            "lon": round(f2["lon"], 6),
            "alt_baro": round(f2["alt"], 0),
            "alt_geom": round(f2["alt"] + 30.0, 0),
            "gs": f2["speed_kts"],
            "track": f2["heading"],
            "baro_rate": f2["climb_rate"],
            "seen": 0.1,
            "rssi": -11.5
        })

        # 3. PC-12 Turboprop on straight-in approach
        f3 = self.flights[2]
        dist_nm3 = f3["speed_kts"] * dt_hrs
        hdg_rad3 = math.radians(f3["heading"])
        dlat3 = (dist_nm3 / 60.0) * math.cos(hdg_rad3)
        dlon3 = (dist_nm3 / (60.0 * math.cos(math.radians(f3["lat"])))) * math.sin(hdg_rad3)
        f3["lat"] += dlat3
        f3["lon"] += dlon3
        f3["alt"] += (f3["descent_rate"] / 60.0)

        if f3["alt"] < 200.0 or f3["lon"] < -76.54:
            f3["lat"] = 38.240
            f3["lon"] = -76.450
            f3["alt"] = 1800.0

        active_aircraft.append({
            "hex": f3["hex"],
            "flight": f3["flight"],
            "r": f3["r"],
            "t": f3["t"],
            "desc": f3["desc"],
            "category": f3["category"],
            "lat": round(f3["lat"], 6),
            "lon": round(f3["lon"], 6),
            "alt_baro": round(f3["alt"], 0),
            "alt_geom": round(f3["alt"] + 15.0, 0),
            "gs": f3["speed_kts"],
            "track": f3["heading"],
            "baro_rate": f3["descent_rate"],
            "seen": 0.2,
            "rssi": -18.0
        })

        return active_aircraft

mock_simulator = MockFlightSimulator()
