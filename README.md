# ALEMS — Aerial Lead Exposure Monitoring System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)

An open-source, standalone, evidentiary-grade monitoring platform designed to quantify aircraft proximity, classify 100LL leaded avgas piston aircraft, integrate dual-layer wind telemetry (compensating for tree-line sheltering), model aerosolized lead downwind dispersion, and generate tamper-evident corroboration logs cross-referenced with official FAA and NOAA records.

---

## Key Features

- 🛩️ **Targeted 100LL Aircraft Identification**: Integrates an ICAO 8643 database and FAA N-number decoding to automatically classify piston aircraft burning 100LL leaded fuel ($2.12\text{ g Pb/gallon}$) versus unleaded turboprops, jets, and military traffic.
- 📍 **Universal Location Setup**:
  - Search any street address (using free OpenStreetMap Nominatim geocoding).
  - Enter exact Latitude, Longitude, and Elevation.
  - Or click / drag the **interactive pin directly on the radar map** to position your property.
- 🛫 **Global Airfield & Runway Alignment**:
  - Enter any ICAO/FAA airport code (e.g. `2W6`, `KRHV`, `KSMO`, `KGAI`, `KPAO`, `KFRG`, etc.) to automatically populate coordinates, elevation, and runway vectors.
  - Dynamically renders runway centerlines and extended departure corridors on the map.
- 🌬️ **Dual-Layer Wind Monitoring**:
  - **Ground Microclimate**: Ingests local breathing-level wind, gusts, and temperature from your **Ecowitt weather station via Home Assistant**.
  - **Winds Aloft (Above Tree Line)**: Ingests official aerodrome observations (**2W6 AWOS / KNHK ASOS**) at standard 10m mast height above tree canopy friction to govern pattern-altitude plume steering.
- 📐 **Gaussian Downwind Dispersion & 3D Proximity**:
  - Calculates 3D slant range $\sqrt{d_{xy}^2 + z_{agl}^2}$ and Closest Point of Approach (CPA).
  - Determines relative wind alignment and projects dynamic downwind exhaust plume cones from aircraft.
  - Computes a physically calibrated **Lead Exposure Risk Score** (0–100 index).
- 🗺️ **100% Free Base Maps (Zero API Key Required)**:
  - **Dark Radar Canvas**: High-contrast dark basemap.
  - **OpenStreetMap Standard**: Road names, terrain, and landmarks.
  - **Esri High-Resolution Satellite Imagery**: Aerial imagery of buildings, runways, and tree canopies.
- 📋 **Evidentiary Corroboration Logs**:
  - Generates SQLite and audit-ready CSV logs containing full aircraft kinematics, local wind, airport wind, downwind status, risk index, and a **SHA-256 cryptographic hash** for legal or regulatory verification.
- 📱 **Mobile-Friendly Web GUI**:
  - Responsive layout optimized for desktop, tablets, and smartphones.
  - Real-time WebSocket push updates from the background daemon.

---

## Standalone Docker Deployment

ALEMS is fully containerized and can run standalone on any server, desktop, or Raspberry Pi.

```bash
# 1. Clone the repository
git clone https://github.com/benhayashi/ALEMS.git
cd ALEMS

# 2. Start ALEMS container via Docker Compose
docker compose up -d --build
```

