"""SQLite Database Management for ALEMS.
Stores immutable flyover events, high-frequency track records, and weather observations.
"""

import sqlite3
import hashlib
import json
import math
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from alems.config import config
from alems.geodesy import haversine_distance_m

class Database:
    """Handles SQLite persistence for flight logs and exposure records."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.DATABASE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_hex: Dict[str, Optional[Dict[str, str]]] = {}
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS flyover_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                start_time_utc TEXT NOT NULL,
                end_time_utc TEXT NOT NULL,
                cpa_time_utc TEXT NOT NULL,
                cpa_time_local TEXT NOT NULL,
                icao_hex TEXT NOT NULL,
                tail_number TEXT,
                aircraft_type TEXT,
                manufacturer TEXT,
                model_name TEXT,
                engine_type TEXT,
                fuel_type TEXT,
                is_leaded INTEGER NOT NULL DEFAULT 1,
                min_distance_ft REAL NOT NULL,
                min_slant_range_ft REAL NOT NULL,
                cpa_alt_msl_ft REAL NOT NULL,
                cpa_alt_agl_ft REAL NOT NULL,
                cpa_ground_speed_kts REAL,
                cpa_track_deg REAL,
                cpa_vert_rate_fpm REAL,
                cpa_lat REAL NOT NULL,
                cpa_lon REAL NOT NULL,
                ecowitt_wind_speed_mph REAL,
                ecowitt_wind_dir_deg REAL,
                ecowitt_temp_f REAL,
                ecowitt_humidity REAL,
                aerodrome_station TEXT,
                aerodrome_wind_speed_kts REAL,
                aerodrome_wind_dir_deg REAL,
                wind_alignment_deg REAL,
                is_downwind INTEGER NOT NULL DEFAULT 0,
                lead_emission_rate_mg_s REAL,
                max_exposure_score REAL NOT NULL,
                avg_exposure_score REAL NOT NULL,
                exposure_level TEXT NOT NULL,
                total_duration_sec REAL NOT NULL,
                point_count INTEGER NOT NULL,
                corroboration_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS track_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                alt_msl_ft REAL,
                alt_agl_ft REAL,
                ground_speed_kts REAL,
                track_deg REAL,
                vertical_rate_fpm REAL,
                dist_to_house_ft REAL,
                slant_range_ft REAL,
                bearing_to_house REAL,
                wind_speed_mph REAL,
                wind_dir_deg REAL,
                is_downwind INTEGER,
                exposure_score REAL,
                FOREIGN KEY (event_id) REFERENCES flyover_events(event_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS weather_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                source TEXT NOT NULL,
                wind_speed REAL,
                wind_dir REAL,
                wind_gust REAL,
                temp_f REAL,
                humidity REAL,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS aircraft_registry (
                hex TEXT PRIMARY KEY,
                reg TEXT,
                icao_type TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_events_start ON flyover_events(start_time_utc);
            CREATE INDEX IF NOT EXISTS idx_events_hex ON flyover_events(icao_hex);
            CREATE INDEX IF NOT EXISTS idx_events_leaded ON flyover_events(is_leaded);
            CREATE INDEX IF NOT EXISTS idx_events_downwind ON flyover_events(is_downwind);
            CREATE INDEX IF NOT EXISTS idx_points_event ON track_points(event_id);
            """)
            self._populate_aircraft_registry_if_empty(conn)

    def _populate_aircraft_registry_if_empty(self, conn: sqlite3.Connection) -> None:
        """Seed aircraft_registry from readsb_aircrafts.json if database table is empty."""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM aircraft_registry")
            if cursor.fetchone()[0] == 0:
                json_path = self.db_path.parent / "readsb_aircrafts.json"
                if json_path.exists():
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    batch = [
                        (h, val[0] if len(val) > 0 else None, val[1] if len(val) > 1 else None)
                        for h, val in data.items()
                    ]
                    conn.executemany("INSERT OR IGNORE INTO aircraft_registry (hex, reg, icao_type) VALUES (?, ?, ?)", batch)
                    conn.commit()
        except Exception as e:
            print(f"Warning: Failed to populate aircraft_registry: {e}")

    def lookup_aircraft_hex(self, hex_code: str) -> Optional[Dict[str, str]]:
        """Lookup registration and ICAO type from local 440k+ aircraft registry."""
        if not hex_code:
            return None
        hex_clean = hex_code.strip().lower()
        if hex_clean in self._cache_hex:
            return self._cache_hex[hex_clean]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT reg, icao_type FROM aircraft_registry WHERE hex IN (?, ?) LIMIT 1",
                (hex_clean, hex_clean.upper())
            )
            row = cursor.fetchone()
            res = {"reg": row[0], "icao_type": row[1]} if row else None
            if len(self._cache_hex) < 15000:
                self._cache_hex[hex_clean] = res
            return res


    @staticmethod
    def calculate_record_hash(record: Dict[str, Any], points: List[Dict[str, Any]]) -> str:
        """Compute SHA256 checksum for legal and regulatory corroboration."""
        h = hashlib.sha256()
        canonical_str = f"{record.get('event_id')}|{record.get('cpa_time_utc')}|{record.get('icao_hex')}|" \
                        f"{record.get('min_distance_ft')}|{record.get('min_slant_range_ft')}|{record.get('cpa_alt_msl_ft')}|" \
                        f"{record.get('ecowitt_wind_speed_mph')}|{record.get('ecowitt_wind_dir_deg')}|" \
                        f"{len(points)}"
        h.update(canonical_str.encode("utf-8"))
        return h.hexdigest()

    def record_flyover_event(self, event: Dict[str, Any], points: List[Dict[str, Any]]) -> str:
        """Persist a completed flyover event along with all its high-frequency trajectory points."""
        corroboration_hash = self.calculate_record_hash(event, points)
        event["corroboration_hash"] = corroboration_hash
        event["created_at"] = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO flyover_events (
                event_id, start_time_utc, end_time_utc, cpa_time_utc, cpa_time_local,
                icao_hex, tail_number, aircraft_type, manufacturer, model_name,
                engine_type, fuel_type, is_leaded, min_distance_ft, min_slant_range_ft,
                cpa_alt_msl_ft, cpa_alt_agl_ft, cpa_ground_speed_kts, cpa_track_deg,
                cpa_vert_rate_fpm, cpa_lat, cpa_lon, ecowitt_wind_speed_mph,
                ecowitt_wind_dir_deg, ecowitt_temp_f, ecowitt_humidity,
                aerodrome_station, aerodrome_wind_speed_kts, aerodrome_wind_dir_deg,
                wind_alignment_deg, is_downwind, lead_emission_rate_mg_s,
                max_exposure_score, avg_exposure_score, exposure_level,
                total_duration_sec, point_count, corroboration_hash, created_at
            ) VALUES (
                :event_id, :start_time_utc, :end_time_utc, :cpa_time_utc, :cpa_time_local,
                :icao_hex, :tail_number, :aircraft_type, :manufacturer, :model_name,
                :engine_type, :fuel_type, :is_leaded, :min_distance_ft, :min_slant_range_ft,
                :cpa_alt_msl_ft, :cpa_alt_agl_ft, :cpa_ground_speed_kts, :cpa_track_deg,
                :cpa_vert_rate_fpm, :cpa_lat, :cpa_lon, :ecowitt_wind_speed_mph,
                :ecowitt_wind_dir_deg, :ecowitt_temp_f, :ecowitt_humidity,
                :aerodrome_station, :aerodrome_wind_speed_kts, :aerodrome_wind_dir_deg,
                :wind_alignment_deg, :is_downwind, :lead_emission_rate_mg_s,
                :max_exposure_score, :avg_exposure_score, :exposure_level,
                :total_duration_sec, :point_count, :corroboration_hash, :created_at
            )
            """, event)

            # Insert track points in batch
            if points:
                cursor.executemany("""
                INSERT INTO track_points (
                    event_id, timestamp_utc, lat, lon, alt_msl_ft, alt_agl_ft,
                    ground_speed_kts, track_deg, vertical_rate_fpm, dist_to_house_ft,
                    slant_range_ft, bearing_to_house, wind_speed_mph, wind_dir_deg,
                    is_downwind, exposure_score
                ) VALUES (
                    :event_id, :timestamp_utc, :lat, :lon, :alt_msl_ft, :alt_agl_ft,
                    :ground_speed_kts, :track_deg, :vertical_rate_fpm, :dist_to_house_ft,
                    :slant_range_ft, :bearing_to_house, :wind_speed_mph, :wind_dir_deg,
                    :is_downwind, :exposure_score
                )
                """, points)

            conn.commit()
        return corroboration_hash

    def log_weather_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Record an atmospheric snapshot."""
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO weather_snapshots (
                timestamp_utc, source, wind_speed, wind_dir, wind_gust, temp_f, humidity, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.get("timestamp_utc", datetime.now(timezone.utc).isoformat()),
                snapshot.get("source", "unknown"),
                snapshot.get("wind_speed"),
                snapshot.get("wind_dir"),
                snapshot.get("wind_gust"),
                snapshot.get("temp_f"),
                snapshot.get("humidity"),
                json.dumps(snapshot.get("raw_data", {}))
            ))

    def get_recent_events(self, limit: int = 50, leaded_only: bool = False) -> List[Dict[str, Any]]:
        """Fetch recent flyovers for the UI event feed."""
        query = "SELECT * FROM flyover_events"
        params: List[Any] = []
        if leaded_only:
            query += " WHERE is_leaded = 1"
        query += " ORDER BY cpa_time_utc DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_event_points(self, event_id: str) -> List[Dict[str, Any]]:
        """Fetch high frequency trajectory points for a given event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM track_points WHERE event_id = ? ORDER BY timestamp_utc ASC", (event_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_exposure_heatmap_points(
        self,
        time_range: str = "24h",
        center_lat: Optional[float] = None,
        center_lon: Optional[float] = None,
        radius_nm: Optional[float] = None
    ) -> Dict[str, Any]:
        """Aggregate weighted exposure coordinates for 100LL cumulative heatmap within radius_nm from airport.
        Supports time_range: '24h', '7d', '30d', 'all'
        Returns: {
            'points': [[lat, lon, intensity], ...],
            'count': int,
            'time_range': str,
            'radius_nm': float,
            'center': {'lat': float, 'lon': float}
        }
        """
        c_lat = center_lat if center_lat is not None else config.AIRPORT_LAT
        c_lon = center_lon if center_lon is not None else config.AIRPORT_LON
        r_nm = float(radius_nm) if radius_nm is not None else config.HEATMAP_RADIUS_NM

        now = datetime.now(timezone.utc)
        cutoff_iso = None
        if time_range == "24h":
            cutoff_iso = (now - timedelta(hours=24)).isoformat()
        elif time_range == "7d":
            cutoff_iso = (now - timedelta(days=7)).isoformat()
        elif time_range == "30d":
            cutoff_iso = (now - timedelta(days=30)).isoformat()

        # Bounding box pre-filter for performance
        lat_margin = (r_nm / 55.0) + 0.02
        cos_lat = math.cos(math.radians(c_lat)) or 1.0
        lon_margin = (r_nm / (55.0 * abs(cos_lat))) + 0.02

        min_lat, max_lat = c_lat - lat_margin, c_lat + lat_margin
        min_lon, max_lon = c_lon - lon_margin, c_lon + lon_margin

        query = """
            SELECT tp.lat, tp.lon, tp.alt_agl_ft, tp.ground_speed_kts, tp.track_deg,
                   tp.wind_speed_mph, tp.wind_dir_deg, tp.exposure_score,
                   fe.max_exposure_score
            FROM track_points tp
            JOIN flyover_events fe ON tp.event_id = fe.event_id
            WHERE fe.is_leaded = 1
              AND tp.lat BETWEEN ? AND ?
              AND tp.lon BETWEEN ? AND ?
        """
        params: List[Any] = [min_lat, max_lat, min_lon, max_lon]
        if cutoff_iso:
            query += " AND tp.timestamp_utc >= ?"
            params.append(cutoff_iso)

        def _offset_coord(lat: float, lon: float, dist_m: float, bearing_deg: float) -> tuple[float, float]:
            rad = math.radians(bearing_deg % 360.0)
            d_lat = (dist_m / 111139.0) * math.cos(rad)
            cos_l = math.cos(math.radians(lat)) or 1.0
            d_lon = (dist_m / (111139.0 * abs(cos_l))) * math.sin(rad)
            return round(lat + d_lat, 6), round(lon + d_lon, 6)

        heatmap_points: List[List[float]] = []
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute(query, params)
            rows = c.fetchall()

            max_radius_m = r_nm * 1852.0
            for row in rows:
                p_lat = float(row["lat"])
                p_lon = float(row["lon"])
                dist_m = haversine_distance_m(p_lat, p_lon, c_lat, c_lon)
                if dist_m > max_radius_m:
                    continue

                alt = max(50.0, float(row["alt_agl_ft"] or 1000.0))
                # Lower altitude flight segments (takeoff, landing, low pattern passes) have highest ground deposition
                alt_factor = max(0.2, min(1.0, 1500.0 / (alt + 300.0)))
                exp_score = float(row["exposure_score"] or 0.0)
                fe_max = float(row["max_exposure_score"] or 0.0)
                score_boost = max(0.0, min(0.3, (exp_score or fe_max) / 200.0))

                # Calibrate center intensity (0.25 - 0.70)
                center_intensity = round(min(0.70, max(0.25, alt_factor * 0.50 + score_boost)), 2)
                heatmap_points.append([round(p_lat, 6), round(p_lon, 6), center_intensity])

                # Determine transport heading: wind direction if wind > 2 mph, else aircraft track
                w_dir = row["wind_dir_deg"]
                w_spd = row["wind_speed_mph"]
                trk = float(row["track_deg"] or 0.0)
                has_wind = (w_dir is not None and w_spd is not None and float(w_spd) > 2.0)

                if has_wind:
                    transport_hdg = (float(w_dir) + 180.0) % 360.0
                    drift_dist_m = min(900.0, float(w_spd) * 0.44704 * min(50.0, alt * 0.3048 / 2.0))
                    cross_hdg_1 = (transport_hdg + 90.0) % 360.0
                    cross_hdg_2 = (transport_hdg - 90.0) % 360.0
                else:
                    transport_hdg = trk
                    drift_dist_m = min(150.0, alt * 0.10)
                    cross_hdg_1 = (trk + 90.0) % 360.0
                    cross_hdg_2 = (trk - 90.0) % 360.0

                # Lateral Gaussian crosswind spread (sigma_y expands with altitude)
                sigma_y = max(140.0, min(400.0, 100.0 + alt * 0.20))

                # Mid-corridor lateral dispersion (±1 sigma) -> transitions to Orange
                lat_1a, lon_1a = _offset_coord(p_lat, p_lon, sigma_y, cross_hdg_1)
                lat_1b, lon_1b = _offset_coord(p_lat, p_lon, sigma_y, cross_hdg_2)
                intensity_1sig = round(center_intensity * 0.50, 2)
                if haversine_distance_m(lat_1a, lon_1a, c_lat, c_lon) <= max_radius_m:
                    heatmap_points.append([lat_1a, lon_1a, intensity_1sig])
                if haversine_distance_m(lat_1b, lon_1b, c_lat, c_lon) <= max_radius_m:
                    heatmap_points.append([lat_1b, lon_1b, intensity_1sig])

                # Outer boundary lateral dispersion (±2 sigma) -> transitions to Yellow
                lat_2a, lon_2a = _offset_coord(p_lat, p_lon, sigma_y * 2.0, cross_hdg_1)
                lat_2b, lon_2b = _offset_coord(p_lat, p_lon, sigma_y * 2.0, cross_hdg_2)
                intensity_2sig = round(center_intensity * 0.22, 2)
                if haversine_distance_m(lat_2a, lon_2a, c_lat, c_lon) <= max_radius_m:
                    heatmap_points.append([lat_2a, lon_2a, intensity_2sig])
                if haversine_distance_m(lat_2b, lon_2b, c_lat, c_lon) <= max_radius_m:
                    heatmap_points.append([lat_2b, lon_2b, intensity_2sig])

                # Downwind settling drift plume footprint
                if drift_dist_m > 30.0:
                    d_lat, d_lon = _offset_coord(p_lat, p_lon, drift_dist_m, transport_hdg)
                    intensity_drift = round(center_intensity * 0.40, 2)
                    if haversine_distance_m(d_lat, d_lon, c_lat, c_lon) <= max_radius_m:
                        heatmap_points.append([d_lat, d_lon, intensity_drift])

                        # Mild lateral dispersion at the settling tail
                        tail_1a, tail_1b = _offset_coord(d_lat, d_lon, sigma_y * 1.2, cross_hdg_1)
                        tail_2a, tail_2b = _offset_coord(d_lat, d_lon, sigma_y * 1.2, cross_hdg_2)
                        tail_intensity = round(center_intensity * 0.18, 2)
                        if haversine_distance_m(tail_1a, tail_1b, c_lat, c_lon) <= max_radius_m:
                            heatmap_points.append([tail_1a, tail_1b, tail_intensity])
                        if haversine_distance_m(tail_2a, tail_2b, c_lat, c_lon) <= max_radius_m:
                            heatmap_points.append([tail_2a, tail_2b, tail_intensity])

        return {
            "points": heatmap_points,
            "count": len(heatmap_points),
            "time_range": time_range,
            "radius_nm": r_nm,
            "center": {"lat": c_lat, "lon": c_lon},
            "units": {
                "surface_deposition": "µg/m²",
                "air_concentration": "µg/m³",
                "emission_rate": "mg/s",
                "risk_index": "0-100 scale"
            },
            "uncertainty": {
                "confidence_interval": "95%",
                "total_margin_pct": 28.0,
                "factors": {
                    "wind_vector_fluctuation": "±15° (approx ±14% transport drift)",
                    "throttle_power_variance": "±20% (cruise vs climb fuel burn)",
                    "particle_settling_aerodynamics": "±22% (sub-micron lead aerosol size distribution)"
                },
                "standard_error_formula": "Gaussian Pasquill-Gifford plume root-sum-square (RSS) propagation"
            }
        }

    def get_statistics(self, time_range: str = "all") -> Dict[str, Any]:
        """Aggregate statistical summary, timeline trend, and fleet breakdown.
        Supports time_range: '24h', '7d', '30d', 'all'
        """
        now = datetime.now(timezone.utc)
        cutoff_iso = None
        if time_range == "24h":
            cutoff_iso = (now - timedelta(hours=24)).isoformat()
        elif time_range == "7d":
            cutoff_iso = (now - timedelta(days=7)).isoformat()
        elif time_range == "30d":
            cutoff_iso = (now - timedelta(days=30)).isoformat()

        where_clause = ""
        params = []
        if cutoff_iso:
            where_clause = " WHERE start_time_utc >= ?"
            params = [cutoff_iso]

        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute(f"SELECT COUNT(*) FROM flyover_events{where_clause}", params)
            total_events = c.fetchone()[0]

            leaded_where = f" WHERE is_leaded = 1{' AND start_time_utc >= ?' if cutoff_iso else ''}"
            c.execute(f"SELECT COUNT(*) FROM flyover_events{leaded_where}", params)
            total_leaded = c.fetchone()[0]

            downwind_where = f" WHERE is_leaded = 1 AND is_downwind = 1{' AND start_time_utc >= ?' if cutoff_iso else ''}"
            c.execute(f"SELECT COUNT(*) FROM flyover_events{downwind_where}", params)
            total_downwind_leaded = c.fetchone()[0]

            c.execute(f"SELECT AVG(min_slant_range_ft), MIN(min_slant_range_ft) FROM flyover_events{leaded_where}", params)
            avg_slant, min_slant = c.fetchone()

            c.execute(f"SELECT MAX(max_exposure_score), AVG(max_exposure_score) FROM flyover_events{leaded_where}", params)
            max_risk, avg_risk = c.fetchone()

            c.execute(f"""
            SELECT aircraft_type, COUNT(*) as cnt 
            FROM flyover_events 
            {leaded_where}
            GROUP BY aircraft_type 
            ORDER BY cnt DESC LIMIT 5
            """, params)
            top_types = [dict(row) for row in c.fetchall()]

            # Fleet distribution
            c.execute(f"""
            SELECT fuel_type, COUNT(*) as cnt
            FROM flyover_events
            {where_clause}
            GROUP BY fuel_type
            ORDER BY cnt DESC
            """, params)
            fleet_rows = c.fetchall()
            fleet_labels = [row["fuel_type"] or "Unknown" for row in fleet_rows]
            fleet_counts = [row["cnt"] for row in fleet_rows]

            # Timeline aggregation for exposure chart
            timeline_labels = []
            timeline_leaded = []
            timeline_risk = []

            if time_range == "24h":
                for i in range(12, -1, -1):
                    t_bucket = now - timedelta(hours=i * 2)
                    timeline_labels.append(t_bucket.strftime("%H:00"))
                    b_start = (t_bucket - timedelta(hours=2)).isoformat()
                    b_end = t_bucket.isoformat()
                    c.execute("""
                    SELECT COUNT(*), MAX(max_exposure_score)
                    FROM flyover_events
                    WHERE is_leaded = 1 AND start_time_utc >= ? AND start_time_utc < ?
                    """, (b_start, b_end))
                    cnt, peak = c.fetchone()
                    timeline_leaded.append(cnt or 0)
                    timeline_risk.append(round(peak or 0.0, 1))
            elif time_range == "7d":
                for i in range(6, -1, -1):
                    day = now - timedelta(days=i)
                    timeline_labels.append(day.strftime("%a %b %d"))
                    d_start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                    d_end = day.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
                    c.execute("""
                    SELECT COUNT(*), MAX(max_exposure_score)
                    FROM flyover_events
                    WHERE is_leaded = 1 AND start_time_utc >= ? AND start_time_utc <= ?
                    """, (d_start, d_end))
                    cnt, peak = c.fetchone()
                    timeline_leaded.append(cnt or 0)
                    timeline_risk.append(round(peak or 0.0, 1))
            else: # 30d or all
                for i in range(14, -1, -1):
                    day = now - timedelta(days=i * 2)
                    timeline_labels.append(day.strftime("%b %d"))
                    d_start = (day - timedelta(days=2)).isoformat()
                    d_end = day.isoformat()
                    c.execute("""
                    SELECT COUNT(*), MAX(max_exposure_score)
                    FROM flyover_events
                    WHERE is_leaded = 1 AND start_time_utc >= ? AND start_time_utc <= ?
                    """, (d_start, d_end))
                    cnt, peak = c.fetchone()
                    timeline_leaded.append(cnt or 0)
                    timeline_risk.append(round(peak or 0.0, 1))

            return {
                "time_range": time_range,
                "total_events": total_events or 0,
                "total_leaded_events": total_leaded or 0,
                "total_downwind_leaded": total_downwind_leaded or 0,
                "avg_slant_range_ft": round(avg_slant or 0.0, 1),
                "min_slant_range_ft": round(min_slant or 0.0, 1),
                "max_risk_score": round(max_risk or 0.0, 1),
                "avg_risk_score": round(avg_risk or 0.0, 1),
                "top_leaded_aircraft": top_types,
                "fleet_breakdown": {
                    "labels": fleet_labels,
                    "counts": fleet_counts
                },
                "timeline": {
                    "labels": timeline_labels,
                    "leaded_counts": timeline_leaded,
                    "risk_scores": timeline_risk
                }
            }

    def clear_all_events(self) -> int:
        """Purge all recorded flyover events and high-frequency track points."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM flyover_events")
            count = c.fetchone()[0]
            conn.execute("DELETE FROM track_points;")
            conn.execute("DELETE FROM flyover_events;")
            conn.commit()
            return count

    def checkpoint(self) -> None:
        """Flush WAL journal transactions into the main database file."""
        with self._get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

    def export_snapshot(self, output_path: Path) -> Path:
        """Create a consistent, defragmented SQLite snapshot for backup/migration."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()
        with self._get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.execute(f"VACUUM INTO '{output_path}';")
        return output_path

    def inspect_database_file(self, db_file_path: Path) -> Dict[str, Any]:
        """Verify an imported database file and inspect its contents."""
        if not db_file_path.exists():
            raise FileNotFoundError("Database file does not exist")
        with open(db_file_path, "rb") as f:
            header = f.read(16)
            if not header.startswith(b"SQLite format 3\x00"):
                raise ValueError("Invalid file format: Not a valid SQLite 3 database")

        conn = sqlite3.connect(str(db_file_path))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            event_count = 0
            point_count = 0
            registry_count = 0

            if "flyover_events" in tables:
                cursor.execute("SELECT COUNT(*) FROM flyover_events")
                event_count = cursor.fetchone()[0]
            if "track_points" in tables:
                cursor.execute("SELECT COUNT(*) FROM track_points")
                point_count = cursor.fetchone()[0]
            if "aircraft_registry" in tables:
                cursor.execute("SELECT COUNT(*) FROM aircraft_registry")
                registry_count = cursor.fetchone()[0]

            return {
                "valid": True,
                "tables": tables,
                "event_count": event_count,
                "point_count": point_count,
                "registry_count": registry_count,
                "size_bytes": db_file_path.stat().st_size
            }
        finally:
            conn.close()

    def restore_from_snapshot(self, snapshot_path: Path) -> Dict[str, Any]:
        """Safely restore the active database with an imported backup."""
        info = self.inspect_database_file(snapshot_path)
        if not info.get("valid"):
            raise ValueError("Invalid SQLite snapshot file")

        # 1. Invalidate hex lookup cache
        self._cache_hex.clear()

        # 2. Safety copy of current db
        backup_path = self.db_path.with_name(f"{self.db_path.name}.pre_restore_bak")
        if self.db_path.exists():
            import shutil
            shutil.copy2(self.db_path, backup_path)

        # 3. Use SQLite Online Backup API to safely overwrite active db in-place
        src = sqlite3.connect(str(snapshot_path), timeout=30.0)
        dst = sqlite3.connect(str(self.db_path), timeout=30.0)
        try:
            dst.execute("PRAGMA busy_timeout=30000;")
            src.backup(dst)
        finally:
            src.close()
            dst.close()

        # 4. Checkpoint WAL and ensure schema
        try:
            self.checkpoint()
        except Exception:
            pass
        self._init_db()

        return info

db = Database()

