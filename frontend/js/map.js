/**
 * Leaflet Map & Radar Visualizer for ALEMS.
 * Uses 100% Free Base Maps (Zero API Key Required):
 * - Dark Radar Canvas
 * - OpenStreetMap Standard (OSM)
 * - Esri World Imagery (High-Resolution Satellite)
 * Supports interactive pin placement, custom property coordinates, and dynamic runway vectors.
 */

let map = null;
let baseLayers = {};
let layerControl = null;
let aircraftMarkers = {};
let aircraftTracks = {};
let plumePolygons = {};
let homeMarker = null;
let runwayLine = null;
let runwayThresholdMarkers = [];
let extendedCenterline = null;
let proximityCircles = [];
let isPinDropMode = false;

const NM_TO_METERS = 1852.0;

function initMap(homeConfig, airportConfig) {
  if (map) {
    recenterAndRedraw(homeConfig, airportConfig);
    return;
  }
  if (typeof L === 'undefined') {
    console.warn("Leaflet library is not yet loaded");
    return;
  }

  const homeLat = (homeConfig && homeConfig.lat) ? homeConfig.lat : 38.2720;
  const homeLon = (homeConfig && homeConfig.lon) ? homeConfig.lon : -76.4950;

  map = L.map('map', {
    center: [homeLat, homeLon],
    zoom: 13,
    zoomControl: true,
    attributionControl: false
  });

  // Base Map Layer 1: Esri World Dark Gray Canvas (100% Free, zero API key, no watermark)
  const esriDarkBase = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 16
  });
  const esriDarkRef = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 16
  });
  const darkLayer = L.layerGroup([esriDarkBase, esriDarkRef]);

  // Base Map Layer 2: OpenStreetMap Standard (100% Free, zero API key)
  const osmLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19
  });

  // Base Map Layer 3: Esri World Imagery Satellite (100% Free, zero API key)
  const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19
  });
  const satelliteLabels = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19
  });
  const satLayerGroup = L.layerGroup([satelliteLayer, satelliteLabels]);

  // Default to Dark Radar layer
  darkLayer.addTo(map);

  baseLayers = {
    "Dark Radar": darkLayer,
    "Street Map (OSM)": osmLayer,
    "Satellite Imagery": satLayerGroup
  };

  layerControl = L.control.layers(baseLayers, null, { position: 'topright' }).addTo(map);

  // Click / tap on map listener for Pin Drop Mode
  map.on('click', (e) => {
    if (isPinDropMode) {
      setHomeLocation(e.latlng.lat, e.latlng.lng);
      togglePinDropMode(false);
    }
  });

  // Draw home and airfield
  drawHomeMarker(homeConfig);
  drawProximityRings(homeLat, homeLon);
  drawAirportRunway(airportConfig);
}

function recenterAndRedraw(homeConfig, airportConfig) {
  if (!map) return;

  const homeLat = (homeConfig && homeConfig.lat) ? homeConfig.lat : 38.2720;
  const homeLon = (homeConfig && homeConfig.lon) ? homeConfig.lon : -76.4950;

  drawHomeMarker(homeConfig);
  drawProximityRings(homeLat, homeLon);
  drawAirportRunway(airportConfig);
  map.setView([homeLat, homeLon], 13);
}

function drawHomeMarker(homeConfig) {
  if (!map) return;
  const homeLat = (homeConfig && homeConfig.lat) ? homeConfig.lat : 38.2720;
  const homeLon = (homeConfig && homeConfig.lon) ? homeConfig.lon : -76.4950;
  const addr = (homeConfig && homeConfig.address) ? homeConfig.address : "Monitored Property";
  const elev = (homeConfig && homeConfig.elev_msl_ft) ? homeConfig.elev_msl_ft : 110.0;

  const houseIcon = L.divIcon({
    className: 'property-marker-container',
    html: `
      <div style="position: relative; width: 26px; height: 26px; cursor: move;">
        <div style="position: absolute; width: 26px; height: 26px; border-radius: 50%; background: rgba(245, 158, 11, 0.3); animation: pulse 2s infinite;"></div>
        <div style="position: absolute; top: 5px; left: 5px; width: 16px; height: 16px; border-radius: 50%; background: #f59e0b; border: 2px solid #fff; box-shadow: 0 0 10px #f59e0b;"></div>
      </div>
    `,
    iconSize: [26, 26],
    iconAnchor: [13, 13]
  });

  if (homeMarker) {
    map.removeLayer(homeMarker);
  }

  homeMarker = L.marker([homeLat, homeLon], {
    icon: houseIcon,
    draggable: true,
    title: "Drag pin to adjust monitored property location"
  }).addTo(map);

  homeMarker.bindPopup(`
    <div style="font-family: sans-serif; min-width: 180px; font-size: 0.85rem;">
      <strong style="color: #f59e0b;">Monitored Property</strong><br/>
      ${addr}<br/>
      <hr style="border: 0; border-top: 1px solid #444; margin: 4px 0;"/>
      Lat: ${homeLat.toFixed(5)}, Lon: ${homeLon.toFixed(5)}<br/>
      Elev: ${elev} ft MSL<br/>
      <small style="color: #94a3b8;">(Drag pin or click map to change)</small>
    </div>
  `);

  homeMarker.on('dragend', (e) => {
    const pos = e.target.getLatLng();
    setHomeLocation(pos.lat, pos.lng);
  });
}

