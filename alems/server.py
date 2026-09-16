"""FastAPI Server and REST / WebSocket API for ALEMS."""

import asyncio
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
import time
import requests
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request, UploadFile, File, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from alems.config import config, BASE_DIR, DATA_DIR
from alems.storage.db import db
from alems.storage.exporter import exporter
from alems.daemon import daemon
from alems.collectors.adsb_client import adsb_client, normalize_readsb_url, ADSBClient
from alems.collectors.weather_client import weather_collector

app = FastAPI(title="Aerial Lead Exposure Monitoring System (ALEMS)", version="1.0.0")

# Mount frontend static directory
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
(FRONTEND_DIR / "css").mkdir(parents=True, exist_ok=True)
(FRONTEND_DIR / "js").mkdir(parents=True, exist_ok=True)

@app.on_event("startup")
async def startup_event():
    # Start background daemon task
    asyncio.create_task(daemon.run())

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0, post-check=0, pre-check=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.on_event("shutdown")
def shutdown_event():
    daemon.stop()

@app.api_route("/", methods=["GET", "HEAD"])
def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        response = FileResponse(index_path)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return JSONResponse({"status": "Frontend not yet initialized. Visit /api/status"})

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    svg_icon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#0f172a"/><text x="16" y="22" font-size="18" font-family="system-ui,sans-serif" font-weight="bold" fill="#38bdf8" text-anchor="middle">Pb</text></svg>"""
    return Response(content=svg_icon, media_type="image/svg+xml")

from alems.geocoding import geocoding_service

@app.get("/api/config")
def get_config():
    return {
        "home": {
            "address": config.HOME_ADDRESS,
            "lat": config.HOME_LAT,
            "lon": config.HOME_LON,
            "elev_msl_ft": config.HOME_ELEV_MSL_FT
        },
        "airport": {
            "id": config.AIRPORT_ID,
            "name": config.AIRPORT_NAME,
            "lat": config.AIRPORT_LAT,
            "lon": config.AIRPORT_LON,
            "elev_msl_ft": config.AIRPORT_ELEV_MSL_FT,
            "runway_heading_11": config.AIRPORT_RUNWAY_HEADING_11,
            "runway_heading_29": config.AIRPORT_RUNWAY_HEADING_29,
            "runway_length_ft": config.AIRPORT_RUNWAY_LENGTH_FT
        },
        "thresholds": {
            "active_radius_nm": config.ACTIVE_MONITOR_RADIUS_NM,
            "flyover_radius_nm": config.FLYOVER_EVENT_RADIUS_NM,
            "plume_half_angle_deg": config.PLUME_DISPERSION_HALF_ANGLE_DEG
        },
        "endpoints": {
            "adsb_provider": config.ADSB_PROVIDER,
            "adsb_custom_url": config.ADSB_CUSTOM_URL,
            "readsb_url": config.READSB_URL,
            "readsb_host": config.READSB_HOST,
            "readsb_port": config.READSB_PORT,
            "readsb_path": config.READSB_PATH,
            "weather_provider": config.WEATHER_PROVIDER,
            "ecowitt_ip": config.ECOWITT_IP,
            "ecowitt_port": config.ECOWITT_PORT,
            "hass_url": config.HASS_URL,
            "has_hass_token": bool(config.HASS_TOKEN),
            "metar_stations": config.METAR_STATIONS
        },
        "simulation_mode": daemon.simulation_mode
    }

class ConfigUpdateRequest(BaseModel):
    home_address: Optional[str] = None
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    home_elev_ft: Optional[float] = None
    airport_id: Optional[str] = None
    airport_name: Optional[str] = None
    airport_lat: Optional[float] = None
    airport_lon: Optional[float] = None
    airport_elev_ft: Optional[float] = None
    runway_heading_1: Optional[float] = None
    runway_heading_2: Optional[float] = None
    runway_length_ft: Optional[float] = None
    active_radius_nm: Optional[float] = None
    flyover_radius_nm: Optional[float] = None
    adsb_provider: Optional[str] = None
    adsb_custom_url: Optional[str] = None
    readsb_url: Optional[str] = None
    readsb_host: Optional[str] = None
    readsb_port: Optional[int] = None
    readsb_path: Optional[str] = None
    weather_provider: Optional[str] = None
    ecowitt_ip: Optional[str] = None
    ecowitt_port: Optional[int] = None
    hass_url: Optional[str] = None
    hass_token: Optional[str] = None
    simulation_mode: Optional[bool] = None

