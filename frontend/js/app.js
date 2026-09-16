/**
 * Main application client for ALEMS.
 * Manages WebSocket connection, tab switching, real-time UI updates, and API calls.
 */

let appConfig = null;
let ws = null;
let reconnectTimer = null;
let httpPollTimer = null;
let currentAircraftList = [];
let allEventsList = [];
let latestWeather = {};

// Lightweight, non-blocking toast notification helper
function showToast(message, isError = false) {
  let toast = document.getElementById('toast-notification');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast-notification';
    toast.className = 'toast-notification';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.style.borderColor = isError ? '#ef4444' : '#10b981';
  toast.style.color = isError ? '#fca5a5' : '#6ee7b7';
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
  }, 4000);
}

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
        if (typeof fetchAndRenderAnalytics === 'function') {
          fetchAndRenderAnalytics();
        }
        setTimeout(() => {
          if (typeof resizeCharts === 'function') resizeCharts();
        }, 150);
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
  if (typeof setupMigrationUI === 'function') {
    setupMigrationUI();
  }
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
    await fetchLiveAircraftHttp();
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

  window.appConfig = cfg;

  // Geofence & Heatmap Radius Inputs
  const heatmapRadiusInput = document.getElementById('setting-heatmap-radius');
  if (heatmapRadiusInput && cfg.thresholds) heatmapRadiusInput.value = cfg.thresholds.heatmap_radius_nm || 10.0;

  const activeRadiusInput = document.getElementById('setting-active-radius');
  if (activeRadiusInput && cfg.thresholds) activeRadiusInput.value = cfg.thresholds.active_radius_nm || 3.5;

  const flyoverRadiusInput = document.getElementById('setting-flyover-radius');
  if (flyoverRadiusInput && cfg.thresholds) flyoverRadiusInput.value = cfg.thresholds.flyover_radius_nm || 1.5;

  // ADS-B Hardware / Source Inputs
  const adsbProvider = document.getElementById('setting-adsb-provider');
  if (adsbProvider && cfg.endpoints) {
    adsbProvider.value = cfg.endpoints.adsb_provider || 'readsb_local';
    updateAdsbPanels(adsbProvider.value);
  }

  const adsbCustomUrl = document.getElementById('setting-adsb-custom-url');
  if (adsbCustomUrl && cfg.endpoints) adsbCustomUrl.value = cfg.endpoints.adsb_custom_url || '';

  const adsbLolCoords = document.getElementById('adsb-lol-coords');
  if (adsbLolCoords && cfg.home) {
    adsbLolCoords.textContent = `${cfg.home.lat}, ${cfg.home.lon}`;
  }

  const readsbUrl = document.getElementById('setting-readsb-url');
  if (readsbUrl && cfg.endpoints) readsbUrl.value = cfg.endpoints.readsb_url || '';

  const readsbHost = document.getElementById('setting-readsb-host');
  if (readsbHost && cfg.endpoints) readsbHost.value = cfg.endpoints.readsb_host || '';

  const readsbPort = document.getElementById('setting-readsb-port');
  if (readsbPort && cfg.endpoints) readsbPort.value = cfg.endpoints.readsb_port || 80;

  const readsbPath = document.getElementById('setting-readsb-path');
  if (readsbPath && cfg.endpoints) readsbPath.value = cfg.endpoints.readsb_path || '/tar1090/data/aircraft.json';

  // Weather Hardware Inputs
  const weatherProvider = document.getElementById('setting-weather-provider');
  if (weatherProvider && cfg.endpoints) {
    weatherProvider.value = cfg.endpoints.weather_provider || 'ecowitt_local';
    updateWeatherPanels(weatherProvider.value);
  }

  const ecowittIp = document.getElementById('setting-ecowitt-ip');
  if (ecowittIp && cfg.endpoints) ecowittIp.value = cfg.endpoints.ecowitt_ip || '';

  const ecowittPort = document.getElementById('setting-ecowitt-port');
  if (ecowittPort && cfg.endpoints) ecowittPort.value = cfg.endpoints.ecowitt_port || 80;

  const hassInput = document.getElementById('setting-hass-url');
  if (hassInput && cfg.endpoints) hassInput.value = cfg.endpoints.hass_url || '';

  const pushIpEl = document.getElementById('push-server-ip');
  if (pushIpEl) {
    pushIpEl.textContent = window.location.hostname;
  }
}

