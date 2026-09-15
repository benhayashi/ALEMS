"""Corroborating log exporter for ALEMS.
Produces standardized CSV and JSON records formatted for scientific and evidentiary corroboration
with official FAA/NTSB/FlightAware flight tracks and NOAA weather observations.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from alems.config import config
from alems.storage.db import db

class LogExporter:
    """Exports structured flight and lead risk records for evidentiary corroboration."""

    def __init__(self, export_dir: Optional[Path] = None):
        self.export_dir = export_dir or config.EXPORTS_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_events_csv(
        self,
        output_filename: Optional[str] = None,
        leaded_only: bool = False,
        limit: int = 1000
    ) -> Path:
        """Generate an audit-ready CSV file of flyover events."""
        if not output_filename:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_filename = f"alems_flyover_corroboration_{ts}.csv"

        target_path = self.export_dir / output_filename
        events = db.get_recent_events(limit=limit, leaded_only=leaded_only)

        fieldnames = [
            "event_id",
            "cpa_time_utc",
            "cpa_time_local",
            "start_time_utc",
            "end_time_utc",
            "total_duration_sec",
            "icao_hex",
            "tail_number",
            "aircraft_type",
            "manufacturer",
            "model_name",
            "engine_type",
            "fuel_type",
            "is_leaded",
            "cpa_lat",
            "cpa_lon",
            "min_distance_ft",
            "min_slant_range_ft",
            "cpa_alt_msl_ft",
            "cpa_alt_agl_ft",
            "cpa_ground_speed_kts",
            "cpa_track_deg",
            "cpa_vert_rate_fpm",
            "ecowitt_wind_speed_mph",
            "ecowitt_wind_dir_deg",
            "ecowitt_temp_f",
            "ecowitt_humidity",
            "aerodrome_station",
            "aerodrome_wind_speed_kts",
            "aerodrome_wind_dir_deg",
            "wind_alignment_deg",
            "is_downwind",
            "lead_emission_rate_mg_s",
            "max_exposure_score",
            "avg_exposure_score",
            "exposure_level",
            "corroboration_hash"
        ]

        with open(target_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for ev in events:
                writer.writerow(ev)

        return target_path

    def export_event_trajectory_csv(self, event_id: str) -> Optional[Path]:
        """Export high-frequency 1-second trajectory points for an individual flyover pass."""
        points = db.get_event_points(event_id)
        if not points:
            return None

        filename = f"alems_trajectory_{event_id}.csv"
        target_path = self.export_dir / filename

        fieldnames = [
            "event_id",
            "timestamp_utc",
            "lat",
            "lon",
            "alt_msl_ft",
            "alt_agl_ft",
            "ground_speed_kts",
            "track_deg",
            "vertical_rate_fpm",
            "dist_to_house_ft",
            "slant_range_ft",
            "bearing_to_house",
            "wind_speed_mph",
            "wind_dir_deg",
            "is_downwind",
            "exposure_score"
        ]

        with open(target_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for pt in points:
                writer.writerow(pt)

        return target_path

exporter = LogExporter()