@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    updates = {}
    if req.home_address is not None:
        updates["HOME_ADDRESS"] = req.home_address
    if req.home_lat is not None:
        updates["HOME_LAT"] = req.home_lat
    if req.home_lon is not None:
        updates["HOME_LON"] = req.home_lon
    if req.home_elev_ft is not None:
        updates["HOME_ELEV_MSL_FT"] = req.home_elev_ft

    if req.airport_id is not None:
        updates["AIRPORT_ID"] = req.airport_id.upper()
    if req.airport_name is not None:
        updates["AIRPORT_NAME"] = req.airport_name
    if req.airport_lat is not None:
        updates["AIRPORT_LAT"] = req.airport_lat
    if req.airport_lon is not None:
        updates["AIRPORT_LON"] = req.airport_lon
    if req.airport_elev_ft is not None:
        updates["AIRPORT_ELEV_MSL_FT"] = req.airport_elev_ft
    if req.runway_heading_1 is not None:
        updates["AIRPORT_RUNWAY_HEADING_11"] = req.runway_heading_1
    if req.runway_heading_2 is not None:
        updates["AIRPORT_RUNWAY_HEADING_29"] = req.runway_heading_2
    if req.runway_length_ft is not None:
        updates["AIRPORT_RUNWAY_LENGTH_FT"] = req.runway_length_ft

    if req.active_radius_nm is not None:
        updates["ACTIVE_MONITOR_RADIUS_NM"] = req.active_radius_nm
    if req.flyover_radius_nm is not None:
        updates["FLYOVER_EVENT_RADIUS_NM"] = req.flyover_radius_nm

    if req.adsb_provider is not None:
        updates["ADSB_PROVIDER"] = req.adsb_provider
        adsb_client.provider = req.adsb_provider
    if req.adsb_custom_url is not None:
        updates["ADSB_CUSTOM_URL"] = req.adsb_custom_url

    if req.readsb_host is not None:
        updates["READSB_HOST"] = req.readsb_host
    if req.readsb_port is not None:
        updates["READSB_PORT"] = req.readsb_port
    if req.readsb_path is not None:
        updates["READSB_PATH"] = req.readsb_path

    if req.readsb_url is not None and req.readsb_url.strip():
        norm_url = normalize_readsb_url(req.readsb_url)
        updates["READSB_URL"] = norm_url
        adsb_client.endpoint_url = norm_url
    elif req.readsb_host and req.readsb_host.strip():
        host = req.readsb_host.strip()
        port = req.readsb_port or 80
        path = req.readsb_path or "/tar1090/data/aircraft.json"
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
        p = f":{port}" if port and port not in (80, 443) else ""
        clean_path = path if path and path.startswith("/") else f"/{path}"
        constructed_url = normalize_readsb_url(f"{host}{p}{clean_path}")
        updates["READSB_URL"] = constructed_url
        adsb_client.endpoint_url = constructed_url

    # Proactively test connection with new settings
    try:
        adsb_client.fetch_raw_aircraft()
    except Exception:
        pass

    if req.weather_provider is not None:
        updates["WEATHER_PROVIDER"] = req.weather_provider
    if req.ecowitt_ip is not None:
        updates["ECOWITT_IP"] = req.ecowitt_ip.strip()
    if req.ecowitt_port is not None:
        updates["ECOWITT_PORT"] = req.ecowitt_port

    if req.hass_url is not None:
        updates["HASS_URL"] = req.hass_url
    if req.hass_token is not None:
        updates["HASS_TOKEN"] = req.hass_token

    if req.simulation_mode is not None:
        daemon.simulation_mode = req.simulation_mode

    # Save updates persistently to data/config.json
    config.save_persisted(updates)

    # Broadcast updated configuration to all connected UI clients
    await daemon.broadcast({"type": "CONFIG_UPDATED", "config": get_config()})
    return {"status": "success", "config": get_config(), "simulation_mode": daemon.simulation_mode}

