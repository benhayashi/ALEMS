"""Atmospheric dispersion and aerosolized lead exposure risk model for ALEMS.
Calculates emission rates, wind alignment, downwind transport, and exposure risk scores.
"""

import math
from typing import Dict, Any, Tuple, Optional
from alems.config import config
from alems.geodesy import distance_ft, haversine_distance_m, initial_bearing

class DispersionModel:
    """Computes downwind aerosolized lead plume transport and exposure risk."""

    def __init__(self, half_angle_deg: float = config.PLUME_DISPERSION_HALF_ANGLE_DEG):
        self.half_angle_deg = half_angle_deg

    @staticmethod
    def calculate_emission_rate_g_per_s(
        aircraft_meta: Dict[str, Any],
        vertical_rate_fpm: float = 0.0,
        ground_speed_kts: float = 100.0,
        altitude_agl_ft: float = 1000.0
    ) -> float:
        """Estimate instantaneous lead emission rate in grams per second.
        Reciprocating piston engines emit lead compounds (tetraethyllead + ethylene dibromide scavengers).
        Power factor varies with phase of flight (climb/takeoff vs cruise vs descent).
        """
        if not aircraft_meta.get("is_leaded", False):
            return 0.0

        burn_rate_gph = float(aircraft_meta.get("burn_rate_gph", 10.5))
        lead_per_gal = float(aircraft_meta.get("lead_content_g_per_gal", config.LEAD_CONTENT_GRAMS_PER_GALLON))

        # Determine power factor based on telemetry
        if vertical_rate_fpm > 300:
            # Climb / departure power (full throttle, rich mixture)
            power_factor = 1.0
        elif vertical_rate_fpm < -300:
            # Descent / approach power
            power_factor = 0.45
        elif ground_speed_kts > 130 and altitude_agl_ft > 1500:
            # High speed cruise
            power_factor = 0.75
        else:
            # Pattern altitude / cruise
            power_factor = 0.65

        effective_gph = burn_rate_gph * power_factor
        lead_grams_per_sec = (effective_gph * lead_per_gal) / 3600.0
        return lead_grams_per_sec

    @staticmethod
    def calculate_wind_alignment(
        bearing_ac_to_house: float,
        wind_from_deg: float
    ) -> Tuple[float, bool]:
        """Determine whether the house is downwind of the aircraft.
        wind_from_deg: direction the wind is blowing FROM (0-360).
        Plume moves TOWARDS (wind_from_deg + 180) % 360.
        Returns:
            angular_offset_deg: difference between plume vector and bearing to house (0 - 180).
            is_downwind: True if house is within the lateral plume expansion cone.
        """
        plume_vector = (wind_from_deg + 180.0) % 360.0
        diff = abs(plume_vector - bearing_ac_to_house) % 360.0
        if diff > 180.0:
            diff = 360.0 - diff

        is_downwind = diff <= config.PLUME_DISPERSION_HALF_ANGLE_DEG
        return diff, is_downwind

    def calculate_point_exposure(
        self,
        lat: float,
        lon: float,
        alt_msl_ft: float,
        ground_speed_kts: float,
        vertical_rate_fpm: float,
        aircraft_meta: Dict[str, Any],
        wind_speed_mph: float,
        wind_dir_deg: float,
        home_lat: Optional[float] = None,
        home_lon: Optional[float] = None,
        home_elev_ft: Optional[float] = None
    ) -> Dict[str, Any]:
        """Calculate detailed exposure metrics for a single telemetry observation."""
        h_lat = home_lat if home_lat is not None else config.HOME_LAT
        h_lon = home_lon if home_lon is not None else config.HOME_LON
        h_elev = home_elev_ft if home_elev_ft is not None else config.HOME_ELEV_MSL_FT
        # Non-leaded aircraft (Turbines, Jets, Electric) emit 0 lead
        is_leaded = aircraft_meta.get("is_leaded", False)
        if not is_leaded:
            return {
                "is_leaded": False,
                "lead_emission_rate_g_s": 0.0,
                "lead_emission_rate_mg_s": 0.0,
                "angular_offset_deg": 0.0,
                "is_downwind": False,
                "exposure_score": 0.0,
                "exposure_level": "NONE (Unleaded / Jet-A)",
                "estimated_ground_conc_ug_m3": 0.0
            }

        # Spatial geometry
        dist_m = haversine_distance_m(lat, lon, h_lat, h_lon)
        dist_ft = dist_m * 3.28084
        alt_agl_ft = max(50.0, float(alt_msl_ft) - h_elev)
        alt_agl_m = alt_agl_ft * 0.3048

        # Bearing from aircraft to house
        bearing_to_house = initial_bearing(lat, lon, h_lat, h_lon)

        # Wind transport & alignment
        angular_offset, is_downwind = self.calculate_wind_alignment(bearing_to_house, wind_dir_deg)

        # Emission rate
        q_g_s = self.calculate_emission_rate_g_per_s(
            aircraft_meta,
            vertical_rate_fpm=vertical_rate_fpm,
            ground_speed_kts=ground_speed_kts,
            altitude_agl_ft=alt_agl_ft
        )
        q_mg_s = q_g_s * 1000.0

        # Gaussian dispersion physics
        # Convert wind speed to m/s, floor at 0.5 m/s to prevent division by zero in calm air
        wind_speed_ms = max(0.5, float(wind_speed_mph) * 0.44704)

        # Effective downwind and crosswind distances
        theta_rad = math.radians(angular_offset)
        downwind_dist_m = max(10.0, dist_m * math.cos(theta_rad))
        crosswind_dist_m = dist_m * math.sin(theta_rad)

        # Pasquill-Gifford dispersion parameters (Neutral Class D typical boundary layer)
        # sigma_y = 0.08 * x * (1 + 0.0001*x)^(-0.5)
        # sigma_z = 0.06 * x * (1 + 0.0015*x)^(-0.5)
        sigma_y = max(10.0, 0.08 * downwind_dist_m / math.sqrt(1.0 + 0.0001 * downwind_dist_m))
        sigma_z = max(5.0, 0.06 * downwind_dist_m / math.sqrt(1.0 + 0.0015 * downwind_dist_m))

        # Ground level concentration (g/m3) from elevated plume:
        # C = (Q / (pi * u * sigma_y * sigma_z)) * exp(-y^2 / (2*sigma_y^2)) * exp(-H^2 / (2*sigma_z^2))
        try:
            exp_cross = math.exp(-0.5 * (crosswind_dist_m / sigma_y) ** 2)
            exp_vert = math.exp(-0.5 * (alt_agl_m / sigma_z) ** 2)
            conc_g_m3 = (q_g_s / (math.pi * wind_speed_ms * sigma_y * sigma_z)) * exp_cross * exp_vert
        except OverflowError:
            conc_g_m3 = 0.0

        conc_ug_m3 = conc_g_m3 * 1e6  # Micrograms per cubic meter

        # Proximity weighting factor:
        # Even if crosswind is slight, direct close overhead flyovers (< 1500 ft slant range)
        # have wake vortex downwash that forces exhaust down to ground level regardless of macro wind
        slant_range_ft = math.sqrt(dist_ft ** 2 + alt_agl_ft ** 2)
        overhead_factor = max(0.0, 1.0 - (slant_range_ft / 3000.0))

        # Composite Exposure Score (0 - 100):
        # Calibrated against ambient lead health benchmarks:
        # EPA National Ambient Air Quality Standard (NAAQS) for lead is 0.15 ug/m3 (3-month avg).
        # Short-term peak flyover plumes can reach 0.5 - 5.0 ug/m3 for several seconds.
        raw_score = (conc_ug_m3 * 25.0) + (overhead_factor * 40.0 * (1.0 if is_downwind else 0.4))
        score = min(100.0, max(0.0, round(raw_score, 1)))

        if score >= 70.0:
            level = "CRITICAL / DIRECT PLUME"
        elif score >= 40.0:
            level = "ELEVATED DOWNWIND"
        elif score >= 15.0:
            level = "MODERATE"
        elif score > 0.0:
            level = "LOW / UPWIND"
        else:
            level = "NEGLIGIBLE"

        return {
            "is_leaded": True,
            "lead_emission_rate_g_s": round(q_g_s, 6),
            "lead_emission_rate_mg_s": round(q_mg_s, 3),
            "angular_offset_deg": round(angular_offset, 1),
            "is_downwind": is_downwind,
            "exposure_score": score,
            "exposure_level": level,
            "estimated_ground_conc_ug_m3": round(conc_ug_m3, 4),
            "slant_range_ft": round(slant_range_ft, 1)
        }

dispersion_model = DispersionModel()
