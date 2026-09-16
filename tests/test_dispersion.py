"""Tests for atmospheric dispersion and lead exposure risk calculations."""

import pytest
from alems.dispersion import dispersion_model
from alems.classifier import classifier

def test_wind_alignment():
    # Aircraft is west of house, so bearing from aircraft to house is 90° (due East)
    # Wind is blowing FROM 270° (West) -> Plume moves TOWARDS (270 + 180) % 360 = 90° (East)
    # Angular offset should be 0°, is_downwind should be True!
    offset, is_downwind = dispersion_model.calculate_wind_alignment(
        bearing_ac_to_house=90.0,
        wind_from_deg=270.0
    )
    assert offset == 0.0
    assert is_downwind is True

    # Opposite case: Wind blowing FROM 90° (East) -> Plume moves TOWARDS 270° (West)
    # Offset should be 180°, is_downwind should be False
    offset, is_downwind = dispersion_model.calculate_wind_alignment(
        bearing_ac_to_house=90.0,
        wind_from_deg=90.0
    )
    assert offset == 180.0
    assert is_downwind is False

def test_point_exposure_unleaded():
    meta_turbine = classifier.classify({"t": "PC12", "flight": "N120PC"})
    res = dispersion_model.calculate_point_exposure(
        lat=38.2725,
        lon=-76.4955,
        alt_msl_ft=1100.0,
        ground_speed_kts=110.0,
        vertical_rate_fpm=0.0,
        aircraft_meta=meta_turbine,
        wind_speed_mph=5.0,
        wind_dir_deg=270.0
    )
    assert res["is_leaded"] is False
    assert res["lead_emission_rate_g_s"] == 0.0
    assert res["exposure_score"] == 0.0

def test_point_exposure_leaded():
    meta_piston = classifier.classify({"t": "C172", "flight": "N172SP"})
    res = dispersion_model.calculate_point_exposure(
        lat=38.2722,
        lon=-76.4952,
        alt_msl_ft=800.0,
        ground_speed_kts=95.0,
        vertical_rate_fpm=500.0, # Climbing full throttle
        aircraft_meta=meta_piston,
        wind_speed_mph=8.0,
        wind_dir_deg=315.0,
        home_lat=38.2720,
        home_lon=-76.4950,
        home_elev_ft=110.0
    )
    assert res["is_leaded"] is True
    assert res["lead_emission_rate_mg_s"] > 5.0 # ~5.5 mg/s
    assert res["exposure_score"] > 0.0