@app.get("/api/geocode")
def geocode_address(query: str = Query(...)):
    res = geocoding_service.geocode_address(query)
    if not res:
        return JSONResponse({"error": f"Address not found: '{query}'"}, status_code=404)
    return res

@app.get("/api/airport/lookup")
def lookup_airport(code: str = Query(...)):
    res = geocoding_service.lookup_airport(code)
    if not res:
        return JSONResponse({"error": f"Airport code not found: '{code}'"}, status_code=404)
    return res

@app.api_route("/api/weather/ecowitt", methods=["GET", "POST"])
async def receive_ecowitt_push(request: Request):
    """Webhook endpoint for Ecowitt Customized Weather Service pushes."""
    params = {}
    if request.method == "POST":
        try:
            form = await request.form()
            params.update(dict(form))
        except Exception:
            pass
    params.update(dict(request.query_params))
    data = weather_collector.handle_ecowitt_push_data(params)
    return {"status": "success", "received_fields": len(params), "live_weather": data}

@app.get("/api/test/adsb")
@app.get("/api/test/readsb")
def test_adsb_connection(
    provider: Optional[str] = None,
    url: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = 80,
    path: Optional[str] = "/tar1090/data/aircraft.json"
):
    """Test connectivity to chosen ADS-B provider (local readsb, adsb.lol, opensky, custom)."""
    sel_provider = provider or config.ADSB_PROVIDER
    target_url = url
    if sel_provider == "readsb_local":
        if not target_url and host:
            clean_host = host.strip()
            if not clean_host.startswith("http://") and not clean_host.startswith("https://"):
                clean_host = f"http://{clean_host}"
            p = f":{port}" if port and port not in (80, 443) else ""
            clean_path = path if path and path.startswith("/") else f"/{path or 'tar1090/data/aircraft.json'}"
            target_url = f"{clean_host}{p}{clean_path}"
        target_url = normalize_readsb_url(target_url or config.READSB_URL)
    elif sel_provider == "custom_url":
        target_url = url or config.ADSB_CUSTOM_URL

    try:
        orig_provider = config.ADSB_PROVIDER
        if provider:
            config.ADSB_PROVIDER = provider
        if target_url and sel_provider == "custom_url":
            config.ADSB_CUSTOM_URL = target_url

        client = ADSBClient(endpoint_url=target_url, provider=sel_provider)
        t0 = time.time()
        ac_list = client.fetch_raw_aircraft()
        elapsed_ms = round((time.time() - t0) * 1000, 1)

        config.ADSB_PROVIDER = orig_provider

        if client.is_connected:
            return {
                "success": True,
                "provider": sel_provider,
                "url": client.endpoint_url,
                "status_code": 200,
                "aircraft_count": len(ac_list),
                "latency_ms": elapsed_ms
            }
        else:
            return {
                "success": False,
                "provider": sel_provider,
                "url": client.endpoint_url or target_url,
                "error": client.last_error or f"Failed to connect to {sel_provider}"
            }
    except Exception as e:
        return {"success": False, "provider": sel_provider, "url": target_url, "error": str(e)}

@app.get("/api/test/ecowitt")
def test_ecowitt_connection(ip: Optional[str] = None, port: Optional[int] = 80):
    """Test local network connection to Ecowitt gateway."""
    target_ip = ip or config.ECOWITT_IP
    if not target_ip:
        return {"success": False, "error": "No Ecowitt IP address specified"}
    
    target_port = port or config.ECOWITT_PORT or 80
    url = f"http://{target_ip}:{target_port}/get_livedata_info"
    try:
        t0 = time.time()
        resp = requests.get(url, timeout=3.0)
        elapsed_ms = round((time.time() - t0) * 1000, 1)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "success": True,
                "url": url,
                "latency_ms": elapsed_ms,
                "data_keys": list(data.keys()) if isinstance(data, dict) else []
            }
        else:
            return {"success": False, "url": url, "status_code": resp.status_code, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "url": url, "error": str(e)}

