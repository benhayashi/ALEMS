/**
 * Analytics Charts for ALEMS using Chart.js.
 */

let exposureChart = null;
let fleetChart = null;

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
          labels: ['06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00'],
          datasets: [
            {
              label: '100LL Piston Flyovers',
              data: [1, 3, 8, 12, 15, 9, 6, 2],
              backgroundColor: 'rgba(239, 68, 68, 0.65)',
              borderColor: '#ef4444',
              borderWidth: 1,
              yAxisID: 'y'
            },
            {
              label: 'Peak Lead Exposure Score',
              data: [15, 42, 65, 88, 92, 70, 45, 20],
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
            legend: { labels: { color: '#94a3b8', font: { size: 11 } } }
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
              ticks: { color: '#94a3b8', font: { size: 10 } },
              title: { display: false }
            },
            y1: {
              type: 'linear',
              position: 'right',
              grid: { drawOnChartArea: false },
              ticks: { color: '#f59e0b', font: { size: 10 } },
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
          labels: ['100LL Piston', 'Turboprop (Jet-A)', 'Turbofan/Jet'],
          datasets: [{
            data: [78, 14, 8],
            backgroundColor: ['#ef4444', '#3b82f6', '#64748b'],
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
}

function updateAnalyticsUI(stats) {
  if (!stats) return;

  const elTotal = document.getElementById('stat-total-flyovers');
  const elLeaded = document.getElementById('stat-leaded-flyovers');
  const elDownwind = document.getElementById('stat-downwind-events');
  const elMinSlant = document.getElementById('stat-min-slant');
  const elMaxRisk = document.getElementById('stat-peak-risk');

  if (elTotal) elTotal.textContent = stats.total_events || 0;
  if (elLeaded) elLeaded.textContent = stats.total_leaded_events || 0;
  if (elDownwind) elDownwind.textContent = stats.total_downwind_leaded || 0;
  if (elMinSlant) elMinSlant.textContent = `${stats.min_slant_range_ft ? Math.round(stats.min_slant_range_ft).toLocaleString() : '--'} ft`;
  if (elMaxRisk) elMaxRisk.textContent = `${stats.max_risk_score || 0} / 100`;
}
