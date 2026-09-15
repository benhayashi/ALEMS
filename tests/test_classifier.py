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