Access the Web Dashboard at: **`http://localhost:8085`** (or your server's IP address on port 8085).

All configuration settings, the SQLite database (`data/alems.db`), and generated CSV exports (`exports/`) persist automatically on your host machine.

---

## Native Installation (Linux / macOS / Windows)

### 1. Prerequisites
- Python 3.10+
- `readsb` receiver running on your local network (e.g. Raspberry Pi 4).

### 2. Setup
```bash
git clone https://github.com/benhayashi/ALEMS.git
cd ALEMS

python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 3. Running
```bash
# Start ALEMS daemon and web server on port 8085
./venv/bin/python3 run.py start

# Start with realistic simulated airfield traffic for immediate testing
./venv/bin/python3 run.py start --simulate
```

### 4. Diagnostic Status Check
To test connectivity to your Raspberry Pi 4 readsb receiver, Home Assistant, and NOAA weather feed:
```bash
./venv/bin/python3 run.py status
```

### 5. Exporting Corroboration CSV Logs
```bash
# Export all recorded flyovers to CSV
./venv/bin/python3 run.py export

# Export only 100LL leaded piston aircraft
./venv/bin/python3 run.py export --leaded-only --output leaded_passes.csv
```

### 6. Running Automated Test Suite
```bash
PYTHONPATH=. ./venv/bin/pytest -v
```

---

## Configuration

Settings can be customized anytime directly in the **Settings** tab of the Web GUI or through environment variables / `data/config.json`:

| Setting | Default Value | Description |
|---|---|---|
| Property Address | `44081 Beaver Creek Dr, California, MD 20619` | Street address (or search via Nominatim) |
| Property Coordinates | `38.2720`, `-76.4950` (110 ft MSL) | Lat/Lon or set by dropping pin on map |
| Airfield Code | `2W6` | Airport code (auto-populates coords & runway) |
| Active Geofence | `3.5 NM` | Aircraft tracking radius |
| Flyover Event Trigger | `1.5 NM` | Close proximity trigger threshold |
| readsb Feed URL | `http://raspberrypi.local/tar1090/data/aircraft.json` | ADS-B JSON feed from Raspberry Pi |
| Home Assistant URL | `http://homeassistant.local:8123` | Home Assistant API for Ecowitt sensors |
| Home Assistant Token | `""` | Long-Lived Access Token |

---

## Hardware & Sensor Integration

### Raspberry Pi 4 (`readsb`)
1. In `readsb` / `tar1090`, telemetry is accessible at:
   - `http://<YOUR_PI_IP>/tar1090/data/aircraft.json`
   - or `http://<YOUR_PI_IP>:8080/data/aircraft.json`
2. Enter this URL in the ALEMS Settings tab and click **Save & Apply Configuration**.

### Ecowitt Weather Station (via Home Assistant)
1. Ensure your Ecowitt Home Assistant integration provides:
   - `sensor.ecowitt_wind_speed`
   - `sensor.ecowitt_wind_direction`
   - `sensor.ecowitt_wind_gust`
   - `sensor.ecowitt_temperature`
2. Create a Long-Lived Access Token under Home Assistant Profile $\rightarrow$ Security $\rightarrow$ Long-Lived Access Tokens.
3. Paste the token into the ALEMS Settings tab.
4. *Tree Line Sheltering Compensation:* ALEMS monitors both your ground-level Ecowitt sensor (breathing microclimate) and the aerodrome observation at standard 10m mast height above the tree line to deliver scientifically sound evidence.

---

## Corroborating Evidence Log Schema

Every flyover event logged to SQLite and exported to CSV contains the following fields to facilitate evidentiary corroboration with official FAA/NTSB/FlightAware radar data and NWS archives:

| Column Header | Description |
|---|---|
| `event_id` | Unique UUID for the flyover pass |
| `cpa_time_utc` | Exact UTC timestamp at Closest Point of Approach (ISO-8601) |
| `cpa_time_local` | Local Time timestamp at CPA |
| `icao_hex` | 24-bit Mode S transponder hex code (e.g., `A1B2C3`) |
| `tail_number` | FAA N-number (e.g., `N172SP`) |
| `aircraft_type` | ICAO 8643 aircraft type designator (e.g., `C172`, `PA28`, `SR22`) |
| `manufacturer` | Aircraft manufacturer |
| `model_name` | Model name and engine configuration |
| `engine_type` | Engine technology (`Piston` vs `Turboprop` vs `Jet`) |
| `fuel_type` | Fuel consumed (`100LL` Leaded AvGas vs `Jet-A` Unleaded) |
| `is_leaded` | Binary flag (`1` for 100LL piston, `0` for unleaded) |
| `min_distance_ft` | Minimum horizontal distance from house at CPA (feet) |
| `min_slant_range_ft` | 3D Euclidean distance $\sqrt{d_{xy}^2 + \text{agl}^2}$ at CPA (feet) |
| `cpa_alt_msl_ft` | Altitude above Mean Sea Level at CPA |
| `cpa_alt_agl_ft` | Altitude Above Ground Level at CPA |
| `cpa_ground_speed_kts`| Aircraft speed over ground in knots |
| `cpa_track_deg` | Aircraft track over ground in degrees (0–360) |
| `cpa_vert_rate_fpm` | Climb/descent rate (positive = climb, negative = descent) |
| `ecowitt_wind_speed_mph`| Local ground wind speed from Ecowitt |
| `ecowitt_wind_dir_deg`| Local ground wind direction from Ecowitt |
| `aerodrome_station` | Aerodrome reference station (e.g. `KNHK` / `2W6`) |
| `aerodrome_wind_speed_kts`| Aerodrome wind speed at 10m mast height above tree canopy |
| `aerodrome_wind_dir_deg`| Aerodrome wind direction |
| `wind_alignment_deg` | Angular offset between aircraft-to-house bearing and wind drift |
| `is_downwind` | `1` if property was directly downwind in the exhaust plume |
| `lead_emission_rate_mg_s`| Estimated lead emission rate in mg/sec |
| `max_exposure_score`| Peak lead exposure risk index (0–100 scale) |
| `avg_exposure_score`| Average exposure risk index across pass duration |
| `exposure_level` | Classification (`CRITICAL`, `ELEVATED`, `MODERATE`, `LOW`, `NONE`) |
| `corroboration_hash` | SHA-256 cryptographic hash of event metadata and trajectory points |

---

## Database & Configuration Migration (Docker / Raspberry Pi)

ALEMS features a built-in GUI migration engine designed for moving between machines or deploying to a standalone Raspberry Pi:

### Exporting from Existing Instance
In the **Settings** tab under **Database & Configuration Migration**:
- **Full Bundle (.zip)**: Exports a complete self-contained package containing `alems.db` (clean defragmented SQLite snapshot), `config.yaml`, `config.json`, and `manifest.json`.
- **Database (.db)**: Downloads the live SQLite database snapshot with 440k+ FAA aircraft records and flyovers.
- **Settings (.yaml)**: Downloads active settings formatted for Docker Compose or standalone `config.yaml`.

### Importing into a New Docker / Raspberry Pi Instance
1. Deploy ALEMS on your new device using `docker compose up -d`.
2. Open the ALEMS Web GUI at `http://<NEW_DEVICE_IP>:8085`.
3. In **Settings** $\rightarrow$ **Database & Configuration Migration**, drag and drop your `.zip` bundle, `.db` database, or `.yaml` configuration into the import zone.
4. Preview the validated package contents, record counts, and schema.
5. Click **Confirm & Restore**. The engine hot-swaps the database using SQLite's online transactional backup API, syncs configuration settings, and broadcasts real-time state updates across all connected clients.
6. *Automated Safety Backup:* Before any restore operation, ALEMS automatically creates a `.pre_restore_bak` copy of the existing database.

---

## License

This project is licensed under the [MIT License](LICENSE) — a permissive license that allows free commercial, private, educational, and public use, modification, and distribution.

