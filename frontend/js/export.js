/**
 * Corroboration Log Export & Hash Verification for ALEMS.
 */

function downloadAuditCsv(leadedOnly = false) {
  const url = `/api/export/csv?leaded_only=${leadedOnly}`;
  const link = document.createElement('a');
  link.href = url;
  link.download = `alems_flyover_corroboration_${new Date().toISOString().slice(0,10)}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function downloadEventTrajectoryCsv(eventId) {
  if (!eventId) return;
  const url = `/api/export/event/${eventId}/csv`;
  const link = document.createElement('a');
  link.href = url;
  link.download = `alems_trajectory_${eventId}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function copyCorroborationHash(hashStr) {
  navigator.clipboard.writeText(hashStr).then(() => {
    if (typeof showToast === 'function') {
      showToast(`SHA256 hash copied to clipboard: ${hashStr.slice(0, 16)}...`);
    }
  }).catch(err => {
    prompt("Copy hash:", hashStr);
  });
}
