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
let aircraftVectors = {};
let plumePolygons = {};
let homeMarker = null;
let runwayLine = null;
let runwayThresholdMarkers = [];
let extendedCenterline = null;
let proximityCircles = [];
let isPinDropMode = false;

// 100LL Plume Cones state
let showPlumeCones = localStorage.getItem('alems_show_plumes') !== 'false'; // default true
let plumeConesGroup = L.layerGroup();

// 100LL Exposure Heatmap state
let exposureHeatmapLayer = null;
let heatmapBoundaryCircle = null;
let exposureHeatmapGroup = L.layerGroup();
let isHeatmapActive = false;
let currentHeatmapTimeframe = '24h';
let currentHeatmapCenterType = 'airport'; // 'airport' or 'property'
let cachedAirportConfig = null;
let cachedHomeConfig = null;

const NM_TO_METERS = 1852.0;

function initMap(homeConfig, airportConfig) {
  cachedHomeConfig = homeConfig;
  cachedAirportConfig = airportConfig;
  if (map) {
    recenterAndRedraw(homeConfig, airportConfig);
    return;
  }
  if (typeof L === 'undefined') {
    console.warn("Leaflet library is not yet loaded");
    return;
  }

  const homeLat = (homeConfig && homeConfig.lat) ? homeConfig.lat : 38.3000;
  const homeLon = (homeConfig && homeConfig.lon) ? homeConfig.lon : -76.6000;

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

  // Base Map Layer 4: Topographical Contours (100% Free Esri World Topo Map, zero API key)
  const topoLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19
  });

  // Default to Dark Radar layer
  darkLayer.addTo(map);

  baseLayers = {
    "Dark Radar": darkLayer,
    "Topographical (Contours)": topoLayer,
    "Street Map (OSM)": osmLayer,
    "Satellite Imagery": satLayerGroup
  };

  const overlayLayers = {
    "🔻 100LL Plume Cones": plumeConesGroup,
    "🔥 100LL Exposure Heatmap": exposureHeatmapGroup
  };

  layerControl = L.control.layers(baseLayers, overlayLayers, { position: 'topright' }).addTo(map);

  if (showPlumeCones) {
    plumeConesGroup.addTo(map);
  }
  updatePlumeToggleButton();

  map.on('overlayadd', (e) => {
    if (e.name && e.name.includes("Heatmap")) {
      toggleExposureHeatmap(true);
    } else if (e.name && e.name.includes("Plume")) {
      togglePlumeCones(true);
    }
  });
  map.on('overlayremove', (e) => {
    if (e.name && e.name.includes("Heatmap")) {
      toggleExposureHeatmap(false);
    } else if (e.name && e.name.includes("Plume")) {
      togglePlumeCones(false);
    }
  });

  // Dynamic zoom listener to maintain consistent physical ground footprint for heatmap
  map.on('zoomend', onMapZoomChange);

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
  cachedHomeConfig = homeConfig;
  cachedAirportConfig = airportConfig;

  const homeLat = (homeConfig && homeConfig.lat) ? homeConfig.lat : 38.3000;
  const homeLon = (homeConfig && homeConfig.lon) ? homeConfig.lon : -76.6000;

  drawHomeMarker(homeConfig);
  drawProximityRings(homeLat, homeLon);
  drawAirportRunway(airportConfig);
  if (isHeatmapActive) {
    fetchAndDrawExposureHeatmap();
  }
  map.setView([homeLat, homeLon], 13);
}

