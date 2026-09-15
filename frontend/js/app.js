/**
 * Main application client for ALEMS.
 * Manages WebSocket connection, tab switching, real-time UI updates, and API calls.
 */

let appConfig = null;
let ws = null;
let reconnectTimer = null;
let currentAircraftList = [];
let allEventsList = [];

// Safe Tab Switching function (available globally)
function switchTab(tabId) {
  const targetPane = document.getElementById(tabId);
  if (!targetPane) return;

  // 1. Update button states
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    const isTarget = btn.getAttribute('data-tab') === tabId;
    btn.classList.toggle('active', isTarget);
  });

  // 2. Update pane states
  const tabPanes = document.querySelectorAll('.tab-pane');
  tabPanes.forEach(pane => {
    const isTarget = pane.id === tabId;
    pane.classList.toggle('active', isTarget);
  });

  // 3. Tab-specific hooks
  if (tabId === 'tab-radar') {
    if (typeof map !== 'undefined' && map) {
      setTimeout(() => {
        map.invalidateSize();
      }, 100);
      setTimeout(() => {
        map.invalidateSize();
      }, 300);
    }
  } else if (tabId === 'tab-analytics') {
    if (typeof initCharts === 'function') {
      try {
        initCharts();
      } catch (err) {
        console.warn("Analytics charts init:", err);
      }
    }
  } else if (tabId === 'tab-logs') {
    refreshEvents();
  }
}

function setupTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const target = btn.getAttribute('data-tab');
      switchTab(target);
    });
  });
}

// Window resize listener to keep map sized properly on mobile orientation changes
window.addEventListener('resize', () => {
  if (typeof map !== 'undefined' && map) {
    map.invalidateSize();
  }
});

document.addEventListener('DOMContentLoaded', async () => {
  setupTabs();
  await loadConfigAndInit();
  connectWebSocket();
  setupSettingsHandlers();
});

async function loadConfigAndInit() {
  try {
    const resp = await fetch('/api/config');
    appConfig = await resp.json();

    // Set UI badges & inputs
    applyConfigToUI(appConfig);

    // Initialize Map safely
    if (typeof initMap === 'function') {
      try {
        initMap(appConfig.home, appConfig.airport);
      } catch (mapErr) {
        console.error("Failed to initialize map:", mapErr);
      }
    }

    // Load initial events and stats
    await refreshEvents();
    await refreshStats();
  } catch (e) {
    console.error("Failed to load initial config:", e);
  }
}