@app.get("/api/status")
def get_status():
    return {
        "daemon_running": daemon.is_running,
        "simulation_mode": daemon.simulation_mode,
        "adsb": {
            "url": adsb_client.endpoint_url,
            "connected": adsb_client.is_connected,
            "last_error": adsb_client.last_error,
            "last_fetch_time": adsb_client.last_fetch_time
        },
        "weather": {
            "ecowitt_status": weather_collector.last_ecowitt.get("status"),
            "aerodrome_station": weather_collector.last_aerodrome.get("station"),
            "aerodrome_status": weather_collector.last_aerodrome.get("status")
        }
    }

@app.get("/api/aircraft")
def get_active_aircraft():
    total = len(daemon.latest_aircraft_snapshot)
    in_geo = sum(1 for a in daemon.latest_aircraft_snapshot if a.get("in_geofence"))
    return {
        "aircraft": daemon.latest_aircraft_snapshot,
        "count": total,
        "total_count": total,
        "geofence_count": in_geo,
        "adsb_connected": adsb_client.is_connected,
        "weather": daemon.latest_weather_snapshot
    }

@app.get("/api/weather")
def get_weather():
    return weather_collector.get_effective_wind()

@app.get("/api/events")
def get_events(limit: int = 100, leaded_only: bool = False):
    events = db.get_recent_events(limit=limit, leaded_only=leaded_only)
    return {"events": events, "count": len(events)}

@app.post("/api/events/clear")
@app.delete("/api/events")
def clear_events():
    """Purge all recorded events and trajectory points."""
    count = db.clear_all_events()
    return {"status": "success", "purged_count": count}

@app.get("/api/events/{event_id}/points")
def get_event_trajectory(event_id: str):
    points = db.get_event_points(event_id)
    return {"event_id": event_id, "points": points, "count": len(points)}

@app.get("/api/statistics")
def get_statistics(time_range: str = Query("all")):
    return db.get_statistics(time_range=time_range)

@app.get("/api/export/csv")
def download_events_csv(leaded_only: bool = Query(False)):
    path = exporter.export_events_csv(leaded_only=leaded_only)
    return FileResponse(path, filename=path.name, media_type="text/csv")

@app.get("/api/export/event/{event_id}/csv")
def download_event_points_csv(event_id: str):
    path = exporter.export_event_trajectory_csv(event_id)
    if not path or not path.exists():
        return JSONResponse({"error": "Event not found or has no points"}, status_code=404)
    return FileResponse(path, filename=path.name, media_type="text/csv")

# ==========================================
# Backup, Export & Device Migration Endpoints
# ==========================================

@app.get("/api/backup/database")
def download_database_backup():
    """Download clean, checkpointed SQLite database snapshot."""
    temp_dir = DATA_DIR / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = temp_dir / f"alems_backup_{ts}.db"
    db.export_snapshot(backup_file)
    return FileResponse(
        backup_file,
        filename=f"alems_backup_{ts}.db",
        media_type="application/vnd.sqlite3"
    )

@app.get("/api/backup/config")
def download_config_backup(format: str = Query("yaml")):
    """Download runtime configuration in YAML or JSON format."""
    clean_dict = config.to_clean_dict()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if format.lower() == "json":
        content = json.dumps(clean_dict, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=alems_config_{ts}.json"}
        )
    else:
        content = yaml.dump(clean_dict, sort_keys=False)
        return Response(
            content=content,
            media_type="application/x-yaml",
            headers={"Content-Disposition": f"attachment; filename=alems_config_{ts}.yaml"}
        )

