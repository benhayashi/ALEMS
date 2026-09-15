"""Geodesic and spatial coordinate calculations for ALEMS."""

import math
from typing import Tuple, List, Dict, Any, Optional

EARTH_RADIUS_M = 6371008.8  # WGS-84 mean earth radius in meters
METERS_TO_FEET = 3.280839895013123
FEET_TO_METERS = 0.3048
METERS_TO_NM = 0.0005399568034557235
NM_TO_METERS = 1852.0

def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_M * c

def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in Nautical Miles (NM)."""
    return haversine_distance_m(lat1, lon1, lat2, lon2) * METERS_TO_NM

def distance_ft(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in Feet."""
    return haversine_distance_m(lat1, lon1, lat2, lon2) * METERS_TO_FEET

def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the initial bearing (forward azimuth) from point 1 to point 2 in degrees (0-360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = (math.cos(phi1) * math.sin(phi2) -
         math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda))
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return bearing

def calculate_3d_slant_range_ft(horizontal_dist_ft: float, altitude_agl_ft: float) -> float:
    """Calculate 3D Euclidean distance (slant range) in feet from receptor to aircraft."""
    return math.sqrt(horizontal_dist_ft ** 2 + max(0.0, altitude_agl_ft) ** 2)

def calculate_cpa(
    points: List[Dict[str, Any]],
    home_lat: float,
    home_lon: float,
    home_elev_ft: float
) -> Optional[Dict[str, Any]]:
    """Analyze a series of trajectory points to find the Closest Point of Approach (CPA).
    Returns point at CPA augmented with distance, bearing, and slant range.
    """
    if not points:
        return None

    best_point = None
    min_slant_range = float("inf")

    for pt in points:
        lat = pt.get("lat")
        lon = pt.get("lon")
        if lat is None or lon is None:
            continue

        alt_msl = pt.get("alt_geom") or pt.get("alt_baro") or 1000.0
        alt_agl = max(0.0, float(alt_msl) - home_elev_ft)
        h_dist_ft = distance_ft(lat, lon, home_lat, home_lon)
        slant_range = calculate_3d_slant_range_ft(h_dist_ft, alt_agl)

        if slant_range < min_slant_range:
            min_slant_range = slant_range
            best_point = dict(pt)
            best_point["min_horiz_dist_ft"] = round(h_dist_ft, 1)
            best_point["min_horiz_dist_nm"] = round(h_dist_ft / 6076.12, 3)
            best_point["min_slant_range_ft"] = round(slant_range, 1)
            best_point["alt_agl_ft"] = round(alt_agl, 1)
            best_point["bearing_from_house"] = round(initial_bearing(home_lat, home_lon, lat, lon), 1)
            best_point["bearing_to_house"] = round(initial_bearing(lat, lon, home_lat, home_lon), 1)

    return best_point