function drawHomeMarker(homeConfig) {
  if (!map) return;
  const homeLat = (homeConfig && homeConfig.lat) ? homeConfig.lat : 38.3000;
  const homeLon = (homeConfig && homeConfig.lon) ? homeConfig.lon : -76.6000;
  const addr = (homeConfig && homeConfig.address) ? homeConfig.address : "Monitored Property";
  const elev = (homeConfig && homeConfig.elev_msl_ft) ? homeConfig.elev_msl_ft : 100.0;

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

async function setHomeLocation(lat, lon, panMap = false, newAddress = null) {
  const roundedLat = parseFloat(lat.toFixed(6));
  const roundedLon = parseFloat(lon.toFixed(6));

  const latInput = document.getElementById('setting-home-lat');
  const lonInput = document.getElementById('setting-home-lon');
  const addrInput = document.getElementById('setting-home-address');
  const headerAddrEl = document.getElementById('header-address');

  if (latInput) latInput.value = roundedLat;
  if (lonInput) lonInput.value = roundedLon;

  // Immediately clear old address from header and input to prevent stale display
  if (newAddress) {
    if (addrInput) addrInput.value = newAddress;
    if (headerAddrEl) headerAddrEl.textContent = `📍 ${newAddress.split(',')[0]}`;
  } else {
    if (headerAddrEl) headerAddrEl.textContent = `📍 Resolving Address...`;
  }

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

  // Resolve address: use provided newAddress or reverse geocode coordinates
  let resolvedAddress = newAddress;
  if (!resolvedAddress) {
    try {
      const revRes = await fetch(`/api/geocode/reverse?lat=${roundedLat}&lon=${roundedLon}`);
      if (revRes.ok) {
        const revData = await revRes.json();
        if (revData && revData.address) {
          resolvedAddress = revData.address;
        }
      }
    } catch (e) {
      console.warn("Reverse geocoding failed:", e);
    }
  }

  if (!resolvedAddress) {
    resolvedAddress = `Lat ${roundedLat.toFixed(4)}, Lon ${roundedLon.toFixed(4)}`;
  }

  // Update input and header with resolved address
  if (addrInput) addrInput.value = resolvedAddress;
  if (headerAddrEl) {
    headerAddrEl.textContent = `📍 ${resolvedAddress.split(',')[0]}`;
    headerAddrEl.title = resolvedAddress;
  }

  // Auto-save both address and coordinates via API
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        home_address: resolvedAddress,
        home_lat: roundedLat,
        home_lon: roundedLon
      })
    });
    const data = await res.json();
    if (data.config && typeof applyConfigToUI === 'function') {
      applyConfigToUI(data.config);
    }
    if (typeof showToast === 'function') {
      showToast(`📍 Property location updated: ${resolvedAddress.split(',')[0]}`);
    }
  } catch (err) {
    console.error("Failed to auto-save location:", err);
  }
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
      <div class="aircraft-marker-icon" style="transform: rotate(${track}deg); transform-origin: 14px 14px; width: 28px; height: 28px;">
        <svg width="28" height="28" viewBox="0 0 24 24" class="svg-plane" style="transform-origin: 14px 14px;">
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
          <strong style="font-size: 1.05rem; color: ${color};">${ac.flight || (ac.aircraft_meta && ac.aircraft_meta.tail_number) || hex}</strong>
          <span style="font-size: 0.72rem; background: ${isLeaded ? 'rgba(239,68,68,0.2)' : 'rgba(59,130,246,0.2)'}; color: ${color}; padding: 2px 6px; border-radius: 4px; font-weight: bold;">
            ${(ac.aircraft_meta && ac.aircraft_meta.fuel_type) || 'AVGAS'}
          </span>
        </div>
        <div><strong>Type:</strong> ${(ac.aircraft_meta && ac.aircraft_meta.icao_type) || '--'} (${(ac.aircraft_meta && ac.aircraft_meta.model_name) || '--'})</div>
        <div><strong>Engine:</strong> ${(ac.aircraft_meta && ac.aircraft_meta.engine_type) || '--'}</div>
        <div><strong>Slant Range to House:</strong> ${ac.slant_range_ft ? Math.round(ac.slant_range_ft).toLocaleString() : '--'} ft (${ac.dist_nm || '--'} NM)</div>
        <div><strong>Altitude:</strong> ${ac.alt_msl_ft || ac.alt_baro || '--'} ft MSL (${ac.alt_agl_ft || '--'} ft AGL)</div>
        <div><strong>Speed:</strong> ${ac.gs || ac.speed || 0} kts | Track: ${ac.track || 0}°</div>
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

    // Forward Velocity Vector (Aviation Leader Line along ground track)
    const gs = Number(ac.gs || ac.speed || 0);
    if (gs > 15 && track !== undefined && track !== null) {
      const vectorDistM = Math.max(350, Math.min(2500, gs * 22.0));
      const trkRad = (track * Math.PI) / 180.0;
      const vDLat = (vectorDistM * Math.cos(trkRad)) / 111139.0;
      const vDLon = (vectorDistM * Math.sin(trkRad)) / (111139.0 * Math.cos((lat * Math.PI) / 180.0));
      const vectorEnd = [lat + vDLat, lon + vDLon];

      if (!aircraftVectors[hex]) {
        aircraftVectors[hex] = L.polyline([[lat, lon], vectorEnd], {
          color: color,
          weight: 2,
          opacity: 0.85,
          dashArray: '3, 4'
        }).addTo(map);
      } else {
        aircraftVectors[hex].setLatLngs([[lat, lon], vectorEnd]);
        aircraftVectors[hex].setStyle({ color: color });
      }
    } else if (aircraftVectors[hex]) {
      map.removeLayer(aircraftVectors[hex]);
      delete aircraftVectors[hex];
    }

    // Atmospheric dispersion plume cone
    updatePlumeCone(hex, lat, lon, effectiveWindDir, isLeaded, isDownwind, ac.in_geofence, ac.aircraft_meta, ac.flight);
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

      if (aircraftVectors[hex]) {
        map.removeLayer(aircraftVectors[hex]);
        delete aircraftVectors[hex];
      }

      if (plumePolygons[hex]) {
        map.removeLayer(plumePolygons[hex]);
        delete plumePolygons[hex];
      }
    }
  });
}