function applyConfigToUI(cfg) {
  if (!cfg) return;

  const addrEl = document.getElementById('header-address');
  if (addrEl && cfg.home) {
    const label = cfg.home.address ? cfg.home.address.split(',')[0] : `${cfg.home.lat?.toFixed(4)}, ${cfg.home.lon?.toFixed(4)}`;
    addrEl.textContent = `📍 ${label}`;
  }

  const airportEl = document.getElementById('header-airport');
  if (airportEl && cfg.airport) {
    airportEl.textContent = `✈️ ${cfg.airport.id || 'Airfield'} (Rwy ${cfg.airport.runway_heading_11 || '?'}/${cfg.airport.runway_heading_29 || '?'})`;
  }

  const homeAddrInput = document.getElementById('setting-home-address');
  if (homeAddrInput && cfg.home) homeAddrInput.value = cfg.home.address || '';

  const homeLatInput = document.getElementById('setting-home-lat');
  if (homeLatInput && cfg.home) homeLatInput.value = cfg.home.lat || '';

  const homeLonInput = document.getElementById('setting-home-lon');
  if (homeLonInput && cfg.home) homeLonInput.value = cfg.home.lon || '';

  const homeElevInput = document.getElementById('setting-home-elev');
  if (homeElevInput && cfg.home) homeElevInput.value = cfg.home.elev_msl_ft || '';

  const aptIdInput = document.getElementById('setting-airport-id');
  if (aptIdInput && cfg.airport) aptIdInput.value = cfg.airport.id || '';

  const aptNameInput = document.getElementById('setting-airport-name');
  if (aptNameInput && cfg.airport) aptNameInput.value = cfg.airport.name || '';

  const aptLatInput = document.getElementById('setting-airport-lat');
  if (aptLatInput && cfg.airport) aptLatInput.value = cfg.airport.lat || '';

  const aptLonInput = document.getElementById('setting-airport-lon');
  if (aptLonInput && cfg.airport) aptLonInput.value = cfg.airport.lon || '';

  const aptElevInput = document.getElementById('setting-airport-elev');
  if (aptElevInput && cfg.airport) aptElevInput.value = cfg.airport.elev_msl_ft || '';

  const rwy1Input = document.getElementById('setting-runway-hdg1');
  if (rwy1Input && cfg.airport) rwy1Input.value = cfg.airport.runway_heading_11 || '';

  const rwy2Input = document.getElementById('setting-runway-hdg2');
  if (rwy2Input && cfg.airport) rwy2Input.value = cfg.airport.runway_heading_29 || '';

  const simToggle = document.getElementById('setting-sim-toggle');
  if (simToggle) simToggle.checked = cfg.simulation_mode || false;

  const readsbInput = document.getElementById('setting-readsb-url');
  if (readsbInput && cfg.endpoints) readsbInput.value = cfg.endpoints.readsb_url || '';

  const hassInput = document.getElementById('setting-hass-url');
  if (hassInput && cfg.endpoints) hassInput.value = cfg.endpoints.hass_url || '';
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("[*] WebSocket connected to ALEMS daemon");
    const statusDot = document.getElementById('ws-status-dot');
    const statusText = document.getElementById('ws-status-text');
    if (statusDot) statusDot.style.backgroundColor = '#10b981';
    if (statusText) statusText.textContent = 'ONLINE';
    if (reconnectTimer) clearInterval(reconnectTimer);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'INITIAL_STATE' || data.type === 'SNAPSHOT') {
        handleSnapshot(data);
      } else if (data.type === 'NEW_EVENT') {
        handleNewEvent(data.event);
      } else if (data.type === 'CONFIG_UPDATED') {
        appConfig = data.config;
        applyConfigToUI(appConfig);
        if (typeof recenterAndRedraw === 'function') {
          recenterAndRedraw(appConfig.home, appConfig.airport);
        }
      }
    } catch (e) {
      console.error("Error processing WS message:", e);
    }
  };

  ws.onclose = () => {
    const statusDot = document.getElementById('ws-status-dot');
    const statusText = document.getElementById('ws-status-text');
    if (statusDot) statusDot.style.backgroundColor = '#ef4444';
    if (statusText) statusText.textContent = 'RECONNECTING';

    if (!reconnectTimer) {
      reconnectTimer = setInterval(() => {
        connectWebSocket();
      }, 3000);
    }
  };
}

function handleSnapshot(data) {
  currentAircraftList = data.aircraft || [];
  const weather = data.weather || {};

  // 1. Update Map Markers & Plume Cones
  if (typeof updateAircraftMarkers === 'function') {
    updateAircraftMarkers(currentAircraftList, weather);
  }

  // 2. Update Sidebar Active Aircraft Cards
  updateAircraftSidebar(currentAircraftList);

  // 3. Update Weather Cards
  updateWeatherUI(weather);
}

function handleNewEvent(eventRecord) {
  allEventsList.unshift(eventRecord);
  renderEventsTable(allEventsList);
  refreshStats();

  // Notification badge update
  const badge = document.getElementById('nav-logs-badge');
  if (badge) {
    badge.textContent = `${parseInt(badge.textContent || 0) + 1}`;
    badge.style.display = 'inline-block';
  }
}