function setHomeLocation(lat, lon, panMap = false) {
  const roundedLat = parseFloat(lat.toFixed(6));
  const roundedLon = parseFloat(lon.toFixed(6));

  const latInput = document.getElementById('setting-home-lat');
  const lonInput = document.getElementById('setting-home-lon');
  if (latInput) latInput.value = roundedLat;
  if (lonInput) lonInput.value = roundedLon;

  if (homeMarker) {
    homeMarker.setLatLng([roundedLat, roundedLon]);
  } else {
    drawHomeMarker({ lat: roundedLat, lon: roundedLon });
  }
  drawProximityRings(roundedLat, roundedLon);

  if (panMap && map) {
    map.setView([roundedLat, roundedLon], Math.max(map.getZoom(), 17));
    if (homeMarker) {
      setTimeout(() => homeMarker.openPopup(), 200);
    }
  }

  // Auto-save via API so the user doesn't even need to click save
  fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      home_lat: roundedLat,
      home_lon: roundedLon
    })
  }).then(r => r.json()).then(res => {
    if (res.config && typeof applyConfigToUI === 'function') {
      applyConfigToUI(res.config);
    }
    if (typeof showToast === 'function') {
      showToast(`📍 Property location set to: ${roundedLat}, ${roundedLon}`);
    }
  }).catch(err => {
    console.error("Failed to auto-save location:", err);
  });
}

function togglePinDropMode(enable) {
  isPinDropMode = (enable !== undefined) ? enable : !isPinDropMode;

  const radarPane = document.getElementById('tab-radar');
  const banner = document.getElementById('pin-drop-banner');

  if (isPinDropMode) {
    // 1. Immediately switch to radar map tab so user actually sees the map
    if (typeof switchTab === 'function') {
      switchTab('tab-radar');
    }

    // 2. On mobile & desktop, expand map to 100% full screen and hide sidebar clutter
    if (radarPane) radarPane.classList.add('pin-drop-active');

    // 3. Show floating prompt banner over map
    if (banner) banner.style.display = 'flex';

    if (map) {
      map.getContainer().style.cursor = 'crosshair';
      setTimeout(() => map.invalidateSize(), 150);
    }
  } else {
    if (radarPane) radarPane.classList.remove('pin-drop-active');
    if (banner) banner.style.display = 'none';

    if (map) {
      map.getContainer().style.cursor = '';
      setTimeout(() => map.invalidateSize(), 150);
    }
  }

  // Update button texts
  const btns = document.querySelectorAll('.btn-pin-drop');
  btns.forEach(btn => {
    if (isPinDropMode) {
      btn.classList.add('btn-primary');
      btn.textContent = "Cancel Pin Drop";
    } else {
      btn.classList.remove('btn-primary');
      btn.textContent = "Drop Pin on Map";
    }
  });
}

function drawProximityRings(lat, lon) {
  proximityCircles.forEach(c => map.removeLayer(c));
  proximityCircles = [];

  const rings = [
    { radius: 0.5 * NM_TO_METERS, color: '#ef4444', label: '0.5 NM' },
    { radius: 1.0 * NM_TO_METERS, color: '#f59e0b', label: '1.0 NM' },
    { radius: 2.0 * NM_TO_METERS, color: '#3b82f6', label: '2.0 NM' },
    { radius: 3.5 * NM_TO_METERS, color: '#475569', label: '3.5 NM' }
  ];

  rings.forEach(r => {
    const c = L.circle([lat, lon], {
      radius: r.radius,
      color: r.color,
      weight: 1,
      dashArray: '4, 4',
      fill: false,
      opacity: 0.5
    }).addTo(map);
    proximityCircles.push(c);
  });
}

