"""Background monitoring daemon for ALEMS.
Coordinates real-time ingestion, track filtering, CPA tracking, dispersion analysis, and database logging.
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from alems.config import config
from alems.geodesy import distance_nm, distance_ft, calculate_3d_slant_range_ft, initial_bearing, calculate_cpa
from alems.classifier import classifier
from alems.dispersion import dispersion_model
from alems.collectors.adsb_client import adsb_client
from alems.collectors.weather_client import weather_collector
from alems.collectors.mock_feed import mock_simulator
from alems.storage.db import db

class ActiveTrack:
    """Represents an ongoing aircraft flight pass within the geofence."""

    def __init__(self, icao_hex: str, first_point: Dict[str, Any], aircraft_meta: Dict[str, Any]):
        self.event_id = str(uuid.uuid4())
        self.icao_hex = icao_hex
        self.aircraft_meta = aircraft_meta
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.points: List[Dict[str, Any]] = []
        self.min_slant_range_ft: float = float("inf")
        self.cpa_point: Optional[Dict[str, Any]] = None
        self.has_triggered_event: bool = False
        self.max_exposure_score: float = 0.0
        self.exposure_scores: List[float] = []

    def add_point(self, point: Dict[str, Any], exposure_data: Dict[str, Any]) -> None:
        self.last_update_time = time.time()
        slant_range = point.get("slant_range_ft", float("inf"))

        pt_record = {
            "event_id": self.event_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "lat": float(point["lat"]),
            "lon": float(point["lon"]),
            "alt_msl_ft": float(point.get("alt_msl_ft", 0.0)),
            "alt_agl_ft": float(point.get("alt_agl_ft", 0.0)),
            "ground_speed_kts": float(point.get("gs") or 0.0),
            "track_deg": float(point.get("track") or 0.0),
            "vertical_rate_fpm": float(point.get("baro_rate") or point.get("geom_rate") or 0.0),
            "dist_to_house_ft": float(point.get("dist_ft", 0.0)),
            "slant_range_ft": float(slant_range if slant_range != float("inf") else 0.0),
            "bearing_to_house": float(point.get("bearing_to_house", 0.0)),
            "wind_speed_mph": float(exposure_data.get("wind_speed_mph", 0.0)),
            "wind_dir_deg": float(exposure_data.get("wind_dir_deg", 0.0)),
            "is_downwind": 1 if exposure_data.get("is_downwind") else 0,
            "exposure_score": float(exposure_data.get("exposure_score", 0.0))
        }
        self.points.append(pt_record)

        score = exposure_data.get("exposure_score", 0.0)
        self.exposure_scores.append(score)
        if score > self.max_exposure_score:
            self.max_exposure_score = score

        if slant_range < self.min_slant_range_ft:
            self.min_slant_range_ft = slant_range
            self.cpa_point = pt_record

    def is_expired(self, max_age_sec: float = config.MAX_TRACK_AGE_SECONDS) -> bool:
        return (time.time() - self.last_update_time) > max_age_sec

    def to_event_summary(self, weather_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        cpa = self.cpa_point or (self.points[-1] if self.points else {})
        ecowitt = weather_snapshot.get("ecowitt", {})
        aerodrome = weather_snapshot.get("aerodrome", {})

        avg_score = round(sum(self.exposure_scores) / len(self.exposure_scores), 1) if self.exposure_scores else 0.0
        duration = round(self.last_update_time - self.start_time, 1)

        start_dt = datetime.fromtimestamp(self.start_time, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(self.last_update_time, tz=timezone.utc)
        cpa_dt = datetime.fromisoformat(cpa.get("timestamp_utc", start_dt.isoformat()))

        # Convert to local time string (Eastern)
        import zoneinfo
        try:
            eastern = zoneinfo.ZoneInfo("America/New_York")
            cpa_local = cpa_dt.astimezone(eastern).strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            cpa_local = cpa_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        is_downwind = any(p.get("is_downwind") == 1 for p in self.points)

        # Categorize exposure
        if self.max_exposure_score >= 70.0:
            level = "CRITICAL / DIRECT PLUME"
        elif self.max_exposure_score >= 40.0:
            level = "ELEVATED DOWNWIND"
        elif self.max_exposure_score >= 15.0:
            level = "MODERATE"
        elif self.max_exposure_score > 0.0:
            level = "LOW / UPWIND"
        else:
            level = "NONE (Unleaded / Jet-A)"

        return {
            "event_id": self.event_id,
            "start_time_utc": start_dt.isoformat(),
            "end_time_utc": end_dt.isoformat(),
            "cpa_time_utc": cpa_dt.isoformat(),
            "cpa_time_local": cpa_local,
            "icao_hex": self.icao_hex,
            "tail_number": self.aircraft_meta.get("tail_number") or self.icao_hex,
            "aircraft_type": self.aircraft_meta.get("icao_type", "UNKNOWN"),
            "manufacturer": self.aircraft_meta.get("manufacturer", "General Aviation"),
            "model_name": self.aircraft_meta.get("model_name", "Aircraft"),
            "engine_type": self.aircraft_meta.get("engine_type", "Piston"),
            "fuel_type": self.aircraft_meta.get("fuel_type", "100LL"),
            "is_leaded": 1 if self.aircraft_meta.get("is_leaded", True) else 0,
            "min_distance_ft": float(cpa.get("dist_to_house_ft", 0.0)),
            "min_slant_range_ft": float(self.min_slant_range_ft if self.min_slant_range_ft != float("inf") else 0.0),
            "cpa_alt_msl_ft": float(cpa.get("alt_msl_ft", 0.0)),
            "cpa_alt_agl_ft": float(cpa.get("alt_agl_ft", 0.0)),
            "cpa_ground_speed_kts": float(cpa.get("ground_speed_kts", 0.0)),
            "cpa_track_deg": float(cpa.get("track_deg", 0.0)),
            "cpa_vert_rate_fpm": float(cpa.get("vertical_rate_fpm", 0.0)),
            "cpa_lat": float(cpa.get("lat", 0.0)),
            "cpa_lon": float(cpa.get("lon", 0.0)),
            "ecowitt_wind_speed_mph": float(ecowitt.get("wind_speed_mph", 0.0)),
            "ecowitt_wind_dir_deg": float(ecowitt.get("wind_dir_deg", 0.0)),
            "ecowitt_temp_f": float(ecowitt.get("temp_f", 0.0)),
            "ecowitt_humidity": float(ecowitt.get("humidity", 0.0)),
            "aerodrome_station": aerodrome.get("station", "KNHK"),
            "aerodrome_wind_speed_kts": float(aerodrome.get("wind_speed_kts", 0.0)),
            "aerodrome_wind_dir_deg": float(aerodrome.get("wind_dir_deg", 0.0)),
            "wind_alignment_deg": float(round(float(cpa.get("bearing_to_house", 0.0)) - float(aerodrome.get("wind_dir_deg", 0.0)), 1)),
            "is_downwind": 1 if is_downwind else 0,
            "lead_emission_rate_mg_s": float(round(dispersion_model.calculate_emission_rate_g_per_s(self.aircraft_meta) * 1000.0, 2)),
            "max_exposure_score": float(self.max_exposure_score),
            "avg_exposure_score": float(avg_score),
            "exposure_level": level,
            "total_duration_sec": float(duration),
            "point_count": int(len(self.points))
        }


class MonitoringDaemon:
    """Orchestrates background polling, track maintenance, and exposure event logging."""

    def __init__(self, simulation_mode: bool = False):
        self.simulation_mode = simulation_mode
        self.is_running = False
        self.active_tracks: Dict[str, ActiveTrack] = {}
        self.latest_aircraft_snapshot: List[Dict[str, Any]] = []
        self.latest_weather_snapshot: Dict[str, Any] = {}
        self.subscribers: List[Any] = [] # WebSocket client queues

    def register_subscriber(self, queue: asyncio.Queue) -> None:
        self.subscribers.append(queue)

    def unregister_subscriber(self, queue: asyncio.Queue) -> None:
        if queue in self.subscribers:
            self.subscribers.remove(queue)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(message)
            except Exception:
                pass

    async def run(self) -> None:
        """Main asynchronous processing loop."""
        self.is_running = True
        print(f"[*] ALEMS Monitoring Daemon started (Simulation: {self.simulation_mode})")
        print(f"[*] Monitored Property: {config.HOME_ADDRESS} ({config.HOME_LAT}, {config.HOME_LON})")
        print(f"[*] Geofence Radius: {config.ACTIVE_MONITOR_RADIUS_NM} NM (Event threshold: {config.FLYOVER_EVENT_RADIUS_NM} NM)")

        while self.is_running:
            try:
                # 1. Update Weather Telemetry
                weather = weather_collector.get_effective_wind()
                self.latest_weather_snapshot = weather

                # 2. Ingest ADS-B Aircraft
                if self.simulation_mode:
                    raw_aircraft = mock_simulator.get_aircraft_snapshot()
                else:
                    raw_aircraft = adsb_client.fetch_raw_aircraft()
                    # Fallback to simulation if readsb unconfigured/offline and empty
                    if not raw_aircraft and not adsb_client.is_connected:
                        raw_aircraft = mock_simulator.get_aircraft_snapshot()

                # 3. Filter & Augment Telemetry
                all_augmented_aircraft: List[Dict[str, Any]] = []
                in_geofence_aircraft: List[Dict[str, Any]] = []
                current_in_geofence_hexes = set()

                wind_spd = float(weather.get("effective_wind_speed_mph", 5.0))
                wind_dir = float(weather.get("effective_wind_dir_deg", 110.0))

                for ac in raw_aircraft:
                    lat = ac.get("lat")
                    lon = ac.get("lon")
                    if lat is None or lon is None:
                        continue

                    dist_nm_val = distance_nm(lat, lon, config.HOME_LAT, config.HOME_LON)
                    # Filter to regional reception (within 60 NM)
                    if dist_nm_val > 60.0:
                        continue

                    hex_code = (ac.get("hex") or "UNKNOWN").upper()
                    dist_ft_val = distance_ft(lat, lon, config.HOME_LAT, config.HOME_LON)
                    alt_msl = float(ac.get("alt_geom") or ac.get("alt_baro") or 1000.0)
                    alt_agl = max(0.0, alt_msl - config.HOME_ELEV_MSL_FT)
                    slant_range = calculate_3d_slant_range_ft(dist_ft_val, alt_agl)
                    bearing_from_house = initial_bearing(config.HOME_LAT, config.HOME_LON, lat, lon)
                    bearing_to_house = initial_bearing(lat, lon, config.HOME_LAT, config.HOME_LON)

                    # Classification
                    meta = classifier.classify(ac)

                    # Dispersion & Exposure calculation
                    gs = float(ac.get("gs") or 100.0)
                    vs = float(ac.get("baro_rate") or ac.get("geom_rate") or 0.0)

                    disp = dispersion_model.calculate_point_exposure(
                        lat=lat,
                        lon=lon,
                        alt_msl_ft=alt_msl,
                        ground_speed_kts=gs,
                        vertical_rate_fpm=vs,
                        aircraft_meta=meta,
                        wind_speed_mph=wind_spd,
                        wind_dir_deg=wind_dir
                    )

                    slant_range_nm = slant_range / 6076.12
                    in_geofence = (dist_nm_val <= config.ACTIVE_MONITOR_RADIUS_NM) and (alt_msl <= 18000.0)

                    augmented = dict(ac)
                    augmented.update({
                        "hex": hex_code,
                        "dist_nm": round(dist_nm_val, 2),
                        "dist_ft": round(dist_ft_val, 0),
                        "alt_msl_ft": round(alt_msl, 0),
                        "alt_agl_ft": round(alt_agl, 0),
                        "slant_range_ft": round(slant_range, 0),
                        "bearing_from_house": round(bearing_from_house, 1),
                        "bearing_to_house": round(bearing_to_house, 1),
                        "in_geofence": in_geofence,
                        "aircraft_meta": meta,
                        "dispersion": disp
                    })
                    all_augmented_aircraft.append(augmented)

                    if in_geofence:
                        in_geofence_aircraft.append(augmented)
                        current_in_geofence_hexes.add(hex_code)

                        # Manage Active Track for regulatory flyover log
                        if hex_code not in self.active_tracks:
                            self.active_tracks[hex_code] = ActiveTrack(hex_code, augmented, meta)

                        track = self.active_tracks[hex_code]
                        if slant_range_nm <= config.FLYOVER_EVENT_RADIUS_NM and alt_msl <= 18000.0:
                            track.has_triggered_event = True

                        exposure_pt = {
                            "wind_speed_mph": wind_spd,
                            "wind_dir_deg": wind_dir,
                            "is_downwind": disp["is_downwind"],
                            "exposure_score": disp["exposure_score"]
                        }
                        track.add_point(augmented, exposure_pt)

                self.latest_aircraft_snapshot = all_augmented_aircraft

                # 4. Check for completed / expired flyover events
                expired_hexes = []
                for hex_code, track in self.active_tracks.items():
                    if hex_code not in current_in_geofence_hexes or track.is_expired():
                        # Track has left vicinity
                        if track.has_triggered_event and len(track.points) >= 3:
                            summary = track.to_event_summary(weather)
                            h = db.record_flyover_event(summary, track.points)
                            print(f"[+] Flyover Logged: {summary['tail_number']} ({summary['aircraft_type']}, {summary['fuel_type']}) - Min Slant: {summary['min_slant_range_ft']} ft - Risk: {summary['max_exposure_score']} ({summary['exposure_level']}) - Hash: {h[:8]}...")
                            await self.broadcast({"type": "NEW_EVENT", "event": summary})
                        expired_hexes.append(hex_code)

                for hex_code in expired_hexes:
                    del self.active_tracks[hex_code]

                # 5. Broadcast real-time telemetry snapshot to connected UI clients
                await self.broadcast({
                    "type": "SNAPSHOT",
                    "aircraft": all_augmented_aircraft,
                    "geofence_count": len(in_geofence_aircraft),
                    "total_count": len(all_augmented_aircraft),
                    "adsb_connected": adsb_client.is_connected,
                    "weather": weather,
                    "timestamp": time.time()
                })

            except Exception as e:
                print(f"[!] Error in daemon loop: {e}")

            await asyncio.sleep(config.READSB_POLL_INTERVAL_SEC)

    def stop(self) -> None:
        self.is_running = False

daemon = MonitoringDaemon(simulation_mode=False)
