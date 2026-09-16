"""Tests for aircraft and fuel classification."""

import pytest
from alems.classifier import classifier

def test_piston_classification():
    # Cessna 172
    res_c172 = classifier.classify({"t": "C172", "flight": "N172SP", "hex": "A1B2C3"})
    assert res_c172["is_leaded"] is True
    assert res_c172["fuel_type"] == "100LL"
    assert res_c172["engine_type"] == "Piston"
    assert res_c172["lead_content_g_per_gal"] == 2.12

    # Piper PA-28
    res_pa28 = classifier.classify({"t": "PA28", "flight": "N2842W", "hex": "A4D89E"})
    assert res_pa28["is_leaded"] is True
    assert res_pa28["fuel_type"] == "100LL"

    # Cirrus SR22
    res_sr22 = classifier.classify({"t": "SR22", "flight": "N224SR", "hex": "A5F331"})
    assert res_sr22["is_leaded"] is True
    assert res_sr22["burn_rate_gph"] > 15.0

def test_turbine_classification():
    # Pilatus PC-12
    res_pc12 = classifier.classify({"t": "PC12", "flight": "N120PC", "hex": "A79F21"})
    assert res_pc12["is_leaded"] is False
    assert res_pc12["fuel_type"] == "Jet-A"
    assert res_pc12["engine_type"] == "Turboprop"
    assert res_pc12["lead_content_g_per_gal"] == 0.0

    # F/A-18 (Military traffic from Pax River)
    res_f18 = classifier.classify({"t": "F18", "flight": "NAVY101", "hex": "AE0123"})
    assert res_f18["is_leaded"] is False
    assert res_f18["fuel_type"] == "Jet-A"

def test_hex_to_n_number():
    # A00001 is N1
    assert classifier.hex_to_n_number("A00001") == "N1"

def test_high_altitude_invariants():
    # Aircraft cruising at 35,000 ft with no type tag
    res_high = classifier.classify({"hex": "A364E7", "alt_baro": 35000, "gs": 450})
    assert res_high["is_leaded"] is False
    assert res_high["fuel_type"] == "Jet-A"
    assert "High-Altitude" in res_high["engine_type"] or "Jet" in res_high["engine_type"]
    assert res_high["lead_content_g_per_gal"] == 0.0

def test_high_speed_override():
    # Aircraft cruising at 320 kts at 8,000 ft with no type tag
    res_fast = classifier.classify({"hex": "A88888", "alt_baro": 8000, "gs": 320})
    assert res_fast["is_leaded"] is False
    assert res_fast["fuel_type"] == "Jet-A"

def test_airline_callsign_heuristic():
    # Commercial airline callsign (AAL, DAL, SWA, etc.)
    res_airline = classifier.classify({"flight": "AAL1234", "alt_baro": 8000, "gs": 220})
    assert res_airline["is_leaded"] is False
    assert res_airline["fuel_type"] == "Jet-A"

def test_hex_registry_lookup():
    # Mode-S hex AB184D -> N814AW, Airbus A319
    res_reg = classifier.classify({"hex": "AB184D", "alt_baro": 10000, "gs": 230})
    assert res_reg["tail_number"] == "N814AW"
    assert res_reg["icao_type"] == "A319"
    assert res_reg["is_leaded"] is False
    assert res_reg["fuel_type"] == "Jet-A"

def test_unlisted_low_slow_ga_fallback():
    # Unlisted civilian aircraft flying low and slow (1,500 ft, 90 kts)
    res_ga = classifier.classify({"hex": "A99999", "alt_baro": 1500, "gs": 90})
    assert res_ga["is_leaded"] is True
    assert res_ga["fuel_type"] == "100LL"
    assert res_ga["engine_type"] == "Piston"