function drawAirportRunway(apt) {
  if (!apt || !apt.lat || !apt.lon || !map) return;

  if (runwayLine) map.removeLayer(runwayLine);
  if (extendedCenterline) map.removeLayer(extendedCenterline);
  runwayThresholdMarkers.forEach(m => map.removeLayer(m));
  runwayThresholdMarkers = [];

  const aptLat = apt.lat;
  const aptLon = apt.lon;
  const lengthMeters = (apt.runway_length_ft || 5000.0) * 0.3048;
  const hdg1 = apt.runway_heading_11 || 110.0;

  const halfLen = lengthMeters / 2.0;
  const rad = (hdg1 * Math.PI) / 180.0;
  const dLat = (halfLen * Math.cos(rad)) / 111139.0;
  const dLon = (halfLen * Math.sin(rad)) / (111139.0 * Math.cos((aptLat * Math.PI) / 180.0));

  const p1 = [aptLat - dLat, aptLon - dLon];
  const p2 = [aptLat + dLat, aptLon + dLon];

  runwayLine = L.polyline([p1, p2], {
    color: '#38bdf8',
    weight: 6,
    opacity: 0.85
  }).addTo(map);

  const marker = L.circleMarker([aptLat, aptLon], {
    radius: 6,
    color: '#38bdf8',
    fillColor: '#0284c7',
    fillOpacity: 1
  }).addTo(map).bindPopup(`
    <strong>${apt.id} - ${apt.name}</strong><br/>
    Runway Heading: ${hdg1}° / ${(hdg1 + 180) % 360}° (${apt.runway_length_ft || 5000} ft)<br/>
    Elevation: ${apt.elev_msl_ft} ft MSL
  `);
  runwayThresholdMarkers.push(marker);

  // Extended departure corridor
  const extLen = 4000.0;
  const extDLat = (extLen * Math.cos(rad)) / 111139.0;
  const extDLon = (extLen * Math.sin(rad)) / (111139.0 * Math.cos((aptLat * Math.PI) / 180.0));
  const extPoint = [p2[0] + extDLat, p2[1] + extDLon];

  extendedCenterline = L.polyline([p2, extPoint], {
    color: '#38bdf8',
    weight: 2,
    dashArray: '6, 6',
    opacity: 0.4
  }).addTo(map);
}

