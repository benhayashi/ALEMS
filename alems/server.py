"""FastAPI Server and REST / WebSocket API for ALEMS."""

import asyncio
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from alems.config import config, BASE_DIR
from alems.storage.db import db
from alems.storage.exporter import exporter
from alems.daemon import daemon
from alems.collectors.adsb_client import adsb_client
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
            "readsb_url": config.READSB_URL,
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
    readsb_url: Optional[str] = None
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

    if req.readsb_url is not None:
        updates["READSB_URL"] = req.readsb_url
        adsb_client.endpoint_url = req.readsb_url
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
    return {
        "aircraft": daemon.latest_aircraft_snapshot,
        "count": len(daemon.latest_aircraft_snapshot),
        "weather": daemon.latest_weather_snapshot
    }

@app.get("/api/weather")
def get_weather():
    return weather_collector.get_effective_wind()

@app.get("/api/events")
def get_events(limit: int = 100, leaded_only: bool = False):
    events = db.get_recent_events(limit=limit, leaded_only=leaded_only)
    return {"events": events, "count": len(events)}

@app.get("/api/events/{event_id}/points")
def get_event_trajectory(event_id: str):
    points = db.get_event_points(event_id)
    return {"event_id": event_id, "points": points, "count": len(points)}

@app.get("/api/statistics")
def get_statistics():
    return db.get_statistics()

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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue = asyncio.Queue()
    daemon.register_subscriber(queue)
    try:
        # Send immediate initial state
        await websocket.send_json({
            "type": "INITIAL_STATE",
            "aircraft": daemon.latest_aircraft_snapshot,
            "weather": daemon.latest_weather_snapshot,
            "events": db.get_recent_events(limit=25),
            "stats": db.get_statistics()
        })
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        daemon.unregister_subscriber(queue)
    except Exception:
        daemon.unregister_subscriber(queue)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