function updateAdsbPanels(selectedProvider) {
  const pReadsb = document.getElementById('panel-adsb-readsb-local');
  const pAdsbLol = document.getElementById('panel-adsb-adsb-lol');
  const pOpenSky = document.getElementById('panel-adsb-opensky');
  const pCustom = document.getElementById('panel-adsb-custom-url');

  if (pReadsb) pReadsb.style.display = (selectedProvider === 'readsb_local') ? 'block' : 'none';
  if (pAdsbLol) pAdsbLol.style.display = (selectedProvider === 'adsb_lol') ? 'block' : 'none';
  if (pOpenSky) pOpenSky.style.display = (selectedProvider === 'opensky') ? 'block' : 'none';
  if (pCustom) pCustom.style.display = (selectedProvider === 'custom_url') ? 'block' : 'none';
}

function updateWeatherPanels(selectedProvider) {
  const pEcowittLocal = document.getElementById('panel-weather-ecowitt-local');
  const pEcowittPush = document.getElementById('panel-weather-ecowitt-push');
  const pHass = document.getElementById('panel-weather-homeassistant');

  if (pEcowittLocal) pEcowittLocal.style.display = (selectedProvider === 'ecowitt_local') ? 'block' : 'none';
  if (pEcowittPush) pEcowittPush.style.display = (selectedProvider === 'ecowitt_push') ? 'block' : 'none';
  if (pHass) pHass.style.display = (selectedProvider === 'homeassistant') ? 'block' : 'none';
}

function startHttpPolling() {
  if (httpPollTimer) return;
  fetchLiveAircraftHttp();
  httpPollTimer = setInterval(fetchLiveAircraftHttp, 2500);
}

function stopHttpPolling() {
  if (httpPollTimer) {
    clearInterval(httpPollTimer);
    httpPollTimer = null;
  }
}

async function fetchLiveAircraftHttp() {
  try {
    const resp = await fetch('/api/aircraft');
    if (resp.ok) {
      const data = await resp.json();
      const statusDot = document.getElementById('ws-status-dot');
      const statusText = document.getElementById('ws-status-text');
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        if (statusDot) statusDot.style.backgroundColor = '#10b981';
        if (statusText) statusText.textContent = 'ONLINE';
      }
      handleSnapshot(data);
    }
  } catch (e) {
    console.warn("HTTP polling error:", e);
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  try {
    ws = new WebSocket(wsUrl);
  } catch (err) {
    console.warn("WebSocket init error, falling back to HTTP sync:", err);
    startHttpPolling();
    return;
  }

  ws.onopen = () => {
    console.log("[*] WebSocket connected to ALEMS daemon");
    const statusDot = document.getElementById('ws-status-dot');
    const statusText = document.getElementById('ws-status-text');
    if (statusDot) statusDot.style.backgroundColor = '#10b981';
    if (statusText) statusText.textContent = 'ONLINE';
    if (reconnectTimer) {
      clearInterval(reconnectTimer);
      reconnectTimer = null;
    }
    stopHttpPolling();
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
      } else if (data.type === 'RESTORE_COMPLETED') {
        if (data.config) {
          appConfig = data.config;
          applyConfigToUI(appConfig);
          if (typeof recenterAndRedraw === 'function') {
            recenterAndRedraw(appConfig.home, appConfig.airport);
          }
        }
        if (data.events) {
          allEventsList = data.events;
          renderEventsTable(allEventsList);
        }
        if (typeof fetchAndRenderAnalytics === 'function') {
          fetchAndRenderAnalytics();
        }
      }
    } catch (e) {
      console.error("Error processing WS message:", e);
    }
  };

  ws.onerror = () => {
    startHttpPolling();
  };

  ws.onclose = () => {
    startHttpPolling();
    if (!reconnectTimer) {
      reconnectTimer = setInterval(() => {
        connectWebSocket();
      }, 4000);
    }
  };
}

