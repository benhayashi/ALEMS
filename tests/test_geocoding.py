import pytest
from alems.geocoding import geocoding_service

def test_geocode_census_or_nominatim():
    res = geocoding_service.geocode_address("44081 Beaver Creek Dr, California, MD 20619")
    assert res is not None
    assert "lat" in res
    assert "lon" in res
    assert 38.0 < res["lat"] < 39.0
    assert -77.0 < res["lon"] < -76.0

def test_lookup_airport():
    apt = geocoding_service.lookup_airport("2W6")
    assert apt is not None
    assert apt["id"] == "2W6"
    assert "runway_heading_1" in apt