function updatePlumeCone(hex, acLat, acLon, windDirDeg, isLeaded, isDownwind, inGeofence, acMeta, flight) {
  // If user disabled cones or aircraft is not leaded, remove layer
  if (!showPlumeCones || !isLeaded) {
    if (plumePolygons[hex]) {
      map.removeLayer(plumePolygons[hex]);
      delete plumePolygons[hex];
    }
    return;
  }

  // Directional dissipation: plume drifts downwind (opposite of origin wind heading)
  const safeWindDir = (windDirDeg !== undefined && windDirDeg !== null && !isNaN(windDirDeg)) ? Number(windDirDeg) : 210.0;
  const plumeHeading = (safeWindDir + 180.0) % 360.0;
  const coneLengthMeters = 2400.0;
  const halfAngle = 24.0;

  const leftAngle = (plumeHeading - halfAngle + 360.0) % 360.0;
  const rightAngle = (plumeHeading + halfAngle) % 360.0;

  function getOffsetPoint(lat, lon, distM, headingDeg) {
    const rad = (headingDeg * Math.PI) / 180.0;
    const dLat = (distM * Math.cos(rad)) / 111139.0;
    const dLon = (distM * Math.sin(rad)) / (111139.0 * Math.cos((lat * Math.PI) / 180.0));
    return [lat + dLat, lon + dLon];
  }

  const pLeft = getOffsetPoint(acLat, acLon, coneLengthMeters, leftAngle);
  const pCenter = getOffsetPoint(acLat, acLon, coneLengthMeters * 1.12, plumeHeading);
  const pRight = getOffsetPoint(acLat, acLon, coneLengthMeters, rightAngle);

  const polygonPoints = [[acLat, acLon], pLeft, pCenter, pRight];
  const plumeColor = isDownwind ? '#ef4444' : '#f59e0b';
  const fillOpacity = isDownwind ? 0.28 : 0.16;

  const callsign = flight || (acMeta && acMeta.tail_number) || hex;
  const tooltipText = `<strong>${callsign}</strong> 100LL Exhaust Plume Drift<br/>Dissipation Heading: ${Math.round(plumeHeading)}°<br/>Winds from: ${Math.round(safeWindDir)}°`;

  if (!plumePolygons[hex]) {
    plumePolygons[hex] = L.polygon(polygonPoints, {
      color: plumeColor,
      weight: 1.5,
      fillColor: plumeColor,
      fillOpacity: fillOpacity,
      dashArray: '4, 4'
    }).bindTooltip(tooltipText, { sticky: true, direction: 'top' }).addTo(map);
  } else {
    plumePolygons[hex].setLatLngs(polygonPoints);
    plumePolygons[hex].setStyle({
      color: plumeColor,
      fillColor: plumeColor,
      fillOpacity: fillOpacity
    });
    plumePolygons[hex].setTooltipContent(tooltipText);
  }
}

/**
 * Toggle 100LL Exhaust Plume Cones
 * @param {boolean|undefined} forcedState
 */