function updateWeatherUI(weather) {
  const ecowitt = weather.ecowitt || {};
  const aerodrome = weather.aerodrome || {};

  // Ground station (Ecowitt)
  const elEcoSpd = document.getElementById('weather-ecowitt-speed');
  const elEcoDir = document.getElementById('weather-ecowitt-dir');
  const elEcoGust = document.getElementById('weather-ecowitt-gust');
  const elEcoTemp = document.getElementById('weather-ecowitt-temp');

  if (elEcoSpd) elEcoSpd.textContent = `${ecowitt.wind_speed_mph || 0} mph`;
  if (elEcoDir) elEcoDir.textContent = `${ecowitt.wind_dir_deg || 0}°`;
  if (elEcoGust) elEcoGust.textContent = `Gust: ${ecowitt.wind_gust_mph || 0} mph`;
  if (elEcoTemp) elEcoTemp.textContent = `${ecowitt.temp_f || 0}°F`;

  // Aerodrome (2W6 / KNHK)
  const elAeroStation = document.getElementById('weather-aero-station');
  const elAeroSpd = document.getElementById('weather-aero-speed');
  const elAeroDir = document.getElementById('weather-aero-dir');

  if (elAeroStation) elAeroStation.textContent = `${aerodrome.station || 'KNHK'} (Above Trees)`;
  if (elAeroSpd) elAeroSpd.textContent = `${aerodrome.wind_speed_kts || 0} kts (${aerodrome.wind_speed_mph || 0} mph)`;
  if (elAeroDir) elAeroDir.textContent = `${aerodrome.wind_dir_deg || 0}°`;

  // Effective Plume Drift Vector
  const elPlumeDir = document.getElementById('weather-plume-dir');
  if (elPlumeDir) {
    const plumeHdg = ((weather.effective_wind_dir_deg || 110.0) + 180.0) % 360.0;
    elPlumeDir.textContent = `${Math.round(plumeHdg)}° (Plume Drift)`;
  }
}