function updateAircraftMarkers(aircraftList, weather) {
  if (!map) return;

  const currentHexes = new Set();
  const effectiveWindDir = (weather && weather.effective_wind_dir_deg) ? weather.effective_wind_dir_deg : 110.0;

  aircraftList.forEach(ac => {
    const hex = ac.hex;
    currentHexes.add(hex);

    const lat = ac.lat;
    const lon = ac.lon;
    const track = ac.track || 0;
    const isLeaded = ac.aircraft_meta && ac.aircraft_meta.is_leaded;
    const isDownwind = ac.dispersion && ac.dispersion.is_downwind;
    const color = isLeaded ? '#ef4444' : '#3b82f6';

    const iconHtml = `
      <div class="aircraft-marker-icon" style="transform: rotate(${track}deg);">
        <svg width="28" height="28" viewBox="0 0 24 24" class="svg-plane">
          <path fill="${color}" stroke="#ffffff" stroke-width="1.2" d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
        </svg>
      </div>
    `;

    const customIcon = L.divIcon({
      className: 'custom-plane-icon',
      html: iconHtml,
      iconSize: [28, 28],
      iconAnchor: [14, 14]
    });

    const popupHtml = `
      <div style="font-family: sans-serif; min-width: 220px; font-size: 0.82rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #444; padding-bottom: 4px; margin-bottom: 6px;">
          <strong style="font-size: 1.05rem; color: ${color};">${ac.flight || ac.aircraft_meta.tail_number || hex}</strong>
          <span style="font-size: 0.72rem; background: ${isLeaded ? 'rgba(239,68,68,0.2)' : 'rgba(59,130,246,0.2)'}; color: ${color}; padding: 2px 6px; border-radius: 4px; font-weight: bold;">
            ${ac.aircraft_meta.fuel_type}
          </span>
        </div>
        <div><strong>Type:</strong> ${ac.aircraft_meta.icao_type} (${ac.aircraft_meta.model_name})</div>
        <div><strong>Engine:</strong> ${ac.aircraft_meta.engine_type}</div>
        <div><strong>Slant Range to House:</strong> ${ac.slant_range_ft ? Math.round(ac.slant_range_ft).toLocaleString() : '--'} ft (${ac.dist_nm} NM)</div>
        <div><strong>Altitude:</strong> ${ac.alt_msl_ft} ft MSL (${ac.alt_agl_ft} ft AGL)</div>
        <div><strong>Speed:</strong> ${ac.gs} kts | Track: ${ac.track}°</div>
        <hr style="border: 0; border-top: 1px solid #444; margin: 6px 0;"/>
        <div><strong>Lead Emission:</strong> ${ac.dispersion ? ac.dispersion.lead_emission_rate_mg_s : 0} mg/sec</div>
        <div><strong>Downwind:</strong> <span style="color: ${isDownwind ? '#f59e0b' : '#10b981'}; font-weight: bold;">${isDownwind ? 'YES (In Plume)' : 'NO'}</span></div>
        <div><strong>Exposure Score:</strong> <strong style="color: ${ac.dispersion && ac.dispersion.exposure_score > 40 ? '#ef4444' : '#f59e0b'};">${ac.dispersion ? ac.dispersion.exposure_score : 0} / 100</strong></div>
      </div>
    `;

    if (!aircraftMarkers[hex]) {
      aircraftMarkers[hex] = L.marker([lat, lon], { icon: customIcon }).addTo(map);
      aircraftTracks[hex] = L.polyline([[lat, lon]], {
        color: color,
        weight: 3,
        opacity: 0.6,
        dashArray: isLeaded ? null : '4, 4'
      }).addTo(map);
    } else {
      aircraftMarkers[hex].setLatLng([lat, lon]);
      aircraftMarkers[hex].setIcon(customIcon);
      aircraftTracks[hex].addLatLng([lat, lon]);
    }
    aircraftMarkers[hex].bindPopup(popupHtml);

    updatePlumeCone(hex, lat, lon, effectiveWindDir, isLeaded, isDownwind);
  });

  // Remove aircraft that left coverage
  Object.keys(aircraftMarkers).forEach(hex => {
    if (!currentHexes.has(hex)) {
      map.removeLayer(aircraftMarkers[hex]);
      delete aircraftMarkers[hex];

      if (aircraftTracks[hex]) {
        map.removeLayer(aircraftTracks[hex]);
        delete aircraftTracks[hex];
      }

      if (plumePolygons[hex]) {
        map.removeLayer(plumePolygons[hex]);
        delete plumePolygons[hex];
      }
    }
  });
}

function updatePlumeCone(hex, acLat, acLon, windDirDeg, isLeaded, isDownwind) {
  if (!isLeaded) {
    if (plumePolygons[hex]) {
      map.removeLayer(plumePolygons[hex]);
      delete plumePolygons[hex];
    }
    return;
  }

  const plumeHeading = (windDirDeg + 180.0) % 360.0;
  const coneLengthMeters = 2500.0;
  const halfAngle = 25.0;

  const leftAngle = (plumeHeading - halfAngle + 360.0) % 360.0;
  const rightAngle = (plumeHeading + halfAngle) % 360.0;

  function getOffsetPoint(lat, lon, distM, headingDeg) {
    const rad = (headingDeg * Math.PI) / 180.0;
    const dLat = (distM * Math.cos(rad)) / 111139.0;
    const dLon = (distM * Math.sin(rad)) / (111139.0 * Math.cos((lat * Math.PI) / 180.0));
    return [lat + dLat, lon + dLon];
  }

  const pLeft = getOffsetPoint(acLat, acLon, coneLengthMeters, leftAngle);
  const pCenter = getOffsetPoint(acLat, acLon, coneLengthMeters * 1.1, plumeHeading);
  const pRight = getOffsetPoint(acLat, acLon, coneLengthMeters, rightAngle);

  const polygonPoints = [[acLat, acLon], pLeft, pCenter, pRight];
  const plumeColor = isDownwind ? '#ef4444' : '#f59e0b';
  const fillOpacity = isDownwind ? 0.28 : 0.12;

  if (!plumePolygons[hex]) {
    plumePolygons[hex] = L.polygon(polygonPoints, {
      color: plumeColor,
      weight: 1,
      fillColor: plumeColor,
      fillOpacity: fillOpacity,
      dashArray: '3, 3'
    }).addTo(map);
  } else {
    plumePolygons[hex].setLatLngs(polygonPoints);
    plumePolygons[hex].setStyle({
      color: plumeColor,
      fillColor: plumeColor,
      fillOpacity: fillOpacity
    });
  }
}
