"""Tests for 100LL Exposure Heatmap data aggregation and API endpoint."""

import pytest
from fastapi.testclient import TestClient
from alems.server import app
from alems.storage.db import db
from alems.config import config

@pytest.fixture
def client():
    return TestClient(app)

def test_get_exposure_heatmap_points_database():
    data = db.get_exposure_heatmap_points(time_range="all", radius_nm=15.0)
    assert isinstance(data, dict)
    assert "points" in data
    assert "count" in data
    assert "time_range" in data
    assert "radius_nm" in data
    assert "center" in data
    assert data["radius_nm"] == 15.0
    assert data["time_range"] == "all"
    assert isinstance(data["points"], list)

    for pt in data["points"]:
        assert len(pt) == 3
        lat, lon, intensity = pt
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0
        assert 0.0 <= intensity <= 1.0

def test_api_exposure_heatmap_endpoint(client):
    res = client.get("/api/exposure/heatmap?time_range=24h&radius_nm=10")
    assert res.status_code == 200
    body = res.json()
    assert "points" in body
    assert "count" in body
    assert body["time_range"] == "24h"
    assert body["radius_nm"] == 10.0
    assert "center" in body
    assert "lat" in body["center"]
    assert "lon" in body["center"]

def test_api_config_heatmap_radius(client):
    # Verify GET /api/config returns heatmap_radius_nm in thresholds
    res = client.get("/api/config")
    assert res.status_code == 200
    cfg = res.json()
    assert "heatmap_radius_nm" in cfg["thresholds"]

    # Verify POST /api/config can update heatmap_radius_nm
    update_res = client.post("/api/config", json={"heatmap_radius_nm": 12.5})
    assert update_res.status_code == 200
    updated_cfg = update_res.json()["config"]
    assert updated_cfg["thresholds"]["heatmap_radius_nm"] == 12.5

    # Reset back to 10.0
    client.post("/api/config", json={"heatmap_radius_nm": 10.0})

def test_api_exposure_heatmap_center_selection(client):
    # Test property center
    res_prop = client.get("/api/exposure/heatmap?center_type=property&radius_nm=8.0")
    assert res_prop.status_code == 200
    data_prop = res_prop.json()
    assert data_prop["center_type"] == "property"
    assert round(data_prop["center"]["lat"], 2) == round(config.HOME_LAT, 2)
    assert round(data_prop["center"]["lon"], 2) == round(config.HOME_LON, 2)

    # Test custom center coords
    res_custom = client.get("/api/exposure/heatmap?center_lat=38.35&center_lon=-76.50&radius_nm=5.0")
    assert res_custom.status_code == 200
    data_custom = res_custom.json()
    assert round(data_custom["center"]["lat"], 2) == 38.35
    assert round(data_custom["center"]["lon"], 2) == -76.50

