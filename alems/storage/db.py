"""SQLite Database Management for ALEMS.
Stores immutable flyover events, high-frequency track records, and weather observations.
"""

import sqlite3
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from alems.config import config

class Database:
    """Handles SQLite persistence for flight logs and exposure records."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.DATABASE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

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

            CREATE INDEX IF NOT EXISTS idx_events_start ON flyover_events(start_time_utc);
            CREATE INDEX IF NOT EXISTS idx_events_hex ON flyover_events(icao_hex);
            CREATE INDEX IF NOT EXISTS idx_events_leaded ON flyover_events(is_leaded);
            CREATE INDEX IF NOT EXISTS idx_events_downwind ON flyover_events(is_downwind);
            CREATE INDEX IF NOT EXISTS idx_points_event ON track_points(event_id);
            """)

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

    def get_statistics(self) -> Dict[str, Any]:
        """Aggregate statistical summary for the dashboard."""
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM flyover_events")
            total_events = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM flyover_events WHERE is_leaded = 1")
            total_leaded = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM flyover_events WHERE is_leaded = 1 AND is_downwind = 1")
            total_downwind_leaded = c.fetchone()[0]

            c.execute("SELECT AVG(min_slant_range_ft), MIN(min_slant_range_ft) FROM flyover_events WHERE is_leaded = 1")
            avg_slant, min_slant = c.fetchone()

            c.execute("SELECT MAX(max_exposure_score), AVG(max_exposure_score) FROM flyover_events WHERE is_leaded = 1")
            max_risk, avg_risk = c.fetchone()

            c.execute("""
            SELECT aircraft_type, COUNT(*) as cnt 
            FROM flyover_events 
            WHERE is_leaded = 1 
            GROUP BY aircraft_type 
            ORDER BY cnt DESC LIMIT 5
            """)
            top_types = [dict(row) for row in c.fetchall()]

            return {
                "total_events": total_events or 0,
                "total_leaded_events": total_leaded or 0,
                "total_downwind_leaded": total_downwind_leaded or 0,
                "avg_slant_range_ft": round(avg_slant or 0.0, 1),
                "min_slant_range_ft": round(min_slant or 0.0, 1),
                "max_risk_score": round(max_risk or 0.0, 1),
                "avg_risk_score": round(avg_risk or 0.0, 1),
                "top_leaded_aircraft": top_types
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

db = Database()