function handleSnapshot(data) {
  currentAircraftList = data.aircraft || [];
  const weather = data.weather || {};
  latestWeather = weather;

  // 1. Update Header ADS-B Receiver Status Badge
  const adsbDot = document.getElementById('adsb-status-dot');
  const adsbText = document.getElementById('adsb-status-text');
  const isConnected = data.adsb_connected !== false;
  const totalCount = data.total_count !== undefined ? data.total_count : currentAircraftList.length;
  const geoCount = data.geofence_count !== undefined ? data.geofence_count : currentAircraftList.filter(a => a.in_geofence).length;

  if (adsbDot) adsbDot.style.backgroundColor = isConnected ? '#10b981' : '#ef4444';
  if (adsbText) {
    adsbText.textContent = isConnected ? `ADS-B: CONNECTED (${totalCount})` : `ADS-B: OFFLINE`;
  }

  // 2. Update geofence summary text
  const geoSummary = document.getElementById('radar-geofence-summary');
  if (geoSummary) {
    geoSummary.textContent = `${geoCount} within 3.5 NM`;
    geoSummary.style.color = geoCount > 0 ? '#ef4444' : '#94a3b8';
  }

  // 3. Render filtered aircraft on map and sidebar
  renderFilteredAircraft();

  // 4. Update Weather Cards
  updateWeatherUI(weather);
}

function onRadarScopeChange() {
  renderFilteredAircraft();
}

