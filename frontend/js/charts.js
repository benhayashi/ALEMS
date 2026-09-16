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
              backgroundColor: function(ctx) {
                const val = ctx.raw || 0;
                if (val <= 0) return 'rgba(16, 185, 129, 0.4)';
                if (val <= 2) return 'rgba(250, 204, 21, 0.65)';
                if (val <= 5) return 'rgba(249, 115, 22, 0.75)';
                return 'rgba(239, 68, 68, 0.85)';
              },
              borderColor: function(ctx) {
                const val = ctx.raw || 0;
                if (val <= 0) return '#10b981';
                if (val <= 2) return '#facc15';
                if (val <= 5) return '#f97316';
                return '#ef4444';
              },
              borderWidth: 1,
              borderRadius: 3,
              yAxisID: 'y'
            },
            {
              label: 'Peak Lead Exposure Score',
              data: [],
              type: 'line',
              borderColor: '#f59e0b',
              backgroundColor: 'rgba(245, 158, 11, 0.12)',
              fill: true,
              tension: 0.3,
              pointBackgroundColor: function(ctx) {
                const score = ctx.raw || 0;
                if (score <= 0) return '#10b981';
                if (score < 40) return '#facc15';
                if (score < 70) return '#f97316';
                return '#ef4444';
              },
              pointBorderColor: '#0f172a',
              pointBorderWidth: 1.5,
              pointRadius: 4.5,
              pointHoverRadius: 7,
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
                    const v = context.parsed.y;
                    let tier = 'Clean';
                    if (v > 5) tier = 'High Frequency';
                    else if (v > 2) tier = 'Moderate Frequency';
                    else if (v > 0) tier = 'Low Frequency';
                    return ` 100LL Passes: ${v} (${tier})`;
                  }
                  const score = context.parsed.y;
                  let tier = 'Clean / None';
                  if (score >= 70) tier = 'Critical / Direct Plume';
                  else if (score >= 40) tier = 'Elevated Downwind';
                  else if (score > 0) tier = 'Low / Moderate';
                  return ` Peak Exposure: ${score} / 100 (${tier})`;
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
              title: { display: true, text: '100LL Passes (Count)', color: '#94a3b8', font: { size: 10 } },
              beginAtZero: true
            },
            y1: {
              type: 'linear',
              position: 'right',
              grid: { drawOnChartArea: false },
              ticks: { color: '#f59e0b', font: { size: 10 } },
              title: { display: true, text: 'Peak Exposure Index (0 – 100)', color: '#f59e0b', font: { size: 10 } },
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

  // 100LL Piston Passes: Dynamic green -> yellow -> orange -> red
  if (elLeaded) {
    const leadedCount = stats.total_leaded_events || 0;
    elLeaded.textContent = leadedCount;
    const elLeadedDesc = document.getElementById('stat-leaded-flyovers-desc');
    const elLeadedCard = elLeaded.closest('.stat-card');

    if (leadedCount === 0) {
      elLeaded.style.color = '#10b981';
      if (elLeadedDesc) elLeadedDesc.textContent = "Zero leaded passes (Clean)";
      if (elLeadedCard) elLeadedCard.style.borderColor = 'rgba(16, 185, 129, 0.25)';
    } else if (leadedCount <= 3) {
      elLeaded.style.color = '#facc15';
      if (elLeadedDesc) elLeadedDesc.textContent = "Low leaded frequency";
      if (elLeadedCard) elLeadedCard.style.borderColor = 'rgba(250, 204, 21, 0.3)';
    } else if (leadedCount <= 9) {
      elLeaded.style.color = '#f97316';
      if (elLeadedDesc) elLeadedDesc.textContent = "Moderate leaded frequency";
      if (elLeadedCard) elLeadedCard.style.borderColor = 'rgba(249, 115, 22, 0.35)';
    } else {
      elLeaded.style.color = '#ef4444';
      if (elLeadedDesc) elLeadedDesc.textContent = "High frequency 100LL passes";
      if (elLeadedCard) elLeadedCard.style.borderColor = 'rgba(239, 68, 68, 0.4)';
    }
  }

  if (elDownwind) elDownwind.textContent = stats.total_downwind_leaded || 0;
  if (elMinSlant) {
    elMinSlant.textContent = stats.min_slant_range_ft && stats.min_slant_range_ft > 0
      ? `${Math.round(stats.min_slant_range_ft).toLocaleString()} ft`
      : '-- ft';
  }

  // Peak Exposure Score: Dynamic green -> yellow -> orange -> red
  if (elMaxRisk) {
    const score = Number(stats.max_risk_score || 0);
    elMaxRisk.textContent = `${score} / 100`;
    const elRiskDesc = document.getElementById('stat-peak-risk-desc');
    const elRiskCard = elMaxRisk.closest('.stat-card');

    if (score === 0) {
      elMaxRisk.style.color = '#10b981';
      if (elRiskDesc) elRiskDesc.innerHTML = `<span style="color: #10b981; font-weight: 600;">Clean / None</span> &bull; No lead detected`;
      if (elRiskCard) elRiskCard.style.borderColor = 'rgba(16, 185, 129, 0.25)';
    } else if (score < 40) {
      elMaxRisk.style.color = '#facc15';
      if (elRiskDesc) elRiskDesc.innerHTML = `<span style="color: #facc15; font-weight: 600;">Low / Moderate</span> &bull; Upwind or high pass`;
      if (elRiskCard) elRiskCard.style.borderColor = 'rgba(250, 204, 21, 0.3)';
    } else if (score < 70) {
      elMaxRisk.style.color = '#f97316';
      if (elRiskDesc) elRiskDesc.innerHTML = `<span style="color: #f97316; font-weight: 600;">Elevated</span> &bull; Downwind or close pass`;
      if (elRiskCard) elRiskCard.style.borderColor = 'rgba(249, 115, 22, 0.35)';
    } else {
      elMaxRisk.style.color = '#ef4444';
      if (elRiskDesc) elRiskDesc.innerHTML = `<span style="color: #ef4444; font-weight: 600;">Critical / Direct Plume</span> &bull; Overhead departure`;
      if (elRiskCard) elRiskCard.style.borderColor = 'rgba(239, 68, 68, 0.4)';
    }
  }

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

// Modal dialog controllers for Peak Exposure Information
function openExposureInfoModal() {
  const dlg = document.getElementById('exposure-info-dialog');
  if (dlg && typeof dlg.showModal === 'function') {
    dlg.showModal();
  }
}

function closeExposureInfoModal() {
  const dlg = document.getElementById('exposure-info-dialog');
  if (dlg && typeof dlg.close === 'function') {
    dlg.close();
  }
}

// Close dialog when clicking outside modal on backdrop
document.addEventListener('DOMContentLoaded', () => {
  const dlg = document.getElementById('exposure-info-dialog');
  if (dlg) {
    dlg.addEventListener('click', (e) => {
      const rect = dlg.getBoundingClientRect();
      if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
        dlg.close();
      }
    });
  }
});

// Bind globally for HTML event attributes
window.changeAnalyticsTimeRange = changeAnalyticsTimeRange;
window.fetchAndRenderAnalytics = fetchAndRenderAnalytics;
window.resizeCharts = resizeCharts;
window.openExposureInfoModal = openExposureInfoModal;
window.closeExposureInfoModal = closeExposureInfoModal;

