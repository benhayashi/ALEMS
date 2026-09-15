/**
 * Analytics Charts for ALEMS using Chart.js.
 * Displays dynamic time-windowed lead exposure trends and fleet distributions.
 */

let exposureChart = null;
let fleetChart = null;
let currentAnalyticsRange = '24h';

function initCharts() {
  if (typeof Chart === 'undefined') {
    console.warn("Chart.js is not loaded");
    return;
  }

  const ctxExposure = document.getElementById('exposureChart');
  const ctxFleet = document.getElementById('fleetChart');

  if (ctxExposure && !exposureChart) {
    try {
      exposureChart = new Chart(ctxExposure, {
        type: 'bar',
        data: {
          labels: [],
          datasets: [
            {
              label: '100LL Piston Flyovers',
              data: [],
              backgroundColor: 'rgba(239, 68, 68, 0.65)',
              borderColor: '#ef4444',
              borderWidth: 1,
              yAxisID: 'y'
            },
            {
              label: 'Peak Lead Exposure Score',
              data: [],
              type: 'line',
              borderColor: '#f59e0b',
              backgroundColor: 'rgba(245, 158, 11, 0.2)',
              fill: false,
              tension: 0.3,
              yAxisID: 'y1'
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: '#94a3b8', font: { size: 11 } } },
            tooltip: {
              callbacks: {
                label: function(context) {
                  if (context.datasetIndex === 0) {
                    return ` ${context.parsed.y} leaded passes`;
                  }
                  return ` Peak Risk: ${context.parsed.y} / 100`;
                }
              }
            }
          },
          scales: {
            x: {
              grid: { color: '#334155' },
              ticks: { color: '#94a3b8', font: { size: 10 } }
            },
            y: {
              type: 'linear',
              position: 'left',
              grid: { color: '#334155' },
              ticks: { color: '#94a3b8', font: { size: 10 }, stepSize: 1 },
              title: { display: true, text: '100LL Passes', color: '#94a3b8', font: { size: 10 } },
              beginAtZero: true
            },
            y1: {
              type: 'linear',
              position: 'right',
              grid: { drawOnChartArea: false },
              ticks: { color: '#f59e0b', font: { size: 10 } },
              title: { display: true, text: 'Lead Exposure (0-100)', color: '#f59e0b', font: { size: 10 } },
              min: 0,
              max: 100
            }
          }
        }
      });
    } catch (e) {
      console.warn("Failed to create exposureChart:", e);
    }
  }

  if (ctxFleet && !fleetChart) {
    try {
      fleetChart = new Chart(ctxFleet, {
        type: 'doughnut',
        data: {
          labels: ['No Data Yet'],
          datasets: [{
            data: [0],
            backgroundColor: ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#64748b'],
            borderColor: '#1e293b',
            borderWidth: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom',
              labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 12 }
            }
          }
        }
      });
    } catch (e) {
      console.warn("Failed to create fleetChart:", e);
    }
  }

  // Initial fetch for active range
  fetchAndRenderAnalytics(currentAnalyticsRange);
}

async function changeAnalyticsTimeRange(range) {
  currentAnalyticsRange = range;

  // Update button active state
  const buttons = document.querySelectorAll('#analytics-time-group button');
  buttons.forEach(btn => {
    if (btn.getAttribute('data-range') === range || btn.id === `btn-range-${range}`) {
      btn.classList.add('active-range');
    } else {
      btn.classList.remove('active-range');
    }
  });

  // Update indicator text
  const indicator = document.getElementById('analytics-range-indicator');
  const labels = {
    '24h': 'Showing: Today (Past 24 Hours)',
    '7d': 'Showing: Past 7 Days',
    '30d': 'Showing: Past 30 Days',
    'all': 'Showing: All Time (Cumulative)'
  };
  if (indicator) indicator.textContent = labels[range] || `Showing: ${range}`;

  await fetchAndRenderAnalytics(range);
}

async function fetchAndRenderAnalytics(range = currentAnalyticsRange) {
  try {
    const resp = await fetch(`/api/statistics?time_range=${encodeURIComponent(range)}`);
    if (!resp.ok) return;
    const stats = await resp.json();
    updateAnalyticsUI(stats);
  } catch (err) {
    console.error("Failed to fetch analytics statistics:", err);
  }
}

function updateAnalyticsUI(stats) {
  if (!stats) return;

  // 1. Update 5 Metric Stat Cards
  const elTotal = document.getElementById('stat-total-flyovers');
  const elLeaded = document.getElementById('stat-leaded-flyovers');
  const elDownwind = document.getElementById('stat-downwind-events');
  const elMinSlant = document.getElementById('stat-min-slant');
  const elMaxRisk = document.getElementById('stat-peak-risk');

  if (elTotal) elTotal.textContent = stats.total_events || 0;
  if (elLeaded) elLeaded.textContent = stats.total_leaded_events || 0;
  if (elDownwind) elDownwind.textContent = stats.total_downwind_leaded || 0;
  if (elMinSlant) {
    elMinSlant.textContent = stats.min_slant_range_ft && stats.min_slant_range_ft > 0
      ? `${Math.round(stats.min_slant_range_ft).toLocaleString()} ft`
      : '-- ft';
  }
  if (elMaxRisk) elMaxRisk.textContent = `${stats.max_risk_score || 0} / 100`;

  // 2. Update Exposure Timeline Chart
  if (exposureChart && stats.timeline) {
    exposureChart.data.labels = stats.timeline.labels || [];
    exposureChart.data.datasets[0].data = stats.timeline.leaded_counts || [];
    exposureChart.data.datasets[1].data = stats.timeline.risk_scores || [];
    exposureChart.update();
  }

  // 3. Update Fleet Distribution Chart
  if (fleetChart && stats.fleet_breakdown) {
    const fb = stats.fleet_breakdown;
    if (fb.labels && fb.labels.length > 0 && fb.counts.some(c => c > 0)) {
      fleetChart.data.labels = fb.labels;
      fleetChart.data.datasets[0].data = fb.counts;
      fleetChart.data.datasets[0].backgroundColor = fb.labels.map(l => {
        if (l.includes('100LL') || l.includes('Piston')) return '#ef4444';
        if (l.includes('Jet-A') || l.includes('Turboprop')) return '#3b82f6';
        if (l.includes('Turbofan') || l.includes('Jet')) return '#64748b';
        return '#10b981';
      });
    } else {
      fleetChart.data.labels = ['No Passes Logged In Period'];
      fleetChart.data.datasets[0].data = [0];
      fleetChart.data.datasets[0].backgroundColor = ['#334155'];
    }
    fleetChart.update();
  }
}

function resizeCharts() {
  if (exposureChart) exposureChart.resize();
  if (fleetChart) fleetChart.resize();
}

// Bind globally for HTML event attributes
window.changeAnalyticsTimeRange = changeAnalyticsTimeRange;
window.fetchAndRenderAnalytics = fetchAndRenderAnalytics;
window.resizeCharts = resizeCharts;