@app.get("/api/backup/bundle")
def download_backup_bundle():
    """Download complete migration bundle (database + config.yaml + config.json + manifest) as a ZIP."""
    temp_dir = DATA_DIR / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    db_temp = temp_dir / f"alems_temp_{ts}.db"
    db.export_snapshot(db_temp)
    info = db.inspect_database_file(db_temp)

    zip_path = temp_dir / f"alems_migration_bundle_{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_temp, arcname="alems.db")

        cfg_dict = config.to_clean_dict()
        zf.writestr("config.yaml", yaml.dump(cfg_dict, sort_keys=False))
        zf.writestr("config.json", json.dumps(cfg_dict, indent=2))

        manifest = {
            "version": "1.0.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": {
                "events_count": info.get("event_count", 0),
                "points_count": info.get("point_count", 0),
                "registry_count": info.get("registry_count", 0),
                "size_bytes": info.get("size_bytes", 0)
            },
            "config_keys_count": len(cfg_dict)
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    if db_temp.exists():
        try:
            db_temp.unlink()
        except Exception:
            pass

    return FileResponse(
        zip_path,
        filename=f"alems_migration_bundle_{ts}.zip",
        media_type="application/zip"
    )

@app.post("/api/backup/inspect")
async def inspect_uploaded_backup(file: UploadFile = File(...)):
    """Inspect an uploaded file to preview its contents before applying."""
    temp_dir = DATA_DIR / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"upload_{uuid.uuid4().hex}_{file.filename}"

    try:
        content = await file.read()
        with open(temp_file, "wb") as f:
            f.write(content)

        fname_lower = (file.filename or "").lower()

        # Check if ZIP bundle
        if fname_lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(temp_file, "r") as zf:
                    namelist = zf.namelist()
                    has_db = any(n.endswith(".db") for n in namelist)
                    has_yaml = any(n.endswith(".yaml") or n.endswith(".yml") for n in namelist)
                    has_json = any(n.endswith(".json") and not n.endswith("manifest.json") for n in namelist)

                    db_info = None
                    if has_db:
                        db_name = next(n for n in namelist if n.endswith(".db"))
                        extracted_db = temp_dir / f"inspect_{uuid.uuid4().hex}.db"
                        with open(extracted_db, "wb") as out_f:
                            out_f.write(zf.read(db_name))
                        try:
                            db_info = db.inspect_database_file(extracted_db)
                        finally:
                            if extracted_db.exists():
                                extracted_db.unlink()

                    return {
                        "type": "bundle_zip",
                        "filename": file.filename,
                        "files": namelist,
                        "has_database": has_db,
                        "has_config": (has_yaml or has_json),
                        "database_info": db_info,
                        "size_bytes": len(content)
                    }
            except zipfile.BadZipFile:
                return JSONResponse({"error": "Uploaded file is not a valid ZIP archive"}, status_code=400)

        # Check if SQLite DB
        elif fname_lower.endswith(".db") or fname_lower.endswith(".sqlite") or content.startswith(b"SQLite format 3\x00"):
            try:
                info = db.inspect_database_file(temp_file)
                return {
                    "type": "database",
                    "filename": file.filename,
                    "database_info": info,
                    "size_bytes": len(content)
                }
            except Exception as e:
                return JSONResponse({"error": f"Invalid SQLite database: {e}"}, status_code=400)

        # Check if YAML / JSON config
        elif fname_lower.endswith(".yaml") or fname_lower.endswith(".yml") or fname_lower.endswith(".json"):
            try:
                text_content = content.decode("utf-8")
                parsed = yaml.safe_load(text_content)
                if not isinstance(parsed, dict):
                    return JSONResponse({"error": "Configuration file must contain key-value mappings"}, status_code=400)
                valid_keys = [k for k in parsed.keys() if hasattr(config, k.upper())]
                return {
                    "type": "config",
                    "filename": file.filename,
                    "format": "yaml" if (fname_lower.endswith(".yaml") or fname_lower.endswith(".yml")) else "json",
                    "valid_keys_count": len(valid_keys),
                    "keys": valid_keys,
                    "size_bytes": len(content)
                }
            except Exception as e:
                return JSONResponse({"error": f"Failed to parse configuration: {e}"}, status_code=400)
        else:
            return JSONResponse({"error": "Unsupported file format. Please upload .zip, .db, .sqlite, .yaml, or .json"}, status_code=400)
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass

@app.post("/api/backup/restore")
async def restore_backup(file: UploadFile = File(...)):
    """Upload and restore a database (.db), configuration (.yaml/.json), or full migration bundle (.zip)."""
    temp_dir = DATA_DIR / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"restore_{uuid.uuid4().hex}_{file.filename}"

    try:
        content = await file.read()
        with open(temp_file, "wb") as f:
            f.write(content)

        fname_lower = (file.filename or "").lower()
        restored_db_info = None
        restored_config_keys = []

        # 1. ZIP Migration Bundle
        if fname_lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(temp_file, "r") as zf:
                    namelist = zf.namelist()
                    # Restore DB if present
                    for n in namelist:
                        if n.endswith(".db"):
                            extracted_db = temp_dir / f"restore_extract_{uuid.uuid4().hex}.db"
                            with open(extracted_db, "wb") as out_f:
                                out_f.write(zf.read(n))
                            try:
                                restored_db_info = db.restore_from_snapshot(extracted_db)
                            finally:
                                if extracted_db.exists():
                                    extracted_db.unlink()
                            break
                    # Restore config if present
                    cfg_file = None
                    for n in ["config.yaml", "config.yml", "config.json"]:
                        if n in namelist:
                            cfg_file = n
                            break
                    if cfg_file:
                        cfg_text = zf.read(cfg_file).decode("utf-8")
                        parsed = yaml.safe_load(cfg_text)
                        if isinstance(parsed, dict):
                            restored_config_keys = config.load_from_dict(parsed)
            except zipfile.BadZipFile:
                return JSONResponse({"error": "Invalid ZIP archive"}, status_code=400)

        # 2. SQLite Database
        elif fname_lower.endswith(".db") or fname_lower.endswith(".sqlite") or content.startswith(b"SQLite format 3\x00"):
            try:
                restored_db_info = db.restore_from_snapshot(temp_file)
            except Exception as e:
                return JSONResponse({"error": f"Failed to restore SQLite database: {e}"}, status_code=400)

        # 3. YAML or JSON Configuration
        elif fname_lower.endswith(".yaml") or fname_lower.endswith(".yml") or fname_lower.endswith(".json"):
            try:
                text_content = content.decode("utf-8")
                parsed = yaml.safe_load(text_content)
                if not isinstance(parsed, dict):
                    return JSONResponse({"error": "Configuration file must contain key-value mappings"}, status_code=400)
                restored_config_keys = config.load_from_dict(parsed)
            except Exception as e:
                return JSONResponse({"error": f"Failed to restore configuration: {e}"}, status_code=400)
        else:
            return JSONResponse({"error": "Unsupported file format. Please upload .zip, .db, .sqlite, .yaml, or .json"}, status_code=400)

        # Broadcast refreshed state to UI via WebSocket
        await daemon.broadcast({
            "type": "RESTORE_COMPLETED",
            "stats": db.get_statistics(),
            "events": db.get_recent_events(limit=25),
            "config": config.to_clean_dict()
        })

        return JSONResponse({
            "success": True,
            "filename": file.filename,
            "database_restored": bool(restored_db_info),
            "database_info": restored_db_info,
            "config_restored": bool(restored_config_keys),
            "config_keys_updated": restored_config_keys,
            "active_config": config.to_clean_dict()
        })
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue = asyncio.Queue()
    daemon.register_subscriber(queue)
    try:
        total = len(daemon.latest_aircraft_snapshot)
        in_geo = sum(1 for a in daemon.latest_aircraft_snapshot if a.get("in_geofence"))
        # Send immediate initial state
        await websocket.send_json({
            "type": "INITIAL_STATE",
            "aircraft": daemon.latest_aircraft_snapshot,
            "total_count": total,
            "geofence_count": in_geo,
            "adsb_connected": adsb_client.is_connected,
            "weather": daemon.latest_weather_snapshot,
            "events": db.get_recent_events(limit=25),
            "stats": db.get_statistics()
        })
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        daemon.unregister_subscriber(queue)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
