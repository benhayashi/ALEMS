"""Tests for geodesy calculations."""

import pytest
from alems.geodesy import (
    haversine_distance_m,
    distance_nm,
    distance_ft,
    initial_bearing,
    calculate_3d_slant_range_ft,
    calculate_cpa
)

def test_distance_and_bearing():
    # 2W6 coordinates: 38.3154, -76.5501
    # 44081 Beaver Creek Dr: 38.2720, -76.4950
    dist_m = haversine_distance_m(38.3154, -76.5501, 38.2720, -76.4950)
    dist_nmi = distance_nm(38.3154, -76.5501, 38.2720, -76.4950)
    dist_feet = distance_ft(38.3154, -76.5501, 38.2720, -76.4950)

    # Expected approx 6.8 km (~3.68 NM, ~22,350 ft)
    assert 6500 < dist_m < 7100
    assert 3.5 < dist_nmi < 3.9
    assert 21000 < dist_feet < 23500

    brg = initial_bearing(38.3154, -76.5501, 38.2720, -76.4950)
    # Expected southeast (~135 degrees)
    assert 130 < brg < 140

def test_slant_range():
    # 3000 ft horizontal, 1000 ft vertical AGL
    slant = calculate_3d_slant_range_ft(3000.0, 1000.0)
    expected = (3000**2 + 1000**2) ** 0.5
    assert abs(slant - expected) < 0.01

def test_cpa_calculation():
    home_lat = 38.2720
    home_lon = -76.4950
    home_elev = 110.0

    points = [
        {"lat": 38.2800, "lon": -76.4950, "alt_geom": 1110.0},
        {"lat": 38.2722, "lon": -76.4950, "alt_geom": 910.0},  # Closest
        {"lat": 38.2600, "lon": -76.4950, "alt_geom": 1110.0},
    ]

    cpa = calculate_cpa(points, home_lat, home_lon, home_elev)
    assert cpa is not None
    assert cpa["lat"] == 38.2722
    assert cpa["alt_agl_ft"] == 800.0
    assert cpa["min_slant_range_ft"] < 1000.0
