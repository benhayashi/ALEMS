"""Tests for Database and Configuration Backup, Export, and Restore."""

import pytest
import tempfile
import zipfile
import yaml
from pathlib import Path
from fastapi.testclient import TestClient

from alems.server import app
from alems.storage.db import Database
from alems.config import Settings

client = TestClient(app)

def test_database_snapshot_and_inspect():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        test_db = Database(db_path=db_path)
        
        snap_path = Path(tmpdir) / "snapshot.db"
        test_db.export_snapshot(snap_path)
        assert snap_path.exists()
        assert snap_path.stat().st_size > 0
        
        info = test_db.inspect_database_file(snap_path)
        assert info["valid"] is True
        assert "flyover_events" in info["tables"]
        assert "aircraft_registry" in info["tables"]

def test_settings_to_dict_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = Settings()
        d = cfg.to_clean_dict()
        assert "HOME_LAT" in d
        assert "DATABASE_PATH" not in d  # machine-specific internal paths excluded
        
        # Test loading modified dict
        updated = cfg.load_from_dict({"ACTIVE_MONITOR_RADIUS_NM": 2.2})
        assert "ACTIVE_MONITOR_RADIUS_NM" in updated
        assert cfg.ACTIVE_MONITOR_RADIUS_NM == 2.2

def test_api_backup_bundle_and_inspect():
    # 1. Export bundle
    res = client.get("/api/backup/bundle")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    
    # 2. Inspect bundle
    files = {"file": ("bundle.zip", res.content, "application/zip")}
    insp_res = client.post("/api/backup/inspect", files=files)
    assert insp_res.status_code == 200
    data = insp_res.json()
    assert data["type"] == "bundle_zip"
    assert data["has_database"] is True
    assert data["has_config"] is True

def test_api_backup_database_and_config():
    # DB export
    db_res = client.get("/api/backup/database")
    assert db_res.status_code == 200
    assert len(db_res.content) > 1000
    
    # Config YAML export
    cfg_res = client.get("/api/backup/config?format=yaml")
    assert cfg_res.status_code == 200
    parsed = yaml.safe_load(cfg_res.content)
    assert "HOME_LAT" in parsed
    
    # Config JSON export
    cfg_json = client.get("/api/backup/config?format=json")
    assert cfg_json.status_code == 200
    assert "HOME_LAT" in cfg_json.json()

def test_api_restore_invalid_file():
    files = {"file": ("malicious.exe", b"NOT_A_VALID_BACKUP", "application/octet-stream")}
    res = client.post("/api/backup/restore", files=files)
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["error"]
