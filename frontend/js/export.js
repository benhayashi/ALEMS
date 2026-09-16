/**
 * Corroboration Log Export & Hash Verification for ALEMS.
 * Includes full database and configuration backup and restore for Docker / Raspberry Pi migrations.
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

// ----------------------------------------------------
// Database & Configuration Migration Functions
// ----------------------------------------------------

function downloadBackupBundle() {
  if (typeof showToast === 'function') showToast("Preparing full migration bundle (.zip)...");
  const link = document.createElement('a');
  link.href = '/api/backup/bundle';
  link.download = `alems_migration_bundle_${new Date().toISOString().slice(0,10)}.zip`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function downloadDatabaseSnapshot() {
  if (typeof showToast === 'function') showToast("Preparing SQLite database snapshot (.db)...");
  const link = document.createElement('a');
  link.href = '/api/backup/database';
  link.download = `alems_backup_${new Date().toISOString().slice(0,10)}.db`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function downloadConfigYaml() {
  const link = document.createElement('a');
  link.href = '/api/backup/config?format=yaml';
  link.download = `config.yaml`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Staged migration file state
let stagedMigrationFile = null;

function setupMigrationUI() {
  const dropzone = document.getElementById('migration-dropzone');
  const fileInput = document.getElementById('migration-file-input');
  const browseBtn = document.getElementById('browse-backup-btn');

  if (!dropzone || !fileInput) return;

  if (browseBtn) {
    browseBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      fileInput.click();
    });
  }

  dropzone.addEventListener('click', () => fileInput.click());

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    }, false);
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      handleSelectedBackupFile(files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleSelectedBackupFile(e.target.files[0]);
    }
  });
}

async function handleSelectedBackupFile(file) {
  stagedMigrationFile = file;
  const inspectBox = document.getElementById('migration-inspect-box');
  const filenameEl = document.getElementById('inspect-filename');
  const detailsEl = document.getElementById('inspect-details');
  const badgeEl = document.getElementById('inspect-badge');
  const statusEl = document.getElementById('migration-status');

  if (statusEl) statusEl.style.display = 'none';
  if (inspectBox) inspectBox.style.display = 'block';
  if (filenameEl) filenameEl.textContent = file.name;
  if (badgeEl) {
    badgeEl.textContent = "Validating...";
    badgeEl.className = "badge badge-cyan";
  }
  if (detailsEl) {
    detailsEl.innerHTML = `<em>Inspecting package and verifying checksums... (${(file.size / 1024).toFixed(1)} KB)</em>`;
  }

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/backup/inspect', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      if (badgeEl) {
        badgeEl.textContent = "Invalid Format";
        badgeEl.className = "badge badge-lead";
      }
      if (detailsEl) {
        detailsEl.innerHTML = `<span style="color: #fca5a5;">❌ Error: ${data.error || 'Failed to inspect file'}</span>`;
      }
      const restoreBtn = document.getElementById('confirm-restore-btn');
      if (restoreBtn) restoreBtn.disabled = true;
      return;
    }

    const restoreBtn = document.getElementById('confirm-restore-btn');
    if (restoreBtn) restoreBtn.disabled = false;

    if (badgeEl) {
      badgeEl.textContent = data.type === 'bundle_zip' ? 'Full Migration Bundle' :
                            data.type === 'database' ? 'SQLite Database' : 'Config YAML/JSON';
      badgeEl.className = "badge badge-green";
    }

    let html = '';
    if (data.type === 'bundle_zip') {
      const dbInfo = data.database_info || {};
      html = `
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.4rem;">
          <div>📦 <strong>Files:</strong> ${data.files.join(', ')}</div>
          <div>💾 <strong>Compressed:</strong> ${(data.size_bytes / 1024 / 1024).toFixed(2)} MB</div>
        </div>
        <div style="background: rgba(0,0,0,0.25); padding: 0.4rem 0.6rem; border-radius: 4px; font-size: 0.76rem;">
          📊 <strong>Database:</strong> ${dbInfo.event_count || 0} flyovers, ${dbInfo.point_count || 0} track points, ${(dbInfo.registry_count || 0).toLocaleString()} FAA aircraft records.
        </div>
      `;
    } else if (data.type === 'database') {
      const dbInfo = data.database_info || {};
      html = `
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.4rem;">
          <div>🗄️ <strong>Type:</strong> SQLite 3 Database</div>
          <div>💾 <strong>Size:</strong> ${(data.size_bytes / 1024 / 1024).toFixed(2)} MB</div>
        </div>
        <div style="background: rgba(0,0,0,0.25); padding: 0.4rem 0.6rem; border-radius: 4px; font-size: 0.76rem;">
          📊 <strong>Database:</strong> ${dbInfo.event_count || 0} flyovers, ${dbInfo.point_count || 0} track points, ${(dbInfo.registry_count || 0).toLocaleString()} FAA aircraft records.
        </div>
      `;
    } else if (data.type === 'config') {
      html = `
        <div>⚙️ <strong>Configuration File (${data.format.toUpperCase()}):</strong> Found ${data.valid_keys_count} recognized station settings (${data.keys.join(', ')}).</div>
      `;
    }

    if (detailsEl) detailsEl.innerHTML = html;

  } catch (err) {
    if (badgeEl) {
      badgeEl.textContent = "Error";
      badgeEl.className = "badge badge-lead";
    }
    if (detailsEl) {
      detailsEl.innerHTML = `<span style="color: #fca5a5;">❌ Failed to inspect file: ${err.message}</span>`;
    }
  }
}

function cancelMigrationUpload() {
  stagedMigrationFile = null;
  const fileInput = document.getElementById('migration-file-input');
  if (fileInput) fileInput.value = '';
  const inspectBox = document.getElementById('migration-inspect-box');
  if (inspectBox) inspectBox.style.display = 'none';
  const statusEl = document.getElementById('migration-status');
  if (statusEl) statusEl.style.display = 'none';
}

async function executeMigrationRestore() {
  if (!stagedMigrationFile) return;

  const restoreBtn = document.getElementById('confirm-restore-btn');
  const statusEl = document.getElementById('migration-status');

  if (restoreBtn) {
    restoreBtn.disabled = true;
    restoreBtn.textContent = "Restoring...";
  }

  if (statusEl) {
    statusEl.style.display = 'block';
    statusEl.style.background = 'rgba(59, 130, 246, 0.15)';
    statusEl.style.border = '1px solid rgba(59, 130, 246, 0.4)';
    statusEl.style.color = '#93c5fd';
    statusEl.textContent = "Applying snapshot, verifying schema, and syncing database...";
  }

  const formData = new FormData();
  formData.append('file', stagedMigrationFile);

  try {
    const res = await fetch('/api/backup/restore', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      if (statusEl) {
        statusEl.style.background = 'rgba(239, 68, 68, 0.15)';
        statusEl.style.border = '1px solid rgba(239, 68, 68, 0.4)';
        statusEl.style.color = '#fca5a5';
        statusEl.textContent = `❌ Restore Failed: ${data.error || 'Server error'}`;
      }
      if (restoreBtn) {
        restoreBtn.disabled = false;
        restoreBtn.textContent = "Confirm & Restore";
      }
      return;
    }

    if (statusEl) {
      statusEl.style.background = 'rgba(16, 185, 129, 0.15)';
      statusEl.style.border = '1px solid rgba(16, 185, 129, 0.4)';
      statusEl.style.color = '#6ee7b7';
      let msg = "✓ Successfully restored: ";
      if (data.database_restored) msg += `Database (${data.database_info?.registry_count?.toLocaleString() || '440k+'} registry records) `;
      if (data.config_restored) msg += `& Configuration (${data.config_keys_updated?.length || 0} keys updated)`;
      statusEl.textContent = msg;
    }

    if (typeof showToast === 'function') {
      showToast("Restore complete! System database and settings updated.");
    }

    // Refresh application state
    if (data.active_config && typeof applyConfigToUI === 'function') {
      applyConfigToUI(data.active_config);
      if (typeof recenterAndRedraw === 'function') {
        recenterAndRedraw(data.active_config.home, data.active_config.airport);
      }
    }
    if (typeof refreshEvents === 'function') {
      refreshEvents();
    }
    if (typeof fetchAndRenderAnalytics === 'function') {
      fetchAndRenderAnalytics();
    }

    setTimeout(() => {
      cancelMigrationUpload();
    }, 5000);

  } catch (err) {
    if (statusEl) {
      statusEl.style.background = 'rgba(239, 68, 68, 0.15)';
      statusEl.style.border = '1px solid rgba(239, 68, 68, 0.4)';
      statusEl.style.color = '#fca5a5';
      statusEl.textContent = `❌ Network Error: ${err.message}`;
    }
    if (restoreBtn) {
      restoreBtn.disabled = false;
      restoreBtn.textContent = "Confirm & Restore";
    }
  }
}