function updateAircraftSidebar(list) {
  const container = document.getElementById('sidebar-aircraft-list');
  const countBadge = document.getElementById('sidebar-aircraft-count');
  if (!container) return;

  if (countBadge) countBadge.textContent = list.length;

  if (list.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; color: #64748b; padding: 2rem 1rem; font-size: 0.85rem;">
        No aircraft currently within geofence (3.5 NM).
      </div>
    `;
    return;
  }

  container.innerHTML = list.map(ac => {
    const meta = ac.aircraft_meta || {};
    const disp = ac.dispersion || {};
    const isLeaded = meta.is_leaded;
    const isDownwind = disp.is_downwind;

    return `
      <div class="aircraft-item ${isLeaded ? 'leaded' : 'turbine'}">
        <div class="ac-top-row">
          <span class="ac-callsign">${ac.flight || meta.tail_number || ac.hex}</span>
          <span class="ac-type-badge ${isLeaded ? 'type-100ll' : 'type-jeta'}">
            ${meta.fuel_type} (${meta.icao_type})
          </span>
        </div>
        <div style="font-size: 0.72rem; color: #cbd5e1; margin-bottom: 0.35rem;">
          ${meta.model_name}
        </div>
        <div class="ac-metrics">
          <div>
            <div style="font-size: 0.65rem; color: #64748b;">SLANT DIST</div>
            <div class="ac-metric-val">${ac.slant_range_ft ? ac.slant_range_ft.toLocaleString() : '--'} ft</div>
          </div>
          <div>
            <div style="font-size: 0.65rem; color: #64748b;">ALT AGL</div>
            <div class="ac-metric-val">${ac.alt_agl_ft} ft</div>
          </div>
          <div>
            <div style="font-size: 0.65rem; color: #64748b;">SPEED</div>
            <div class="ac-metric-val">${ac.gs} kts</div>
          </div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.4rem;">
          <span class="downwind-pill ${isDownwind ? 'warning' : 'safe'}">
            ${isDownwind ? '⚠ DOWNWIND PLUME' : '✓ CROSS/UPWIND'}
          </span>
          <span style="font-size: 0.72rem; font-weight: bold; color: ${disp.exposure_score > 40 ? '#ef4444' : '#f59e0b'};">
            Risk: ${disp.exposure_score || 0}/100
          </span>
        </div>
      </div>
    `;
  }).join('');
}

async function refreshEvents() {
  try {
    const leadedOnly = document.getElementById('filter-leaded-only')?.checked || false;
    const resp = await fetch(`/api/events?limit=100&leaded_only=${leadedOnly}`);
    const data = await resp.json();
    allEventsList = data.events || [];
    renderEventsTable(allEventsList);
  } catch (e) {
    console.error("Failed to fetch events:", e);
  }
}

function renderEventsTable(events) {
  const tbody = document.getElementById('events-table-body');
  if (!tbody) return;

  if (events.length === 0) {
    tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: #64748b; padding: 2rem;">No flyovers logged yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = events.map(ev => {
    const isLeaded = ev.is_leaded === 1;
    const isDownwind = ev.is_downwind === 1;

    let scoreColor = '#6ee7b7';
    if (ev.max_exposure_score >= 70) scoreColor = '#ef4444';
    else if (ev.max_exposure_score >= 40) scoreColor = '#f59e0b';
    else if (ev.max_exposure_score >= 15) scoreColor = '#38bdf8';

    return `
      <tr>
        <td><strong>${ev.cpa_time_local || ev.cpa_time_utc}</strong></td>
        <td>
          <strong style="color: ${isLeaded ? '#fca5a5' : '#93c5fd'};">${ev.tail_number || ev.icao_hex}</strong><br/>
          <span style="font-size: 0.7rem; color: #64748b;">${ev.icao_hex}</span>
        </td>
        <td>
          ${ev.aircraft_type}<br/>
          <span style="font-size: 0.7rem; color: #94a3b8;">${ev.model_name}</span>
        </td>
        <td>
          <span class="ac-type-badge ${isLeaded ? 'type-100ll' : 'type-jeta'}">
            ${ev.fuel_type} (${ev.engine_type})
          </span>
        </td>
        <td><strong>${ev.min_slant_range_ft ? ev.min_slant_range_ft.toLocaleString() : '--'} ft</strong></td>
        <td>${ev.cpa_alt_agl_ft} ft</td>
        <td>${ev.cpa_ground_speed_kts} kts</td>
        <td>${ev.ecowitt_wind_speed_mph} mph @ ${ev.ecowitt_wind_dir_deg}°</td>
        <td>
          <span class="downwind-pill ${isDownwind ? 'warning' : 'safe'}">
            ${isDownwind ? 'YES' : 'NO'}
          </span>
        </td>
        <td>
          <strong style="color: ${scoreColor}; font-size: 0.95rem;">${ev.max_exposure_score}</strong>
          <span style="font-size: 0.7rem; color: #94a3b8;">(${ev.exposure_level})</span>
        </td>
        <td>
          <div style="display: flex; gap: 0.35rem;">
            <button class="btn btn-secondary" style="padding: 0.2rem 0.45rem; font-size: 0.72rem;" onclick="downloadEventTrajectoryCsv('${ev.event_id}')">
              CSV
            </button>
            <button class="btn btn-secondary" style="padding: 0.2rem 0.45rem; font-size: 0.72rem;" title="Copy SHA-256 Corroboration Hash" onclick="copyCorroborationHash('${ev.corroboration_hash}')">
              #Hash
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function refreshStats() {
  try {
    const resp = await fetch('/api/statistics');
    const stats = await resp.json();
    if (typeof updateAnalyticsUI === 'function') {
      updateAnalyticsUI(stats);
    }
  } catch (e) {
    console.error("Failed to fetch statistics:", e);
  }
}

function setupSettingsHandlers() {
  // 1. Simulation Toggle
  const simToggle = document.getElementById('setting-sim-toggle');
  if (simToggle) {
    simToggle.addEventListener('change', async (e) => {
      const active = e.target.checked;
      await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ simulation_mode: active })
      });
      console.log(`Simulation mode set to: ${active}`);
    });
  }

  // 2. Geocode Address Button
  const geocodeBtn = document.getElementById('geocode-addr-btn');
  if (geocodeBtn) {
    geocodeBtn.addEventListener('click', async () => {
      const addr = document.getElementById('setting-home-address').value.trim();
      if (!addr) {
        alert("Please enter a street address to search.");
        return;
      }
      geocodeBtn.disabled = true;
      geocodeBtn.textContent = "Geocoding...";
      try {
        const resp = await fetch(`/api/geocode?query=${encodeURIComponent(addr)}`);
        if (resp.ok) {
          const data = await resp.json();
          document.getElementById('setting-home-lat').value = data.lat;
          document.getElementById('setting-home-lon').value = data.lon;
          if (data.address) {
            document.getElementById('setting-home-address').value = data.address;
          }
          if (typeof setHomeLocation === 'function') {
            setHomeLocation(data.lat, data.lon);
          }
          alert(`Address found!\nLat: ${data.lat}, Lon: ${data.lon}`);
        } else {
          alert(`Could not geocode address: "${addr}". Please check the spelling or enter coordinates directly.`);
        }
      } catch (err) {
        alert(`Geocoding request failed: ${err.message}`);
      } finally {
        geocodeBtn.disabled = false;
        geocodeBtn.textContent = "Find & Geocode";
      }
    });
  }

  // 3. Airport Lookup Button
  const airportBtn = document.getElementById('lookup-airport-btn');
  if (airportBtn) {
    airportBtn.addEventListener('click', async () => {
      const code = document.getElementById('setting-airport-id').value.trim();
      if (!code) {
        alert("Please enter an airport code (e.g. 2W6, KRHV, KSMO, KGAI).");
        return;
      }
      airportBtn.disabled = true;
      airportBtn.textContent = "Looking up...";
      try {
        const resp = await fetch(`/api/airport/lookup?code=${encodeURIComponent(code)}`);
        if (resp.ok) {
          const apt = await resp.json();
          document.getElementById('setting-airport-name').value = apt.name || '';
          document.getElementById('setting-airport-lat').value = apt.lat || '';
          document.getElementById('setting-airport-lon').value = apt.lon || '';
          document.getElementById('setting-airport-elev').value = apt.elev_msl_ft || '';
          document.getElementById('setting-runway-hdg1').value = apt.runway_heading_1 || '';
          document.getElementById('setting-runway-hdg2').value = apt.runway_heading_2 || '';
          if (typeof drawAirportRunway === 'function') {
            drawAirportRunway({
              id: apt.id,
              name: apt.name,
              lat: apt.lat,
              lon: apt.lon,
              elev_msl_ft: apt.elev_msl_ft,
              runway_heading_11: apt.runway_heading_1,
              runway_heading_29: apt.runway_heading_2,
              runway_length_ft: apt.runway_length_ft
            });
          }
          alert(`Airport loaded: ${apt.name} (${apt.id})\nRunway: ${apt.runway_heading_1}° / ${apt.runway_heading_2}°`);
        } else {
          alert(`Airport code "${code}" not found. You can enter the coordinates and runway headings manually below.`);
        }
      } catch (err) {
        alert(`Airport lookup failed: ${err.message}`);
      } finally {
        airportBtn.disabled = false;
        airportBtn.textContent = "Lookup Airport";
      }
    });
  }

  // 4. Save & Apply Configuration Button
  const saveBtn = document.getElementById('save-settings-btn');
  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const payload = {
        home_address: document.getElementById('setting-home-address')?.value.trim() || undefined,
        home_lat: parseFloat(document.getElementById('setting-home-lat')?.value) || undefined,
        home_lon: parseFloat(document.getElementById('setting-home-lon')?.value) || undefined,
        home_elev_ft: parseFloat(document.getElementById('setting-home-elev')?.value) || undefined,
        airport_id: document.getElementById('setting-airport-id')?.value.trim() || undefined,
        airport_name: document.getElementById('setting-airport-name')?.value.trim() || undefined,
        airport_lat: parseFloat(document.getElementById('setting-airport-lat')?.value) || undefined,
        airport_lon: parseFloat(document.getElementById('setting-airport-lon')?.value) || undefined,
        airport_elev_ft: parseFloat(document.getElementById('setting-airport-elev')?.value) || undefined,
        runway_heading_1: parseFloat(document.getElementById('setting-runway-hdg1')?.value) || undefined,
        runway_heading_2: parseFloat(document.getElementById('setting-runway-hdg2')?.value) || undefined,
        readsb_url: document.getElementById('setting-readsb-url')?.value.trim() || undefined,
        hass_url: document.getElementById('setting-hass-url')?.value.trim() || undefined,
        hass_token: document.getElementById('setting-hass-token')?.value.trim() || undefined
      };

      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";

      try {
        const resp = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (resp.ok) {
          const result = await resp.json();
          appConfig = result.config;
          applyConfigToUI(appConfig);
          if (typeof recenterAndRedraw === 'function') {
            recenterAndRedraw(appConfig.home, appConfig.airport);
          }
          alert("Configuration saved & applied successfully!\nRadar map and monitoring geofence have been updated.");
        } else {
          alert("Error saving configuration. Please check the values entered.");
        }
      } catch (err) {
        alert(`Failed to save configuration: ${err.message}`);
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save & Apply Configuration";
      }
    });
  }

  // 5. Filter checkbox on logs table
  const filterCheckbox = document.getElementById('filter-leaded-only');
  if (filterCheckbox) {
    filterCheckbox.addEventListener('change', () => refreshEvents());
  }
}