function togglePlumeCones(forcedState) {
  if (forcedState !== undefined) {
    showPlumeCones = Boolean(forcedState);
  } else {
    showPlumeCones = !showPlumeCones;
  }
  localStorage.setItem('alems_show_plumes', showPlumeCones ? 'true' : 'false');
  updatePlumeToggleButton();

  if (!showPlumeCones) {
    Object.keys(plumePolygons).forEach(hex => {
      if (plumePolygons[hex] && map) {
        map.removeLayer(plumePolygons[hex]);
      }
      delete plumePolygons[hex];
    });
    if (typeof showToast === 'function') {
      showToast('100LL exhaust dissipation cones hidden');
    }
  } else {
    if (typeof renderFilteredAircraft === 'function') {
      renderFilteredAircraft();
    }
    if (typeof showToast === 'function') {
      showToast('100LL directional exhaust dissipation cones enabled');
    }
  }
}

function updatePlumeToggleButton() {
  const btn = document.getElementById('btn-toggle-plumes');
  if (btn) {
    if (showPlumeCones) {
      btn.classList.add('btn-plumes-active');
      btn.innerHTML = '🔻 Plumes (ON)';
      btn.title = 'Click to hide 100LL exhaust dissipation cones';
    } else {
      btn.classList.remove('btn-plumes-active');
      btn.innerHTML = '🔻 Plumes (OFF)';
      btn.title = 'Click to show 100LL exhaust dissipation cones';
    }
  }
}

/**
 * Dynamic zoom listener ensuring geographic consistency across all map range scales
 */
function onMapZoomChange() {
  if (exposureHeatmapLayer && map && isHeatmapActive) {
    const currentZoom = map.getZoom();
    const r = getHeatmapRadiusForZoom(currentZoom);
    const b = Math.round(r * 0.55);
    exposureHeatmapLayer.setOptions({
      radius: r,
      blur: b
    });
  }
}

function getHeatmapRadiusForZoom(zoom) {
  // Calibrated so physical ground footprint remains consistent as user zooms in/out
  const zoomRadii = {
    8: 8,
    9: 10,
    10: 14,
    11: 18,
    12: 24,
    13: 32,
    14: 46,
    15: 64,
    16: 88,
    17: 120,
    18: 160
  };
  return zoomRadii[zoom] || (zoom < 8 ? 6 : Math.round(24 * Math.pow(1.35, zoom - 12)));
}

/**
 * Switch Heatmap center location: Airfield vs Property
 * @param {string} centerType
 */
function setHeatmapCenter(centerType) {
  currentHeatmapCenterType = centerType;
  const sel = document.getElementById('heatmap-center-select');
  if (sel) sel.value = centerType;
  if (isHeatmapActive) {
    fetchAndDrawExposureHeatmap();
  }
}

/**
 * Toggle 100LL Lead Exposure Heatmap Layer
 * @param {boolean|undefined} forcedState
 */
function toggleExposureHeatmap(forcedState) {
  if (forcedState !== undefined) {
    isHeatmapActive = Boolean(forcedState);
  } else {
    isHeatmapActive = !isHeatmapActive;
  }

  const btn = document.getElementById('btn-toggle-heatmap');
  const timeframeControls = document.getElementById('heatmap-timeframe-controls');
  const legend = document.getElementById('heatmap-legend');

  if (isHeatmapActive) {
    if (btn) {
      btn.classList.add('btn-heatmap-active');
      btn.innerHTML = '🔥 100LL Heatmap (ON)';
    }
    if (timeframeControls) timeframeControls.style.display = 'flex';
    if (legend) legend.style.display = 'block';
    fetchAndDrawExposureHeatmap();
  } else {
    if (btn) {
      btn.classList.remove('btn-heatmap-active');
      btn.innerHTML = '🔥 100LL Heatmap';
    }
    if (timeframeControls) timeframeControls.style.display = 'none';
    if (legend) legend.style.display = 'none';
    if (exposureHeatmapLayer && map) {
      map.removeLayer(exposureHeatmapLayer);
      exposureHeatmapLayer = null;
    }
    if (heatmapBoundaryCircle && map) {
      map.removeLayer(heatmapBoundaryCircle);
      heatmapBoundaryCircle = null;
    }
  }
}

/**
 * Switch Heatmap aggregation timeframe (24h, 7d, 30d, all)
 * @param {string} tf
 */
function setHeatmapTimeframe(tf) {
  currentHeatmapTimeframe = tf;
  document.querySelectorAll('#heatmap-timeframe-controls .timeframe-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.timeframe === tf);
  });
  fetchAndDrawExposureHeatmap();
}

/**
 * Fetch and render 100LL cumulative exposure points onto Leaflet map
 */