function renderFilteredAircraft() {
  const scopeSelect = document.getElementById('radar-scope-select');
  const scope = scopeSelect ? scopeSelect.value : 'all';
  const leadedOnly = document.getElementById('radar-filter-leaded')?.checked || false;

  let filtered = currentAircraftList;
  if (scope === 'geofence') {
    filtered = filtered.filter(a => a.in_geofence);
  }
  if (leadedOnly) {
    filtered = filtered.filter(a => a.aircraft_meta && a.aircraft_meta.is_leaded);
  }

  // Update map markers
  if (typeof updateAircraftMarkers === 'function') {
    updateAircraftMarkers(filtered, latestWeather);
  }

  // Update sidebar list
  updateAircraftSidebar(filtered, scope, leadedOnly);
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
  if (!weather) return;
  const ecowitt = weather.ecowitt || {};
  const aerodrome = weather.aerodrome || {};
  const isEcoConnected = Boolean(weather.is_ecowitt_connected);

  // Ground station (Ecowitt)
  const elEcoBadge = document.getElementById('weather-ecowitt-badge');
  const elEcoSpd = document.getElementById('weather-ecowitt-speed');
  const elEcoDetails = document.getElementById('weather-ecowitt-details');
  const elEcoSub = document.getElementById('weather-ecowitt-sub');

  if (isEcoConnected) {
    if (elEcoBadge) {
      elEcoBadge.textContent = 'ECOWITT LIVE';
      elEcoBadge.className = 'badge badge-green';
      elEcoBadge.style.background = '';
      elEcoBadge.style.color = '';
    }
    if (elEcoSpd) {
      elEcoSpd.textContent = `${ecowitt.wind_speed_mph || 0} mph`;
      elEcoSpd.style.color = 'var(--text-primary)';
    }
    if (elEcoDetails) {
      elEcoDetails.textContent = `Dir: ${ecowitt.wind_dir_deg || 0}° | Gust: ${ecowitt.wind_gust_mph || 0} mph`;
    }
    if (elEcoSub) {
      elEcoSub.textContent = ecowitt.temp_f ? `${ecowitt.temp_f}°F · Below Tree Line` : 'Below Tree Line';
      elEcoSub.style.color = '#38bdf8';
    }
  } else {
    if (elEcoBadge) {
      const isConfigured = weather.provider && weather.provider !== 'aerodrome';
      elEcoBadge.textContent = isConfigured ? 'OFFLINE' : 'NOT CONFIGURED';
      elEcoBadge.className = 'badge';
      elEcoBadge.style.background = 'rgba(148, 163, 184, 0.15)';
      elEcoBadge.style.color = '#94a3b8';
    }
    if (elEcoSpd) {
      elEcoSpd.textContent = 'Not Connected';
      elEcoSpd.style.color = '#94a3b8';
    }
    if (elEcoDetails) {
      elEcoDetails.textContent = 'Using Aerodrome METAR';
    }
    if (elEcoSub) {
      elEcoSub.textContent = 'No local sensor';
      elEcoSub.style.color = '#64748b';
    }
  }

  // Aerodrome (2W6 / KNHK)
  const elAeroBadge = document.getElementById('weather-aero-badge');
  const elAeroStation = document.getElementById('weather-aero-station');
  const elAeroSpd = document.getElementById('weather-aero-speed');
  const elAeroDetails = document.getElementById('weather-aero-details');
  const elAeroTime = document.getElementById('weather-aero-time');

  const aeroStation = aerodrome.station || 'KNHK';
  if (elAeroStation) {
    elAeroStation.textContent = `Aerodrome (${aeroStation})`;
  }

  if (aerodrome.status === 'live') {
    if (elAeroBadge) {
      elAeroBadge.textContent = 'METAR LIVE';
      elAeroBadge.className = 'badge badge-green';
    }
    if (elAeroSpd) {
      elAeroSpd.textContent = `${aerodrome.wind_speed_kts || 0} kts (${aerodrome.wind_speed_mph || 0} mph)`;
    }
    if (elAeroDetails) {
      const gustStr = aerodrome.wind_gust_kts && aerodrome.wind_gust_kts > (aerodrome.wind_speed_kts || 0)
        ? ` · Gust: ${aerodrome.wind_gust_kts} kts` : '';
      elAeroDetails.textContent = `Dir: ${aerodrome.wind_dir_text || (aerodrome.wind_dir_deg != null ? aerodrome.wind_dir_deg + '°' : 'VRB')}${gustStr}`;
    }
    if (elAeroTime) {
      const tempStr = aerodrome.temp_f != null ? `${aerodrome.temp_f}°F · ` : '';
      const timeStr = aerodrome.report_time ? `Obs ${aerodrome.report_time.substring(11, 16)}Z` : 'Standard 10m Mast';
      elAeroTime.textContent = `${tempStr}${timeStr}`;
    }
  } else {
    if (elAeroBadge) {
      elAeroBadge.textContent = aerodrome.status || 'CONNECTING';
      elAeroBadge.className = 'badge';
    }
  }

  // Raw METAR display strip
  const elRawMetar = document.getElementById('weather-raw-metar');
  if (elRawMetar) {
    if (aerodrome.raw_metar) {
      elRawMetar.textContent = `METAR: ${aerodrome.raw_metar}`;
      elRawMetar.title = `Station: ${aeroStation} · Updated: ${aerodrome.timestamp_utc || 'recent'}`;
    } else {
      elRawMetar.textContent = 'METAR: Awaiting observation data...';
    }
  }

  // Plume Drift Vector
  const elPlumeDir = document.getElementById('weather-plume-dir');
  if (elPlumeDir) {
    const driftDeg = weather.plume_drift_dir_deg != null ? Math.round(weather.plume_drift_dir_deg) : 300;
    const driftCard = weather.plume_drift_cardinal ? ` ${weather.plume_drift_cardinal}` : '';
    elPlumeDir.textContent = `${driftDeg}°${driftCard} (Plume Drift)`;
    elPlumeDir.title = `Winds blow from ${weather.effective_wind_dir_deg || 0}° (${weather.effective_wind_cardinal || ''}) at ${weather.effective_wind_speed_mph || 0} mph. Lead exhaust drifts towards ${driftDeg}°${driftCard}.`;
  }
}

async function refreshWeather(manual = false) {
  const btn = document.getElementById('btn-refresh-weather');
  if (btn) {
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.textContent = '...';
  }
  try {
    const res = await fetch('/api/weather/refresh', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.weather) {
      updateWeatherUI(data.weather);
      if (manual && typeof showToast === 'function') {
        const stn = data.weather.aerodrome?.station || 'Aerodrome';
        const wspd = data.weather.effective_wind_speed_mph || 0;
        const wdir = data.weather.effective_wind_cardinal || '';
        showToast(`✓ Weather updated from NOAA ${stn}: ${wspd} mph ${wdir}`);
      }
    }
  } catch (err) {
    console.error('Failed to refresh weather:', err);
    if (manual && typeof showToast === 'function') {
      showToast(`Weather refresh failed: ${err.message}`, true);
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.textContent = '↻';
    }
  }
}

