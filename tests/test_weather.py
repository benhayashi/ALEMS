import pytest
from unittest.mock import patch
from alems.collectors.weather_client import WeatherCollector, degrees_to_cardinal
from alems.config import config

def test_degrees_to_cardinal():
    assert degrees_to_cardinal(0) == "N"
    assert degrees_to_cardinal(360) == "N"
    assert degrees_to_cardinal(90) == "E"
    assert degrees_to_cardinal(180) == "S"
    assert degrees_to_cardinal(210) == "SSW"
    assert degrees_to_cardinal(270) == "W"
    assert degrees_to_cardinal(None) == "VRB"
    assert degrees_to_cardinal("VRB") == "VRB"
    assert degrees_to_cardinal("CALM") == "VRB"

def test_effective_wind_aerodrome_fallback():
    collector = WeatherCollector()
    
    mock_aerodrome = {
        "source": "aerodrome_metar",
        "station": "KNHK",
        "station_name": "Patuxent River NAS",
        "wind_speed_kts": 7.0,
        "wind_speed_mph": 8.1,
        "wind_gust_kts": 10.0,
        "wind_gust_mph": 11.5,
        "wind_dir_deg": 210.0,
        "wind_dir_text": "210°",
        "temp_c": 23.3,
        "temp_f": 74.0,
        "raw_metar": "KNHK 161452Z 21007KT 10SM CLR 23/16 A3002",
        "status": "live"
    }

    with patch.object(collector, "fetch_aerodrome_metar", return_value=mock_aerodrome):
        with patch.object(config, "WEATHER_PROVIDER", "aerodrome"):
            res = collector.get_effective_wind()
            
            assert res["is_ecowitt_connected"] is False
            assert res["active_source"] == "aerodrome_metar"
            assert res["effective_wind_speed_mph"] == 8.1
            assert res["effective_wind_dir_deg"] == 210.0
            assert res["effective_wind_cardinal"] == "SSW"
            assert res["plume_drift_dir_deg"] == 30.0
            assert res["plume_drift_cardinal"] == "NNE"
            assert res["ecowitt"]["status"] == "not_configured"
            assert res["aerodrome"]["raw_metar"] == "KNHK 161452Z 21007KT 10SM CLR 23/16 A3002"

def test_effective_wind_with_live_ecowitt():
    collector = WeatherCollector()
    
    mock_ecowitt = {
        "source": "ecowitt_local",
        "wind_speed_mph": 3.2,
        "wind_dir_deg": 190.0,
        "wind_gust_mph": 5.0,
        "temp_f": 72.5,
        "status": "live"
    }
    
    mock_aerodrome = {
        "source": "aerodrome_metar",
        "station": "KNHK",
        "wind_speed_kts": 8.0,
        "wind_speed_mph": 9.2,
        "wind_gust_kts": 12.0,
        "wind_gust_mph": 13.8,
        "wind_dir_deg": 220.0,
        "status": "live"
    }

    with patch.object(collector, "fetch_ecowitt_local_ip", return_value=mock_ecowitt):
        with patch.object(collector, "fetch_aerodrome_metar", return_value=mock_aerodrome):
            with patch.object(config, "WEATHER_PROVIDER", "ecowitt_local"):
                with patch.object(config, "ECOWITT_IP", "192.168.1.50"):
                    res = collector.get_effective_wind()
                    
                    assert res["is_ecowitt_connected"] is True
                    assert res["active_source"] == "ecowitt_ground"
                    assert res["effective_wind_speed_mph"] == 3.2
                    assert res["effective_wind_dir_deg"] == 220.0
                    assert res["plume_drift_dir_deg"] == 40.0