async function fetchAndDrawExposureHeatmap() {
  if (!map || !isHeatmapActive) return;

  const radiusNm = (window.appConfig && window.appConfig.thresholds && window.appConfig.thresholds.heatmap_radius_nm) || 10.0;
  const propLat = (cachedHomeConfig && cachedHomeConfig.lat) || (window.appConfig && window.appConfig.property && window.appConfig.property.lat) || 38.30000;
  const propLon = (cachedHomeConfig && cachedHomeConfig.lon) || (window.appConfig && window.appConfig.property && window.appConfig.property.lon) || -76.60000;
  const aptLat = (cachedAirportConfig && cachedAirportConfig.lat) || (window.appConfig && window.appConfig.airport && window.appConfig.airport.lat) || 38.315355;
  const aptLon = (cachedAirportConfig && cachedAirportConfig.lon) || (window.appConfig && window.appConfig.airport && window.appConfig.airport.lon) || -76.550116;

  let centerLat, centerLon, centerLabel;
  if (currentHeatmapCenterType === 'property') {
    centerLat = propLat;
    centerLon = propLon;
    centerLabel = 'Property Pinpoint';
  } else {
    centerLat = aptLat;
    centerLon = aptLon;
    centerLabel = (cachedAirportConfig && cachedAirportConfig.id) ? `${cachedAirportConfig.id} Airfield` : 'Airfield (2W6)';
  }

  try {
    const res = await fetch(`/api/exposure/heatmap?time_range=${currentHeatmapTimeframe}&radius_nm=${radiusNm}&center_type=${currentHeatmapCenterType}&center_lat=${centerLat}&center_lon=${centerLon}`);
    if (!res.ok) throw new Error("Failed to fetch exposure heatmap points");
    const data = await res.json();

    const actualRadiusNm = data.radius_nm || radiusNm;
    const radiusMeters = actualRadiusNm * NM_TO_METERS;

    // 1. Draw or update radial boundary circle around selected center
    if (heatmapBoundaryCircle && map) {
      map.removeLayer(heatmapBoundaryCircle);
    }
    heatmapBoundaryCircle = L.circle([centerLat, centerLon], {
      radius: radiusMeters,
      color: '#f97316',
      weight: 1.5,
      dashArray: '6, 6',
      fillColor: '#f97316',
      fillOpacity: 0.04,
      interactive: true
    }).bindTooltip(`${actualRadiusNm} NM Radial Exposure Range around ${centerLabel}`, {
      permanent: false,
      direction: 'top'
    });

    if (isHeatmapActive && map) {
      heatmapBoundaryCircle.addTo(map);
    }

    // Update legend radius text
    const legendRad = document.getElementById('heatmap-legend-radius');
    if (legendRad) {
      legendRad.textContent = `(${actualRadiusNm} NM · ${centerLabel})`;
    }

    // 2. Remove existing heatmap layer
    if (exposureHeatmapLayer && map) {
      map.removeLayer(exposureHeatmapLayer);
      exposureHeatmapLayer = null;
    }

    const points = data.points || [];
    if (points.length > 0 && typeof L.heatLayer === 'function') {
      const currentZoom = map.getZoom();
      const initRadius = getHeatmapRadiusForZoom(currentZoom);
      const initBlur = Math.round(initRadius * 0.55);

      // Yellow -> Orange -> Red spectrum for cumulative lead exposure
      // maxZoom: 1 disables artificial 1/2^(maxZoom-zoom) attenuation so colors stay stable across all range scales!
      exposureHeatmapLayer = L.heatLayer(points, {
        radius: initRadius,
        blur: initBlur,
        maxZoom: 1,
        max: 1.0,
        minOpacity: 0.20,
        gradient: {
          0.18: '#fde047',   // Pale Yellow
          0.40: '#facc15',   // Vibrant Yellow
          0.62: '#f97316',   // Vivid Orange
          0.82: '#ef4444',   // Bright Red
          1.0:  '#991b1b'    // Deep Crimson / Severe
        }
      });

      if (isHeatmapActive && map) {
        exposureHeatmapLayer.addTo(map);
      }
    } else if (points.length === 0) {
      if (typeof showToast === 'function') {
        showToast(`No 100LL flyover points within ${actualRadiusNm} NM in the selected ${currentHeatmapTimeframe} timeframe.`);
      }
    }
  } catch (err) {
    console.error("Error drawing 100LL heatmap:", err);
  }
}

window.togglePlumeCones = togglePlumeCones;
window.setHeatmapCenter = setHeatmapCenter;