function updateAircraftSidebar(list, scope = 'all', leadedOnly = false) {
  const container = document.getElementById('sidebar-aircraft-list');
  const countBadge = document.getElementById('sidebar-aircraft-count');
  if (!container) return;

  if (countBadge) countBadge.textContent = list.length;

  if (list.length === 0) {
    const totalTracked = currentAircraftList.length;
    let hint = `No aircraft currently in view.`;
    if (scope === 'geofence') {
      hint = `No aircraft currently within 3.5 NM house geofence (${totalTracked} active in regional coverage). Select "All Regional Traffic" above to inspect all flights.`;
    } else if (leadedOnly) {
      hint = `No 100LL leaded piston aircraft currently detected (${totalTracked} total active flights). Uncheck "100LL Leaded Only" to see commercial & turbine traffic.`;
    }
    container.innerHTML = `
      <div style="text-align: center; color: #64748b; padding: 2rem 1rem; font-size: 0.85rem; line-height: 1.5;">
        ${hint}
      </div>
    `;
    return;
  }

  container.innerHTML = list.map(ac => {
    const meta = ac.aircraft_meta || {};
    const disp = ac.dispersion || {};
    const isLeaded = meta.is_leaded;
    const isDownwind = disp.is_downwind;
    const inGeo = ac.in_geofence;

    return `
      <div class="aircraft-item ${isLeaded ? 'leaded' : 'turbine'}" style="${inGeo ? 'border-left: 4px solid #ef4444; background: rgba(239, 68, 68, 0.08);' : ''}">
        <div class="ac-top-row">
          <span class="ac-callsign" style="${inGeo ? 'color: #fca5a5; font-weight: 800;' : ''}">
            ${ac.flight || meta.tail_number || ac.hex}
            ${inGeo ? '<span style="font-size: 0.65rem; background: #ef4444; color: #fff; padding: 1px 4px; border-radius: 3px; margin-left: 4px;">GEOFENCE</span>' : ''}
          </span>
          <span class="ac-type-badge ${isLeaded ? 'type-100ll' : 'type-jeta'}">
            ${meta.fuel_type || '100LL'} (${meta.icao_type || 'UNKNOWN'})
          </span>
        </div>
        <div style="font-size: 0.72rem; color: #cbd5e1; margin-bottom: 0.35rem;">
          ${meta.model_name || 'Aircraft'}
        </div>
        <div class="ac-metrics">
          <div>
            <div style="font-size: 0.65rem; color: #64748b;">DISTANCE</div>
            <div class="ac-metric-val">${ac.dist_nm} NM</div>
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

    let scoreColor = '#10b981';
    if (ev.max_exposure_score >= 70) scoreColor = '#ef4444';
    else if (ev.max_exposure_score >= 40) scoreColor = '#f97316';
    else if (ev.max_exposure_score > 0) scoreColor = '#facc15';

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
      showToast(`Simulation mode ${active ? 'enabled' : 'disabled'}`);
    });
  }

  // 2. Weather Provider Selector change
  const weatherProviderSelect = document.getElementById('setting-weather-provider');
  if (weatherProviderSelect) {
    weatherProviderSelect.addEventListener('change', (e) => {
      updateWeatherPanels(e.target.value);
    });
  }

  // 3. Geocode Address Button (Non-blocking inline feedback)
  const geocodeBtn = document.getElementById('geocode-addr-btn');
  const geocodeMsg = document.getElementById('geocode-status-msg');
  if (geocodeBtn) {
    geocodeBtn.addEventListener('click', async () => {
      const addr = document.getElementById('setting-home-address').value.trim();
      if (!addr) {
        if (geocodeMsg) {
          geocodeMsg.style.display = 'block';
          geocodeMsg.style.background = 'rgba(239, 68, 68, 0.15)';
          geocodeMsg.style.color = '#fca5a5';
          geocodeMsg.textContent = 'Please enter a street address to search.';
        }
        return;
      }
      geocodeBtn.disabled = true;
      geocodeBtn.textContent = "Geocoding...";
      if (geocodeMsg) geocodeMsg.style.display = 'none';

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
            setHomeLocation(data.lat, data.lon, true);
          }
          if (geocodeMsg) {
            geocodeMsg.style.display = 'block';
            geocodeMsg.style.background = 'rgba(16, 185, 129, 0.15)';
            geocodeMsg.style.color = '#6ee7b7';
            geocodeMsg.innerHTML = `✓ Located (${data.source}): Lat ${data.lat}, Lon ${data.lon}<br/><span style="font-size:0.78rem; color:#a7f3d0;">Pin placed on map. Drag pin directly onto your house rooftop to fine-tune anytime.</span>`;
          }
          showToast(`📍 Located: ${data.lat}, ${data.lon}`);
        } else {
          if (geocodeMsg) {
            geocodeMsg.style.display = 'block';
            geocodeMsg.style.background = 'rgba(239, 68, 68, 0.15)';
            geocodeMsg.style.color = '#fca5a5';
            geocodeMsg.textContent = `Could not resolve "${addr}". Try street + ZIP (e.g. "123 Main St, 20650") or click "Drop Pin on Map".`;
          }
        }
      } catch (err) {
        if (geocodeMsg) {
          geocodeMsg.style.display = 'block';
          geocodeMsg.style.background = 'rgba(239, 68, 68, 0.15)';
          geocodeMsg.style.color = '#fca5a5';
          geocodeMsg.textContent = `Geocoding request failed: ${err.message}`;
        }
      } finally {
        geocodeBtn.disabled = false;
        geocodeBtn.textContent = "Find & Geocode";
      }
    });
  }

  // 4. Airport Lookup Button (Non-blocking inline feedback)
  const airportBtn = document.getElementById('lookup-airport-btn');
  const airportMsg = document.getElementById('airport-status-msg');
  if (airportBtn) {
    airportBtn.addEventListener('click', async () => {
      const code = document.getElementById('setting-airport-id').value.trim();
      if (!code) {
        if (airportMsg) {
          airportMsg.style.display = 'block';
          airportMsg.style.background = 'rgba(239, 68, 68, 0.15)';
          airportMsg.style.color = '#fca5a5';
          airportMsg.textContent = 'Please enter an airport code (e.g. 2W6, KRHV, KSMO, KGAI).';
        }
        return;
      }
      airportBtn.disabled = true;
      airportBtn.textContent = "Looking up...";
      if (airportMsg) airportMsg.style.display = 'none';

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
          if (airportMsg) {
            airportMsg.style.display = 'block';
            airportMsg.style.background = 'rgba(16, 185, 129, 0.15)';
            airportMsg.style.color = '#6ee7b7';
            airportMsg.textContent = `✓ Loaded: ${apt.name} (${apt.id}) - Rwy ${apt.runway_heading_1}° / ${apt.runway_heading_2}°`;
          }
          showToast(`✈️ Loaded airfield: ${apt.id}`);
        } else {
          if (airportMsg) {
            airportMsg.style.display = 'block';
            airportMsg.style.background = 'rgba(239, 68, 68, 0.15)';
            airportMsg.style.color = '#fca5a5';
            airportMsg.textContent = `Airport code "${code}" not found. You can enter runway headings manually below.`;
          }
        }
      } catch (err) {
        if (airportMsg) {
          airportMsg.style.display = 'block';
          airportMsg.style.background = 'rgba(239, 68, 68, 0.15)';
          airportMsg.style.color = '#fca5a5';
          airportMsg.textContent = `Airport lookup failed: ${err.message}`;
        }
      } finally {
        airportBtn.disabled = false;
        airportBtn.textContent = "Lookup Airport";
      }
    });
  }

  // 4b. ADS-B Provider Selector onchange
  const adsbProviderSelect = document.getElementById('setting-adsb-provider');
  if (adsbProviderSelect) {
    adsbProviderSelect.addEventListener('change', (e) => {
      updateAdsbPanels(e.target.value);
    });
  }

  // 4c. Keep Host/Port/Path in sync with direct URL
  const inputHost = document.getElementById('setting-readsb-host');
  const inputPort = document.getElementById('setting-readsb-port');
  const inputPath = document.getElementById('setting-readsb-path');
  const inputUrl = document.getElementById('setting-readsb-url');

  function syncReadsbUrlFromInputs() {
    const h = inputHost ? inputHost.value.trim() : '';
    if (!h) return;
    const p = inputPort ? inputPort.value.trim() : '';
    const path = (inputPath && inputPath.value.trim()) ? inputPath.value.trim() : '/data/aircraft.pb';
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const cleanHost = (h.startsWith('http://') || h.startsWith('https://')) ? h : `http://${h}`;
    const portPart = (p && p !== '80' && p !== '443') ? `:${p}` : '';
    if (inputUrl) {
      inputUrl.value = `${cleanHost}${portPart}${cleanPath}`;
    }
  }

  if (inputHost) inputHost.addEventListener('input', syncReadsbUrlFromInputs);
  if (inputPort) inputPort.addEventListener('input', syncReadsbUrlFromInputs);
  if (inputPath) inputPath.addEventListener('input', syncReadsbUrlFromInputs);

  // 5. Test ADS-B Connection Button
  const testAdsbBtn = document.getElementById('test-readsb-btn');
  const adsbStatus = document.getElementById('readsb-test-status');
  if (testAdsbBtn) {
    testAdsbBtn.addEventListener('click', async () => {
      const provider = document.getElementById('setting-adsb-provider')?.value || 'readsb_local';
      const host = document.getElementById('setting-readsb-host')?.value.trim();
      const port = document.getElementById('setting-readsb-port')?.value.trim();
      const path = document.getElementById('setting-readsb-path')?.value.trim();
      const url = document.getElementById('setting-readsb-url')?.value.trim();
      const customUrl = document.getElementById('setting-adsb-custom-url')?.value.trim();

      testAdsbBtn.disabled = true;
      testAdsbBtn.textContent = "Testing...";
      if (adsbStatus) adsbStatus.style.display = 'none';

      try {
        let q = `/api/test/adsb?provider=${encodeURIComponent(provider)}`;
        if (provider === 'custom_url') {
          q += `&url=${encodeURIComponent(customUrl || '')}`;
        } else if (provider === 'readsb_local') {
          if (url) q += `&url=${encodeURIComponent(url)}`;
          else q += `&host=${encodeURIComponent(host || 'localhost')}&port=${encodeURIComponent(port || '80')}&path=${encodeURIComponent(path || '/tar1090/data/aircraft.json')}`;
        }

        const resp = await fetch(q);
        const data = await resp.json();
        if (adsbStatus) {
          adsbStatus.style.display = 'block';
          if (data.success) {
            adsbStatus.style.background = 'rgba(16, 185, 129, 0.15)';
            adsbStatus.style.color = '#6ee7b7';
            adsbStatus.textContent = `✓ Connected to ${data.provider}! ${data.aircraft_count} aircraft currently tracked (${data.latency_ms} ms latency)`;
            showToast(`✓ ADS-B connected: ${data.aircraft_count} aircraft`);
          } else {
            adsbStatus.style.background = 'rgba(239, 68, 68, 0.15)';
            adsbStatus.style.color = '#fca5a5';
            adsbStatus.textContent = `✗ Connection failed (${data.provider}): ${data.error}`;
          }
        }
      } catch (err) {
        if (adsbStatus) {
          adsbStatus.style.display = 'block';
          adsbStatus.style.background = 'rgba(239, 68, 68, 0.15)';
          adsbStatus.style.color = '#fca5a5';
          adsbStatus.textContent = `Network error: ${err.message}`;
        }
      } finally {
        testAdsbBtn.disabled = false;
        testAdsbBtn.textContent = "Test Source";
      }
    });
  }

  // 6. Test Ecowitt Gateway Button
  const testEcoBtn = document.getElementById('test-ecowitt-btn');
  const ecoStatus = document.getElementById('ecowitt-test-status');
  if (testEcoBtn) {
    testEcoBtn.addEventListener('click', async () => {
      const ip = document.getElementById('setting-ecowitt-ip')?.value.trim();
      const port = document.getElementById('setting-ecowitt-port')?.value.trim();

      if (!ip) {
        if (ecoStatus) {
          ecoStatus.style.display = 'block';
          ecoStatus.style.background = 'rgba(239, 68, 68, 0.15)';
          ecoStatus.style.color = '#fca5a5';
          ecoStatus.textContent = "Please enter your Ecowitt gateway's local IP address (e.g. 192.168.1.150).";
        }
        return;
      }

      testEcoBtn.disabled = true;
      testEcoBtn.textContent = "Pinging...";
      if (ecoStatus) ecoStatus.style.display = 'none';

      try {
        const resp = await fetch(`/api/test/ecowitt?ip=${encodeURIComponent(ip)}&port=${encodeURIComponent(port || '80')}`);
        const data = await resp.json();
        if (ecoStatus) {
          ecoStatus.style.display = 'block';
          if (data.success) {
            ecoStatus.style.background = 'rgba(16, 185, 129, 0.15)';
            ecoStatus.style.color = '#6ee7b7';
            ecoStatus.textContent = `✓ Connected to Ecowitt gateway! Responded in ${data.latency_ms} ms with live sensor feed.`;
            showToast(`✓ Ecowitt gateway online (${data.latency_ms} ms)`);
          } else {
            ecoStatus.style.background = 'rgba(239, 68, 68, 0.15)';
            ecoStatus.style.color = '#fca5a5';
            ecoStatus.textContent = `✗ Cannot connect to ${data.url}: ${data.error}. Check that gateway IP is correct and on the same Wi-Fi.`;
          }
        }
      } catch (err) {
        if (ecoStatus) {
          ecoStatus.style.display = 'block';
          ecoStatus.style.background = 'rgba(239, 68, 68, 0.15)';
          ecoStatus.style.color = '#fca5a5';
          ecoStatus.textContent = `Network error: ${err.message}`;
        }
      } finally {
        testEcoBtn.disabled = false;
        testEcoBtn.textContent = "Test Gateway";
      }
    });
  }

  // 7. Save & Apply Configuration Button
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
        heatmap_radius_nm: parseFloat(document.getElementById('setting-heatmap-radius')?.value) || undefined,
        active_radius_nm: parseFloat(document.getElementById('setting-active-radius')?.value) || undefined,
        flyover_radius_nm: parseFloat(document.getElementById('setting-flyover-radius')?.value) || undefined,
        adsb_provider: document.getElementById('setting-adsb-provider')?.value || undefined,
        adsb_custom_url: document.getElementById('setting-adsb-custom-url')?.value.trim() || undefined,
        readsb_url: document.getElementById('setting-readsb-url')?.value.trim() || undefined,
        readsb_host: document.getElementById('setting-readsb-host')?.value.trim() || undefined,
        readsb_port: parseInt(document.getElementById('setting-readsb-port')?.value) || undefined,
        readsb_path: document.getElementById('setting-readsb-path')?.value.trim() || undefined,
        weather_provider: document.getElementById('setting-weather-provider')?.value || undefined,
        ecowitt_ip: document.getElementById('setting-ecowitt-ip')?.value.trim() || undefined,
        ecowitt_port: parseInt(document.getElementById('setting-ecowitt-port')?.value) || undefined,
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
          window.appConfig = appConfig;
          applyConfigToUI(appConfig);
          if (typeof recenterAndRedraw === 'function') {
            recenterAndRedraw(appConfig.home, appConfig.airport);
          }
          showToast("✓ Configuration saved & applied successfully!");
        } else {
          showToast("Error saving configuration. Please check values.", true);
        }
      } catch (err) {
        showToast(`Failed to save: ${err.message}`, true);
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save & Apply Configuration";
      }
    });
  }

  // 8. Filter checkbox on logs table
  const filterCheckbox = document.getElementById('filter-leaded-only');
  if (filterCheckbox) {
    filterCheckbox.addEventListener('change', () => refreshEvents());
  }
}

async function clearAllLogs() {
  if (!confirm("Are you sure you want to purge all recorded flight logs and track history? This will reset logs to start clean with live data.")) {
    return;
  }
  try {
    const resp = await fetch('/api/events/clear', { method: 'POST' });
    const data = await resp.json();
    if (data.status === 'success') {
      showToast(`✓ Cleared ${data.purged_count} flyover log records`);
      allEventsList = [];
      renderEventsTable([]);
      refreshStats();
      const badge = document.getElementById('nav-logs-badge');
      if (badge) {
        badge.textContent = '0';
        badge.style.display = 'none';
      }
    }
  } catch (err) {
    showToast(`Error clearing logs: ${err.message}`, true);
  }
}

// Attach globally for inline HTML event attributes
window.onRadarScopeChange = onRadarScopeChange;
window.renderFilteredAircraft = renderFilteredAircraft;
window.clearAllLogs = clearAllLogs;
window.refreshEvents = refreshEvents;
