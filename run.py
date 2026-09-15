#!/usr/bin/env python3
"""Unified CLI Runner for Aerial Lead Exposure Monitoring System (ALEMS)."""

import argparse
import sys
import uvicorn
from alems.config import config
from alems.daemon import daemon
from alems.storage.exporter import exporter
from alems.storage.db import db
from alems.collectors.adsb_client import adsb_client
from alems.collectors.weather_client import weather_collector

def cmd_start(args):
    """Start the ALEMS daemon and FastAPI web server."""
    if args.simulate:
        daemon.simulation_mode = True
        print("[*] Simulation Mode: ENABLED (Injecting 2W6 traffic patterns)")

    print(f"=================================================================")
    print(f"  ALEMS - Aerial Lead Exposure Monitoring System")
    print(f"  Property: {config.HOME_ADDRESS}")
    print(f"  Coordinates: {config.HOME_LAT}, {config.HOME_LON} (Elev: {config.HOME_ELEV_MSL_FT} ft)")
    print(f"  Airfield: {config.AIRPORT_NAME} ({config.AIRPORT_ID}) - 3.7 NM")
    print(f"  Web Dashboard: http://{args.host}:{args.port}")
    print(f"=================================================================")

    uvicorn.run("alems.server:app", host=args.host, port=args.port, reload=False)

def cmd_export(args):
    """Export audit-ready corroboration CSV log."""
    path = exporter.export_events_csv(output_filename=args.output, leaded_only=args.leaded_only)
    print(f"[+] Corroboration CSV exported successfully:")
    print(f"    {path}")

def cmd_status(args):
    """Display system and sensor connection status."""
    print("ALEMS Sensor & Network Diagnostics:")
    print(f"  - Monitored Property: {config.HOME_ADDRESS}")
    print(f"  - Database: {config.DATABASE_PATH} (Size: {config.DATABASE_PATH.stat().st_size if config.DATABASE_PATH.exists() else 0} bytes)")
    
    # ADS-B check
    print(f"  - ADS-B Receiver: {config.READSB_URL}")
    raw_ac = adsb_client.fetch_raw_aircraft()
    if adsb_client.is_connected:
        print(f"    Status: CONNECTED ({len(raw_ac)} aircraft currently tracked)")
    else:
        print(f"    Status: OFFLINE / UNREACHABLE ({adsb_client.last_error})")

    # Weather check
    weather = weather_collector.get_effective_wind()
    eco = weather.get("ecowitt", {})
    aero = weather.get("aerodrome", {})
    print(f"  - Ecowitt Weather Station (via Home Assistant):")
    print(f"    Status: {eco.get('status')} | Wind: {eco.get('wind_speed_mph')} mph @ {eco.get('wind_dir_deg')}°")
    print(f"  - Aerodrome Weather (2W6 / KNHK):")
    print(f"    Status: {aero.get('status')} | Station: {aero.get('station')} | Wind: {aero.get('wind_speed_kts')} kts @ {aero.get('wind_dir_deg')}°")

    stats = db.get_statistics()
    print(f"  - Database Summary:")
    print(f"    Total Flyovers: {stats['total_events']}")
    print(f"    100LL Leaded Passes: {stats['total_leaded_events']}")
    print(f"    Downwind Plume Events: {stats['total_downwind_leaded']}")

def main():
    parser = argparse.ArgumentParser(description="ALEMS - Aerial Lead Exposure Monitoring System")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Start command
    p_start = subparsers.add_parser("start", help="Start ALEMS daemon and web dashboard")
    p_start.add_argument("--host", default=config.HOST, help="Host to bind server to")
    p_start.add_argument("--port", type=int, default=config.PORT, help="Port to bind server to")
    p_start.add_argument("--simulate", action="store_true", help="Run with simulated 2W6 traffic")

    # Export command
    p_export = subparsers.add_parser("export", help="Export corroboration CSV logs")
    p_export.add_argument("--output", default=None, help="Output CSV filename")
    p_export.add_argument("--leaded-only", action="store_true", help="Export only 100LL leaded aircraft")

    # Status command
    subparsers.add_parser("status", help="Check sensor and receiver connectivity")

    args = parser.parse_args()

    if args.command == "start" or args.command is None:
        if args.command is None:
            # Default to start
            args.host = config.HOST
            args.port = config.PORT
            args.simulate = True # Default simulate if invoked without args for easy trial
        cmd_start(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "status":
        cmd_status(args)

if __name__ == "__main__":
    main()
