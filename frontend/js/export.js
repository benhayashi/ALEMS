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
    alert(`Corroboration SHA256 copied to clipboard:\n${hashStr}`);
  }).catch(err => {
    prompt("Copy hash:", hashStr);
  });
}
