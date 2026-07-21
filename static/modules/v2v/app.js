// V2V Module Frontend
// Handles folder upload, compare, summary cards, detail tabs with drill-down

const V2V_TABLE_DEFS = {
  bom: {name: 'BOM Snapshot', cat: 'input'},
  fcst: {name: 'FCST', cat: 'input'},
  supply: {name: 'Supply', cat: 'input'},
  switch: {name: 'Switch Matrix', cat: 'input'},
  item: {name: 'Item Master', cat: 'input'},
  line: {name: 'Line Master', cat: 'input'},
  calendar: {name: 'Line Calendar', cat: 'input'},
  plan_config: {name: 'Plan Config', cat: 'input'},
  plan_input: {name: 'Plan Input', cat: 'output'},
  plan_output: {name: 'Plan Output', cat: 'output'},
  balance: {name: 'BOH', cat: 'output'},
};

let v2vState = {
  jobId: null,
  versionA: null,
  versionB: null,
  summary: {},
  diffs: {},
  activeTable: 'bom',
  granularity: 'week',
  currentPage: 1,
  breadcrumbs: [{label: 'All', granularity: 'week', filters: {}}],
  filters: {changeType: 'ALL'}
};

function v2vInit() {
  console.log('V2V Init');
  setupV2VUpload();
  setupV2VGranularity();
  setupV2VServerVersions();
  setupV2VFilters();
  // Load table defs from server (optional)
  fetch('/v2v/templates/schema').then(r=>r.json()).then(data=>{
    console.log('V2V schema loaded', Object.keys(data).length);
  }).catch(()=>{});
}

function setupV2VUpload() {
  console.log('setupV2VUpload called');
  const inputA = document.getElementById('v2v-files-a');
  const inputB = document.getElementById('v2v-files-b');
  const statusEl = document.getElementById('v2v-status');

  if (!inputA || !inputB) {
    console.error('File inputs not found!', inputA, inputB);
    return;
  }

  function handleFiles(input, version) {
    console.log(`handleFiles called for ${version}, files:`, input.files ? input.files.length : 'null');
    try {
      const files = input.files;
      if (!files || files.length === 0) {
        console.warn(`No files selected for ${version}`);
        const statusEl = document.getElementById('v2v-status');
        if (statusEl) statusEl.innerHTML = `<div class="v2v-status warn">⚠️ Version ${version}: No files detected. Please select a folder containing xlsx files.</div>`;
        return;
      }
      
      const card = document.getElementById(`v2v-card-${version.toLowerCase()}`);
      const listEl = document.getElementById(`v2v-list-${version.toLowerCase()}`);
      const badge = document.getElementById(`v2v-badge-${version.toLowerCase()}`);
      const nameEl = document.getElementById(`v2v-name-${version.toLowerCase()}`);

      // Extract folder name from first file
      let folderName = 'Version ' + version;
      if (files[0].webkitRelativePath) {
        folderName = files[0].webkitRelativePath.split('/')[0];
      } else if (files[0].name) {
        // Fallback: use file name without extension or try to get folder
        folderName = 'Folder-' + version + ` (${files.length} files)`;
      }
      console.log(`Folder name for ${version}:`, folderName);
      if (nameEl) nameEl.textContent = `📁 ${folderName} - Click to reselect`;

      // Identify tables
      let identified = {};
      let fileListHtml = '';
      let xlsxCount = 0;
      for (let i=0; i<files.length; i++) {
        const f = files[i];
        const fname = f.name;
        if (!fname.toLowerCase().endsWith('.xlsx') || fname.startsWith('~$')) continue;
        xlsxCount++;
        const lower = fname.toLowerCase();
        let table = 'unknown';
        if (lower.includes('bom')) table = 'bom';
        else if (lower.includes('fcst') && lower.includes('主表')) table = 'fcst';
        else if (lower.includes('fcst') && lower.includes('明细')) table = 'fcst_detail';
        else if (lower.includes('实际值') || lower.includes('actual')) table = 'actual_io';
        else if (lower.includes('supply') || lower.includes('供应')) table = 'supply';
        else if (lower.includes('切换矩阵')) table = 'switch';
        else if (lower.includes('料号快照')) table = 'item';
        else if (lower.includes('线体日历')) table = 'calendar';
        else if (lower.includes('线体快照')) table = 'line';
        else if (lower.includes('计划设置')) table = 'plan_config';
        else if (lower.includes('排产结果')) table = 'plan_output';
        else if (lower.includes('结存')) table = 'balance';

        if (table !== 'unknown') identified[table] = fname;
        
        const sizeKB = (f.size/1024).toFixed(0);
        fileListHtml += `<div class="v2v-file-item ${table!=='unknown'?'ok':''}"><span>${table!=='unknown'?'✓':''} ${fname} -> ${table}</span><span class="file-size">${sizeKB}KB</span></div>`;
      }

      console.log(`Version ${version} identified:`, identified, `xlsxCount: ${xlsxCount}`);

      if (xlsxCount === 0) {
        fileListHtml = `<div style="color:#dc2626;padding:10px">❌ No xlsx files found in selected folder. Please select a folder containing the 12 xlsx files.<br>Found ${files.length} files but 0 xlsx.<br>Check: ${Array.from(files).slice(0,5).map(f=>f.name).join(', ')}</div>`;
        if (listEl) listEl.innerHTML = fileListHtml;
        if (badge) {
          badge.textContent = `0 xlsx - Error`;
          badge.className = 'v2v-version-badge error';
        }
        return;
      }

      if (listEl) listEl.innerHTML = fileListHtml;
      if (badge) {
        badge.textContent = `${Object.keys(identified).length}/12 tables, ${xlsxCount} xlsx`;
        badge.className = 'v2v-version-badge success';
      }
      if (card) {
        card.classList.add('has-files');
        card.classList.remove('error');
      }

      // Store
      if (version === 'A') {
        v2vState.versionA = {name: folderName, files: files, identified};
      } else {
        v2vState.versionB = {name: folderName, files: files, identified};
      }

      console.log(`Stored version ${version}:`, folderName, 'identified count', Object.keys(identified).length);
      updateCompareButton();

      const statusEl = document.getElementById('v2v-status');
      if (statusEl) {
        statusEl.innerHTML = `<div class="v2v-status info">✅ Version ${version} (${folderName}) loaded: ${xlsxCount} xlsx, ${Object.keys(identified).length} recognized. ${v2vState.versionA && v2vState.versionB ? 'Ready to compare!' : 'Please select the other version'}</div>`;
      }

      // Reset input value to allow re-selecting same folder
      // Don't reset immediately, user may need files for upload
    } catch(err) {
      console.error(`Error in handleFiles ${version}:`, err);
      const statusEl = document.getElementById('v2v-status');
      if (statusEl) statusEl.innerHTML = `<div class="v2v-status error">❌ Error loading Version ${version}: ${err.message}</div>`;
    }
  }

  // Fix: remove old listeners and add new with capture
  inputA.addEventListener('change', (e) => {
    console.log('inputA change event fired', e.target.files.length);
    handleFiles(inputA, 'A');
  });
  inputB.addEventListener('change', (e) => {
    console.log('inputB change event fired', e.target.files.length);
    handleFiles(inputB, 'B');
  });

  // Also listen to input event for some browsers
  inputA.addEventListener('input', () => {
    if (inputA.files && inputA.files.length > 0) handleFiles(inputA, 'A');
  });
  inputB.addEventListener('input', () => {
    if (inputB.files && inputB.files.length > 0) handleFiles(inputB, 'B');
  });

  // Make cards clickable to trigger file input (already button does, but card click also)
  ['v2v-card-a', 'v2v-card-b'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const version = id.includes('-a') ? 'A' : 'B';
    const input = version === 'A' ? inputA : inputB;
    el.addEventListener('click', (e) => {
      // Don't trigger if clicking inside file list or button
      if (e.target.closest('button') || e.target.closest('input')) return;
      console.log(`Card ${version} clicked, triggering file input`);
      input.click();
    });
    el.addEventListener('dragover', (e)=>{ e.preventDefault(); el.style.borderColor='#0f172a'; el.style.background='#f0fdf4'; });
    el.addEventListener('dragleave', ()=>{ el.style.borderColor=''; el.style.background=''; });
    el.addEventListener('drop', (e)=>{
      e.preventDefault();
      el.style.borderColor='';
      el.style.background='';
      console.log(`Drop on ${version}`, e.dataTransfer.files.length);
      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        // For drop, we need to handle folder drop? Browser may not support folder drop with files
        // Create a DataTransfer to assign? For simplicity, show message
        const statusEl = document.getElementById('v2v-status');
        if (statusEl) {
          statusEl.innerHTML = `<div class="v2v-status warn">⚠️ Drag & drop folder may not work in all browsers. Please use the 📁 button to select folder.</div>`;
        }
      }
    });
  });

  console.log('setupV2VUpload completed');
}

function updateCompareButton() {
  const btn = document.getElementById('v2v-btn-compare');
  if (!btn) return;
  if (v2vState.versionA && v2vState.versionB) {
    btn.disabled = false;
    btn.textContent = `▶ Compare ${v2vState.versionA.name} vs ${v2vState.versionB.name}`;
  } else {
    btn.disabled = true;
    btn.textContent = '▶ Compare (Need A & B)';
  }
}

function setupV2VGranularity() {
  document.querySelectorAll('.v2v-granularity-toggle button').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      document.querySelectorAll('.v2v-granularity-toggle button').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      v2vState.granularity = btn.dataset.granularity;
      if (v2vState.jobId) {
        loadV2VDetail(v2vState.activeTable);
      }
    });
  });
}

function setupV2VFilters() {
  const changeSel = document.getElementById('v2v-filter-changetype');
  if (changeSel) {
    changeSel.addEventListener('change', ()=>{
      v2vState.filters.changeType = changeSel.value;
      v2vState.currentPage = 1;
      if (v2vState.jobId) loadV2VDetail(v2vState.activeTable);
    });
  }
  const searchInput = document.getElementById('v2v-search');
  if (searchInput) {
    let timeout;
    searchInput.addEventListener('input', ()=>{
      clearTimeout(timeout);
      timeout = setTimeout(()=>{
        console.log('Search:', searchInput.value);
      }, 300);
    });
  }
  const dlBtn = document.getElementById('v2v-btn-download');
  if (dlBtn) {
    dlBtn.addEventListener('click', async ()=>{
      await downloadV2VCurrentView();
    });
  }
  const exportHtmlBtn = document.getElementById('v2v-btn-export-html');
  if (exportHtmlBtn) {
    exportHtmlBtn.addEventListener('click', async ()=>{
      await exportV2VHtmlReport();
    });
  }
  const cumCb = document.getElementById('v2v-cum');
  if (cumCb) {
    cumCb.addEventListener('change', ()=>{
      if (v2vState.outputQuery) {
        v2vState.outputQuery.cum = cumCb.checked;
      } else {
        v2vState.outputQuery = {cum: cumCb.checked, group_by: getV2VGroupBy(), only_diff: true, granularity: v2vState.granularity};
      }
      v2vState.currentPage = 1;
      if (v2vState.jobId) loadV2VDetail(v2vState.activeTable);
    });
  }
}

async function downloadV2VCurrentView() {
  if (!v2vState.jobId) {
    alert('No comparison job yet');
    return;
  }
  const btn = document.getElementById('v2v-btn-download');
  const origText = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Downloading...'; }

  try {
    const payload = {
      job_id: v2vState.jobId,
      table: v2vState.activeTable,
      granularity: v2vState.granularity,
      filters: {}
    };
    // Add output query if present
    if (v2vState.outputQuery) {
      payload.group_by = v2vState.outputQuery.group_by;
      payload.only_diff = v2vState.outputQuery.only_diff;
      payload.threshold_abs = v2vState.outputQuery.threshold_abs;
      payload.granularity = v2vState.outputQuery.granularity || v2vState.granularity;
    }
    // Add breadcrumb filters
    const lastCrumb = v2vState.breadcrumbs[v2vState.breadcrumbs.length-1];
    if (lastCrumb && lastCrumb.filters) {
      payload.filters = {...payload.filters, ...lastCrumb.filters};
    }
    // Add change type
    payload.change_type = v2vState.filters.changeType || 'ALL';

    const resp = await fetch('/v2v/api/download/current_view', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.error || `HTTP ${resp.status}`);
    }
    const blob = await resp.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `V2V_${payload.table}_${v2vState.jobId.slice(0,6)}.xlsx`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch(e) {
    alert('Download failed: ' + e.message);
    console.error(e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = origText || '📥 Download Current View'; }
  }
}

async function exportV2VHtmlReport() {
  if (!v2vState.jobId) {
    alert('No comparison job yet, please compare first');
    return;
  }
  const btn = document.getElementById('v2v-btn-export-html');
  const origText = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Exporting HTML...'; }

  try {
    // Try to get current V2V tab HTML for full UI export
    const v2vModule = document.getElementById('module-v2v');
    const v2vHtml = v2vModule ? v2vModule.outerHTML : document.body.innerHTML;

    // Fetch CSS for inlining (global + v2v)
    let globalCss = '', v2vCss = '', planMergeCss = '';
    try {
      const resp1 = await fetch('/static/global/style.css');
      globalCss = await resp1.text();
    } catch(e) { console.log('Failed to fetch global css', e); }
    try {
      const resp2 = await fetch('/static/modules/v2v/style.css');
      v2vCss = await resp2.text();
    } catch(e) { console.log('Failed to fetch v2v css', e); }
    try {
      const resp3 = await fetch('/static/modules/plan_merge/style.css');
      planMergeCss = await resp3.text();
    } catch(e) {}

    // Get current comparison data for embedding
    let jobData = null;
    try {
      const jobResp = await fetch(`/v2v/api/job/${v2vState.jobId}`);
      jobData = await jobResp.json();
    } catch(e) { console.log('Failed to fetch job data', e); }

    const previousName = v2vState.versionA ? v2vState.versionA.name : 'Previous';
    const latestName = v2vState.versionB ? v2vState.versionB.name : 'Latest';
    const generatedAt = new Date().toLocaleString();

    // Build standalone HTML with embedded UI + data
    const fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V2V Comparison - ${esc(previousName)} vs ${esc(latestName)} - Full UI Export</title>
<style>
${globalCss}
${v2vCss}
${planMergeCss}
body { background: #f8fafc; padding: 20px; }
.export-header { background: #0f172a; color: white; padding: 16px; border-radius: 8px; margin-bottom: 20px; }
.export-header h1 { margin: 0; font-size: 20px; }
.export-header .meta { font-size: 12px; color: #94a3b8; margin-top: 8px; }
.v2v-section { margin-bottom: 20px; }
</style>
</head>
<body>
<div class="export-header">
<h1>🔍 V2V Comparison - Full UI Export</h1>
<div class="meta">
<div>Previous Version: ${esc(previousName)} | Latest Version: ${esc(latestName)}</div>
<div>Generated: ${generatedAt} | Job ID: ${v2vState.jobId}</div>
<div>This is a standalone export of the V2V Comparison tab at time of export. Contains embedded UI and data.</div>
</div>
</div>

<div style="background:white;padding:16px;border-radius:8px;margin-bottom:20px;border:2px solid #0f172a">
<h3>📋 Embedded Comparison Data (JSON)</h3>
<p style="font-size:12px;color:#64748b">This section contains the raw comparison data used to generate the UI below. For developers.</p>
<pre style="background:#f8fafc;padding:12px;border-radius:4px;max-height:300px;overflow:auto;font-size:11px">${esc(JSON.stringify({jobId: v2vState.jobId, previous: previousName, latest: latestName, summary: jobData ? jobData.summary : {}, overall: jobData ? jobData.overall : {}}, null, 2))}</pre>
</div>

${v2vHtml}

<script>
// Embedded data for offline viewing
window.EMBEDDED_V2V_DATA = ${JSON.stringify({jobId: v2vState.jobId, previous: previousName, latest: latestName, jobData: jobData, v2vState: {activeTable: v2vState.activeTable, granularity: v2vState.granularity}}, null, 2)};
// Disable interactive elements that require server in exported version
document.addEventListener('DOMContentLoaded', () => {
  // Make all buttons that would call server show message
  const serverBtns = document.querySelectorAll('#v2v-btn-load-server, #v2v-btn-refresh');
  serverBtns.forEach(btn => {
    if (btn) {
      btn.disabled = true;
      btn.title = 'Disabled in exported HTML - this is a static snapshot';
      btn.style.opacity = '0.5';
    }
  });
  // Add banner
  const banner = document.createElement('div');
  banner.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#f59e0b;color:white;padding:8px;text-align:center;font-size:12px;z-index:10000';
  banner.textContent = '📄 This is an exported static snapshot of V2V Comparison tab at ' + new Date().toLocaleString() + ' - Some interactive features requiring server are disabled';
  document.body.prepend(banner);
});
</script>
</body>
</html>`;

    const blob = new Blob([fullHtml], {type: 'text/html'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `V2V_FullUI_${previousName}_vs_${latestName}_${new Date().toISOString().slice(0,10)}.html`.replace(/[^a-zA-Z0-9._-]/g, '_');
    a.click();
    URL.revokeObjectURL(a.href);

  } catch(e) {
    console.error('Export HTML failed, falling back to server export', e);
    // Fallback to server-side export
    try {
      const resp = await fetch('/v2v/api/export/html', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({job_id: v2vState.jobId})
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `V2V_Report_${v2vState.jobId.slice(0,6)}.html`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch(e2) {
      alert('Export HTML failed: ' + e2.message);
      console.error(e2);
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = origText || '📄 Export HTML Report'; }
  }
}

async function loadServerVersions() {
  const selA = document.getElementById('v2v-server-a');
  const selB = document.getElementById('v2v-server-b');
  const scanTimeEl = document.getElementById('v2v-scan-time');
  if (!selA || !selB) return;

  const prevA = selA.value;
  const prevB = selB.value;

  try {
    selA.innerHTML = '<option>Loading...</option>';
    selB.innerHTML = '<option>Loading...</option>';
    const resp = await fetch('/v2v/api/versions');
    const data = await resp.json();
    const versions = data.versions || [];
    const scannedAt = data.scanned_at ? `Last scan: ${new Date(data.scanned_at).toLocaleTimeString()}` : '';

    if (scanTimeEl) scanTimeEl.textContent = `${scannedAt} | Found ${versions.length} version folders`;

    selA.innerHTML = '<option value="">Select Previous Version</option>';
    selB.innerHTML = '<option value="">Select Latest Version</option>';
    versions.forEach(v=>{
      const optA = document.createElement('option');
      optA.value = v.path;
      optA.textContent = `${v.name} (${v.file_count} files, ${v.recognized} recog)`;
      if (v.path === prevA) optA.selected = true;
      selA.appendChild(optA);
      const optB = document.createElement('option');
      optB.value = v.path;
      optB.textContent = `${v.name} (${v.file_count} files, ${v.recognized} recog)`;
      if (v.path === prevB) optB.selected = true;
      selB.appendChild(optB);
    });

    // If new folder added and previously not selected, auto-select if only one new
    if (versions.length === 1) {
      selA.selectedIndex = 1;
    } else if (versions.length >= 2 && !prevA && !prevB) {
      // Auto select first two for convenience if nothing selected before
      // selA.selectedIndex = 1;
      // selB.selectedIndex = 2;
    }

    console.log(`Scanned ${versions.length} version folders:`, versions.map(v=>v.name));
    return versions;
  } catch(e) {
    console.log('Failed to load server versions', e);
    selA.innerHTML = '<option value="">Failed to load</option>';
    selB.innerHTML = '<option value="">Failed to load</option>';
    return [];
  }
}

function setupV2VServerVersions() {
  const loadBtn = document.getElementById('v2v-btn-load-server');
  if (loadBtn) {
    loadBtn.addEventListener('click', async ()=>{
      const selA = document.getElementById('v2v-server-a');
      const selB = document.getElementById('v2v-server-b');
      if (!selA || !selB) return;
      const aPath = selA.value;
      const bPath = selB.value;
      if (!aPath || !bPath) {
        alert('Please select both Previous and Latest versions');
        return;
      }
      if (aPath === bPath) {
        alert('Please select different versions');
        return;
      }
      await compareServerVersions(aPath, bPath);
    });
  }

  const refreshBtn = document.getElementById('v2v-btn-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async ()=>{
      refreshBtn.disabled = true;
      refreshBtn.textContent = '⏳ Scanning...';
      await loadServerVersions();
      refreshBtn.disabled = false;
      refreshBtn.textContent = '🔄 Refresh';
      const statusEl = document.getElementById('v2v-status');
      if (statusEl) statusEl.innerHTML = '<div class="v2v-status success">✅ Refreshed folder list. If you added new folder like 0721, it should now appear in dropdowns.</div>';
    });
  }

  // Load on init
  loadServerVersions();
}

async function compareServerVersions(aPath, bPath) {
  const statusEl = document.getElementById('v2v-status');
  const btn = document.getElementById('v2v-btn-load-server');
  if (statusEl) statusEl.innerHTML = '<div class="v2v-status info">⏳ Comparing server folders...</div>';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Comparing...'; }

  try {
    const resp = await fetch('/v2v/api/compare', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({a_path: aPath, b_path: bPath, granularity: v2vState.granularity})
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    handleCompareResult(data);
  } catch(e) {
    if (statusEl) statusEl.innerHTML = `<div class="v2v-status error">❌ ${e.message}</div>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '▶ Compare'; }
  }
}

document.addEventListener('DOMContentLoaded', ()=>{
  const btnCompare = document.getElementById('v2v-btn-compare');
  if (btnCompare) {
    btnCompare.addEventListener('click', async ()=>{
      if (!v2vState.versionA || !v2vState.versionB) {
        alert('Please select both Previous and Latest version folders');
        return;
      }
      await doV2VCompare();
    });
  }
});

async function doV2VCompare() {
  const statusEl = document.getElementById('v2v-status');
  const btn = document.getElementById('v2v-btn-compare');

  if (statusEl) statusEl.innerHTML = '<div class="v2v-status info">⏳ Uploading and comparing... This may take 10-30s for large files</div>';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Comparing...'; }

  try {
    const form = new FormData();
    // Append files_a and files_b
    for (let i=0; i<v2vState.versionA.files.length; i++) {
      form.append('files_a', v2vState.versionA.files[i]);
    }
    for (let i=0; i<v2vState.versionB.files.length; i++) {
      form.append('files_b', v2vState.versionB.files[i]);
    }
    form.append('granularity', v2vState.granularity);

    const resp = await fetch('/v2v/api/compare', {
      method: 'POST',
      body: form
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    
    handleCompareResult(data);

  } catch(e) {
    if (statusEl) statusEl.innerHTML = `<div class="v2v-status error">❌ Compare failed: ${e.message}</div>`;
    console.error(e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = `▶ Compare ${v2vState.versionA.name} vs ${v2vState.versionB.name}`; }
  }
}

function handleCompareResult(data) {
  console.log('Compare result', data);
  v2vState.jobId = data.job_id;
  v2vState.summary = data.summary || {};
  v2vState.diffs = data.diffs || {};
  
  const statusEl = document.getElementById('v2v-status');
  if (statusEl) {
    const overall = data.overall || {};
    statusEl.innerHTML = `<div class="v2v-status success">✅ Compare completed! Job: ${data.job_id} | Tables: ${Object.keys(data.summary).length} | Total Modified: ${overall.total_modified||0} | Added: ${overall.total_added||0} | Deleted: ${overall.total_deleted||0}</div>`;
  }

  // Show summary section
  const summarySection = document.getElementById('v2v-summary-section');
  if (summarySection) summarySection.style.display = 'block';

  // Render summary cards
  renderSummaryCards(data);

  // Show detail section
  const detailSection = document.getElementById('v2v-detail-section');
  if (detailSection) detailSection.style.display = 'block';

  // Render tabs
  renderDetailTabs(data);

  // Load first table detail
  const firstTable = Object.keys(data.summary)[0] || 'bom';
  v2vState.activeTable = firstTable;
  loadV2VDetail(firstTable);
}

function renderSummaryCards(data) {
  const grid = document.getElementById('v2v-summary-grid');
  if (!grid) return;
  
  let html = '';
  const summary = data.summary || {};
  
  // Sort: input tables first, then output, with diff count descending
  const sortedKeys = Object.keys(summary).sort((a,b)=>{
    const defA = V2V_TABLE_DEFS[a] || {cat:'input'};
    const defB = V2V_TABLE_DEFS[b] || {cat:'input'};
    if (defA.cat !== defB.cat) return defA.cat === 'input' ? -1 : 1;
    const modA = summary[a].modified||0 + summary[a].added||0 + summary[a].deleted||0;
    const modB = summary[b].modified||0 + summary[b].added||0 + summary[b].deleted||0;
    return modB - modA;
  });

  for (const key of sortedKeys) {
    const s = summary[key];
    const def = V2V_TABLE_DEFS[key] || {icon:'📄', name:key, cat:'input'};
    const totalDiff = (s.added||0) + (s.deleted||0) + (s.modified||0);
    const hasDiff = totalDiff > 0;
    
    html += `
      <div class="v2v-summary-card ${v2vState.activeTable===key?'active':''}" data-table="${key}" onclick="selectV2VTable('${key}')">
        <div class="v2v-summary-card-header">
          <span class="v2v-summary-card-title"><span class="v2v-summary-card-icon">${def.icon}</span> ${def.name}</span>
          <span class="v2v-summary-card-category ${def.cat}">${def.cat}</span>
        </div>
        <div class="v2v-summary-stats">
          <div class="v2v-stat-row"><span class="v2v-stat-label">Previous Version</span><span class="v2v-stat-value">${s.total_a||0} rows</span></div>
          <div class="v2v-stat-row"><span class="v2v-stat-label">Latest Version</span><span class="v2v-stat-value">${s.total_b||0} rows</span></div>
          <div style="height:1px;background:#f1f5f9;margin:4px 0"></div>
          <div class="v2v-stat-row"><span class="v2v-stat-label">Added</span><span class="v2v-stat-value add">+${s.added||0}</span></div>
          <div class="v2v-stat-row"><span class="v2v-stat-label">Deleted</span><span class="v2v-stat-value del">-${s.deleted||0}</span></div>
          <div class="v2v-stat-row"><span class="v2v-stat-label">Modified</span><span class="v2v-stat-value mod">${s.modified||0}</span></div>
          ${s.error?`<div style="font-size:11px;color:#dc2626;margin-top:4px">⚠️ ${s.error}</div>`:''}
          ${s.note?`<div style="font-size:11px;color:#64748b;margin-top:4px">${s.note}</div>`:''}
        </div>
        <div class="v2v-progress"><div class="v2v-progress-bar ${hasDiff?'has-diff':''}" style="width:${hasDiff?'100%':'0%'}"></div></div>
      </div>
    `;
  }

  grid.innerHTML = html;
}

function renderDetailTabs(data) {
  const tabsEl = document.getElementById('v2v-detail-tabs');
  if (!tabsEl) return;
  
  const summary = data.summary || {};
  // Group by Input/Output
  const groups = {input: [], output: []};
  for (const [key, s] of Object.entries(summary)) {
    if (key === 'actual_io') continue;
    const def = V2V_TABLE_DEFS[key] || {name:key, cat:'input'};
    const cat = def.cat || 'input';
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push([key, s]);
  }

  let html = '';

  // Input group - first row
  if (groups.input && groups.input.length > 0) {
    html += '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-bottom:8px"><span style="font-size:12px;font-weight:600;color:#0f172a;margin-right:8px;min-width:50px">Input:</span>';
    for (const [key, s] of groups.input) {
      const def = V2V_TABLE_DEFS[key] || {name:key};
      const totalDiff = (s.added||0)+(s.deleted||0)+(s.modified||0)+(s.inconsistent||0);
      const hasDiff = totalDiff>0;
      html += `<button class="v2v-detail-tab ${v2vState.activeTable===key?'active':''} ${hasDiff?'has-diff':''}" data-table="${key}" onclick="selectV2VTable('${key}')">${def.name} <span class="count-badge">${totalDiff}</span></button>`;
    }
    html += '</div>';
  }

  // Output group - second row
  if (groups.output && groups.output.length > 0) {
    html += '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px"><span style="font-size:12px;font-weight:600;color:#0f172a;margin-right:8px;min-width:50px">Output:</span>';
    for (const [key, s] of groups.output) {
      const def = V2V_TABLE_DEFS[key] || {name:key};
      const totalDiff = (s.added||0)+(s.deleted||0)+(s.modified||0);
      const hasDiff = totalDiff>0;
      html += `<button class="v2v-detail-tab ${v2vState.activeTable===key?'active':''} ${hasDiff?'has-diff':''}" data-table="${key}" onclick="selectV2VTable('${key}')">${def.name} <span class="count-badge">${totalDiff}</span></button>`;
    }
    html += '</div>';
  }

  tabsEl.innerHTML = html;
}

function selectV2VTable(tableName) {
  console.log('Card clicked:', tableName);
  v2vState.activeTable = tableName;
  v2vState.currentPage = 1;
  v2vState.breadcrumbs = [{label:'All', granularity:v2vState.granularity, filters:{}}];
  
  // Update active states
  document.querySelectorAll('.v2v-summary-card').forEach(c=> c.classList.toggle('active', c.dataset.table===tableName));
  document.querySelectorAll('.v2v-detail-tab').forEach(t=> t.classList.toggle('active', t.dataset.table===tableName));
  
  // Show/hide output builder for plan_output and balance
  updateV2VBuilderForTable(tableName);

  // Auto scroll to detail section
  const detailSection = document.getElementById('v2v-detail-section');
  if (detailSection) {
    setTimeout(()=> detailSection.scrollIntoView({behavior: 'smooth', block: 'start'}), 100);
  }

  loadV2VDetail(tableName);
}

function updateV2VBuilderForTable(tableName) {
  const builder = document.getElementById('v2v-output-builder');
  const detailedSection = document.getElementById('v2v-plan-output-detailed');
  if (!builder) return;
  // Per user request 2026-07-21: Dimension Builder looks messy for BOH, dimension switching already at top, so always hide builder
  builder.style.display = 'none';
  // Only show detailed matrix for plan_output, hide for others
  if (detailedSection) {
    if (tableName === 'plan_output') {
      detailedSection.style.display = 'block';
    } else {
      detailedSection.style.display = 'none';
    }
  }
}

function getV2VGroupBy() {
  const cbs = document.querySelectorAll('.v2v-groupby-cb:checked');
  if (cbs.length === 0) return null;
  return Array.from(cbs).map(cb=>cb.value).join(',');
}

function applyV2VOutputQuery() {
  // Collect from builder
  const groupBy = getV2VGroupBy();
  const granBtn = document.querySelector('#v2v-output-granularity button.active');
  const granularity = granBtn ? granBtn.dataset.granularity : v2vState.granularity;
  const onlyDiff = document.getElementById('v2v-only-diff') ? document.getElementById('v2v-only-diff').checked : true;
  const cum = document.getElementById('v2v-cum') ? document.getElementById('v2v-cum').checked : true;
  const threshAbs = document.getElementById('v2v-threshold-abs') ? document.getElementById('v2v-threshold-abs').value : '0';

  v2vState.granularity = granularity;
  v2vState.currentPage = 1;
  // Store in state for loadV2VDetail to use
  v2vState.outputQuery = {group_by: groupBy, only_diff: onlyDiff, threshold_abs: threshAbs, granularity: granularity, cum: cum};

  loadV2VDetail(v2vState.activeTable);
}

function resetV2VOutputQuery() {
  v2vState.outputQuery = null;
  v2vState.granularity = 'week';
  document.querySelectorAll('#v2v-output-granularity button').forEach(b=>b.classList.remove('active'));
  const weekBtn = document.querySelector('#v2v-output-granularity button[data-granularity="week"]');
  if (weekBtn) weekBtn.classList.add('active');
  if (document.getElementById('v2v-only-diff')) document.getElementById('v2v-only-diff').checked = true;
  if (document.getElementById('v2v-cum')) document.getElementById('v2v-cum').checked = true;
  if (document.getElementById('v2v-threshold-abs')) document.getElementById('v2v-threshold-abs').value = '0';
  loadV2VDetail(v2vState.activeTable);
}

function setV2VQuickQuery(type) {
  // type: line_week, sku_week, line_sku_week, item_week
  if (type === 'line_week') {
    // LINE_CODE + week
    document.querySelectorAll('.v2v-groupby-cb').forEach(cb=>{ cb.checked = (cb.value==='LINE_CODE'); });
    setGranularityUI('week');
  } else if (type === 'sku_week') {
    document.querySelectorAll('.v2v-groupby-cb').forEach(cb=>{ cb.checked = (cb.value==='SKU'); });
    setGranularityUI('week');
  } else if (type === 'line_sku_week') {
    document.querySelectorAll('.v2v-groupby-cb').forEach(cb=>{ cb.checked = (cb.value==='LINE_CODE' || cb.value==='SKU'); });
    setGranularityUI('week');
  } else if (type === 'item_week') {
    document.querySelectorAll('.v2v-groupby-cb').forEach(cb=>{ cb.checked = (cb.value==='ITEM_CODE'); });
    setGranularityUI('week');
  }
  applyV2VOutputQuery();
}

function setGranularityUI(gran) {
  v2vState.granularity = gran;
  document.querySelectorAll('#v2v-output-granularity button').forEach(b=> b.classList.toggle('active', b.dataset.granularity===gran));
  document.querySelectorAll('.v2v-granularity-toggle button').forEach(b=> b.classList.toggle('active', b.dataset.granularity===gran));
}

async function loadV2VDetail(tableName) {
  const wrapper = document.getElementById('v2v-detail-content');
  if (!wrapper) return;
  
  wrapper.innerHTML = '<div class="v2v-loading"><div class="v2v-spinner"></div>Loading diff for '+tableName+'... (may take 5-15s for large tables)</div>';
  
  try {
    const params = new URLSearchParams({
      job_id: v2vState.jobId,
      granularity: v2vState.granularity,
      change_type: v2vState.filters.changeType || 'ALL',
      page: v2vState.currentPage,
      page_size: 100
    });

    // Add output query params if present (Phase3 refined)
    if ((tableName === 'plan_output' || tableName === 'balance' || tableName === 'plan_input') && v2vState.outputQuery) {
      if (v2vState.outputQuery.group_by) params.append('group_by', v2vState.outputQuery.group_by);
      params.append('only_diff', v2vState.outputQuery.only_diff ? 'true' : 'false');
      if (v2vState.outputQuery.threshold_abs) params.append('threshold_abs', v2vState.outputQuery.threshold_abs);
      if (v2vState.outputQuery.threshold_pct) params.append('threshold_pct', v2vState.outputQuery.threshold_pct);
      if (v2vState.outputQuery.cum !== undefined) params.append('cum', v2vState.outputQuery.cum ? 'true' : 'false');
      // Override granularity from output query
      if (v2vState.outputQuery.granularity) params.set('granularity', v2vState.outputQuery.granularity);
    }
    
    // Add breadcrumb filters
    const lastCrumb = v2vState.breadcrumbs[v2vState.breadcrumbs.length-1];
    if (lastCrumb && lastCrumb.filters) {
      for (const [k,v] of Object.entries(lastCrumb.filters)) {
        if (v) params.append(k, v);
      }
    }

    const resp = await fetch(`/v2v/api/diff/${tableName}?${params}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    
    renderV2VTableDetail(data, tableName);
    renderV2VBreadcrumb();
    
  } catch(e) {
    wrapper.innerHTML = `<div class="v2v-status error">❌ Failed to load: ${e.message}</div>`;
  }
}

function renderTimeHorizontal(records, tableName, rowKeyFn, timeKeyFn, valueFn) {
  // Generic time-horizontal renderer: rows = rowKey, cols = time, cell = diff
  try {
    const allTimesSet = new Set();
    const rowsMap = new Map(); // rowKey -> Map(time -> rec)

    for (const rec of records) {
      const rowKey = rowKeyFn(rec) || 'Unknown';
      const timeKey = timeKeyFn(rec) || '';
      if (!timeKey) continue;
      allTimesSet.add(timeKey);
      if (!rowsMap.has(rowKey)) rowsMap.set(rowKey, new Map());
      rowsMap.get(rowKey).set(timeKey, rec);
    }

    const allTimes = Array.from(allTimesSet).sort();
    const rowKeys = Array.from(rowsMap.keys()).sort();

    if (rowKeys.length === 0 || allTimes.length === 0) {
      // Fallback to vertical if cannot pivot
      return null;
    }

    let html = `<div style="font-size:12px;color:#64748b;margin-bottom:8px">Time Horizontal: ${rowKeys.length} rows × ${allTimes.length} time buckets | Rows: ${tableName} key | Columns: Time (Month→Week→Daily→Shift order) | Values: Diff (A/B) | Change Type: <span class="v2v-change-badge add">ADD</span> <span class="v2v-change-badge del">DEL</span> <span class="v2v-change-badge mod">MODIFY</span></div>`;
    html += '<div class="v2v-table-wrapper" style="max-height:500px"><table class="v2v-table"><thead><tr>';
    html += '<th style="min-width:180px;left:0;position:sticky;z-index:20;background:#1e293b">Row / Time (SKU Level)</th>';
    for (const t of allTimes) {
      html += `<th style="min-width:100px;font-size:11px">${esc(t.slice(0,10))}</th>`;
    }
    html += '</tr></thead><tbody>';

    for (const rowKey of rowKeys.slice(0,200)) { // limit 200 rows
      html += `<tr><td style="left:0;position:sticky;background:white;z-index:10;font-weight:600;min-width:180px" class="frozen">${esc(rowKey)}</td>`;
      const timeMap = rowsMap.get(rowKey);
      for (const t of allTimes) {
        const rec = timeMap.get(t);
        if (!rec) {
          html += '<td style="background:#f8fafc"></td>';
        } else {
          // Compute diff if not present
          let diff = rec.diff;
          if (diff === undefined || diff === null) diff = rec.delta;
          if (diff === undefined || diff === null) {
            const aVal = rec.value_a ?? rec.PLAN_VALUE_A ?? rec.ACTUALWEEKVALUE_A ?? rec.BALANCE_QTY_A ?? rec.ACTUALWEEKVALUE_A ?? 0;
            const bVal = rec.value_b ?? rec.PLAN_VALUE_B ?? rec.ACTUALWEEKVALUE_B ?? rec.BALANCE_QTY_B ?? 0;
            // Handle null/undefined
            const aNum = (aVal === null || aVal === undefined || isNaN(aVal)) ? 0 : Number(aVal);
            const bNum = (bVal === null || bVal === undefined || isNaN(bVal)) ? 0 : Number(bVal);
            diff = bNum - aNum;
          }
          const a = rec.value_a ?? rec.PLAN_VALUE_A ?? rec.ACTUALWEEKVALUE_A ?? rec.BALANCE_QTY_A ?? rec.ACTUALWEEKVALUE_A ?? rec.A ?? 0;
          const b = rec.value_b ?? rec.PLAN_VALUE_B ?? rec.ACTUALWEEKVALUE_B ?? rec.BALANCE_QTY_B ?? rec.ACTUALWEEKVALUE_B ?? rec.B ?? 0;
          const aNum = (a === null || a === undefined || isNaN(a)) ? 0 : a;
          const bNum = (b === null || b === undefined || isNaN(b)) ? 0 : b;
          const ct = rec.change_type || (diff !== 0 ? (aNum===0 ? 'ADD' : bNum===0 ? 'DEL' : 'MODIFY') : 'UNCHANGED');
          const ctLower = ct.includes('ADD') ? 'add' : ct.includes('DEL') ? 'del' : 'mod';
          const cls = diff > 0 ? 'num-pos' : diff < 0 ? 'num-neg' : '';
          html += `<td class="data-cell ${cls}" style="font-size:11px;text-align:center;min-width:100px"><span class="v2v-change-badge ${ctLower}" style="font-size:9px">${ct}</span><br>${aNum}/${bNum}<br><small style="color:${diff>0?'#16a34a':diff<0?'#dc2626':'#64748b'}">${diff>0?'+':''}${diff}</small></td>`;
        }
      }
      html += '</tr>';
    }

    html += '</tbody></table></div>';
    if (rowKeys.length > 200) {
      html += `<div style="margin-top:8px;font-size:11px;color:#64748b">Showing first 200 of ${rowKeys.length} rows. Use search to filter.</div>`;
    }

    return html;
  } catch(e) {
    console.error('renderTimeHorizontal error', e);
    return null;
  }
}

function renderV2VTableDetail(data, tableName) {
  const wrapper = document.getElementById('v2v-detail-content');
  if (!wrapper) return;

  const records = data.records || [];
  const pagination = data.pagination || {};
  const def = V2V_TABLE_DEFS[tableName] || {name: tableName};

  if (records.length === 0) {
    let msg = data.message || `No differences for ${def.name}`;
    if (data.coverage) {
      msg += ` | Coverage A: ${data.coverage.date_range_a||''} vs B: ${data.coverage.date_range_b||''}`;
    }
    wrapper.innerHTML = `
      <div class="v2v-status success">✅ ${msg}</div>
      ${data.coverage ? `<div style="padding:8px;background:#f8fafc;border-radius:4px;margin:8px 0;font-size:12px">Coverage: A ${data.coverage.date_range_a} | B ${data.coverage.date_range_b} | Extra in B dates: ${data.coverage.extra_dates_in_b||0} | Missing: ${data.coverage.missing_dates_in_b||0}</div>` : ''}
      <div style="padding:12px;font-size:12px;color:#64748b">Summary: ${JSON.stringify(data.summary||{}, null, 2)}</div>
    `;
    return;
  }

  // Header with actions + special note for FCST
  let extraNote = '';
  if (tableName === 'fcst' && data.summary && data.summary.note) {
    extraNote = `<div style="background:#fffbeb;border:1px solid #fde68a;padding:8px;border-radius:4px;margin-bottom:8px;font-size:12px;color:#92400e">💡 ${esc(data.summary.note)}<br>Grouped view shows SKU×Week aggregated (1 detail edit may appear as 2 grouped modifies if 2 SKUs share same MAIN_ID).</div>`;
  }
  let html = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><div style="font-size:12px;color:#64748b">Showing ${records.length} of ${pagination.total||records.length} records | Page ${pagination.page||1} | Table: ${def.name} | Click card for detail, click row action for drill-down</div></div>`;
  html += extraNote;
  html += '<div class="v2v-table-wrapper"><table class="v2v-table"><thead><tr>';

  // Headers per table
  if (tableName === 'bom') {
    html += '<th>Change</th><th>Parent PN</th><th>Item No</th><th>Field</th><th>A</th><th>B</th>';
  } else if (tableName === 'fcst') {
    html += '<th>Change</th><th>SKU</th><th>Week</th><th>Field</th><th>A</th><th>B</th><th>Delta</th>';
  } else if (tableName === 'plan_config') {
    html += '<th>Field</th><th>A</th><th>B</th><th>Change</th>';
  } else if (tableName === 'actual_io') {
    // Will be removed per user request, but keep placeholder
    html += '<th>Change</th><th>Line</th><th>SKU</th><th>Date</th><th>Shift</th><th>Field</th><th>A</th><th>B</th><th>Delta</th>';
  } else if (tableName === 'supply') {
    const horiz = renderTimeHorizontal(records, tableName, 
      rec => (rec.key && rec.key.PN_CODE) ? rec.key.PN_CODE : rec.PN_CODE || 'Unknown',
      rec => (rec.key && (rec.key.WEEK || rec.key.KITTING_DATE || rec.key._MERGE_DATE)) ? (rec.key.WEEK || rec.key.KITTING_DATE || rec.key._MERGE_DATE) : (rec.WEEK || rec.KITTING_DATE || rec._MERGE_DATE || rec.ACTUALFIRSTDAYOFWEEK || ''),
      rec => rec
    );
    if (horiz) { wrapper.innerHTML = horiz; return; }
    html += '<th>Change</th><th>PN_CODE</th><th>Date/Week</th><th>Field</th><th>A</th><th>B</th><th>Delta</th>';
  } else if (tableName === 'switch') {
    html += '<th>Change</th><th>Line</th><th>Before PN</th><th>After PN</th><th>Field</th><th>A</th><th>B</th><th>Delta</th>';
  } else if (tableName === 'calendar') {
    const horiz = renderTimeHorizontal(records, tableName,
      rec => {
        const k = rec.key || {};
        return `${k.LINE_CODE||rec.LINE_CODE||''} | ${k.PLAN_TYPE||rec.PLAN_TYPE||''} | ${k.SHIFT_NAME||rec.SHIFT_NAME||''}`.replace(/^\s*\|\s*|\s*\|\s*$/g,'').trim() || 'Unknown';
      },
      rec => {
        const k = rec.key || {};
        return k.PLAN_DATE || k.WEEK || k._DATE_STR || rec.PLAN_DATE || rec.WEEK || rec._DATE_STR || '';
      },
      rec => rec
    );
    if (horiz) { wrapper.innerHTML = horiz; return; }
    html += '<th>Change</th><th>Line</th><th>Type</th><th>Date</th><th>Shift</th><th>Item</th><th>A</th><th>B</th><th>Delta</th>';
  } else if (tableName === 'item') {
    html += '<th>Change</th><th>Item No</th><th>Field</th><th>A</th><th>B</th>';
  } else if (tableName === 'line') {
    html += '<th>Change</th><th>Line Code</th><th>Field</th><th>A</th><th>B</th>';
  } else if (tableName === 'plan_output') {
    const horiz = renderTimeHorizontal(records, tableName,
      rec => {
        const gv = rec._group_values || rec.key || {};
        return Object.values(gv).filter(v=>v).join(' | ') || rec.LINE_CODE || rec.SKU || rec.PN_CODE || 'Unknown';
      },
      rec => rec._WEEK || rec._DATE || rec.WEEK || rec.ACTUALFIRSTDAYOFWEEK || '',
      rec => rec
    );
    if (horiz) { wrapper.innerHTML = horiz; return; }
    html += '<th>Time</th><th>Group</th><th>A Total</th><th>B Total</th><th>Diff</th><th>Diff%</th><th>Drill</th>';
  } else if (tableName === 'balance') {
    const horiz = renderTimeHorizontal(records, tableName,
      rec => {
        const gv = rec._group_values || {};
        const k = rec.key || {};
        return Object.values(gv).filter(v=>v).join(' | ') || k.ITEM_CODE || rec.ITEM_CODE || k.PN_CODE || 'Unknown';
      },
      rec => rec._WEEK || rec._DATE || rec.WEEK || (rec.key && rec.key.WEEK) || '',
      rec => rec
    );
    if (horiz) { wrapper.innerHTML = horiz; return; }
    html += '<th>Time</th><th>Group</th><th>A Balance</th><th>B Balance</th><th>Diff</th><th>Diff%/Neg</th><th>Drill</th>';
  } else if (tableName === 'plan_input') {
    const horiz = renderTimeHorizontal(records, tableName,
      rec => (rec.key && rec.key.PN_CODE) ? rec.key.PN_CODE : rec.PN_CODE || 'Unknown',
      rec => (rec.key && rec.key.WEEK) ? rec.key.WEEK : rec.WEEK || rec.ACTUALFIRSTDAYOFWEEK || '',
      rec => rec
    );
    if (horiz) { wrapper.innerHTML = horiz; return; }
    html += '<th>Time</th><th>SKU/PN</th><th>A FCST</th><th>B FCST</th><th>Diff</th><th>Diff%</th><th>Drill</th>';
  } else if (tableName === 'fcst') {
    const horiz = renderTimeHorizontal(records, tableName,
      rec => (rec.key && rec.key.PN_CODE) ? rec.key.PN_CODE : rec.PN_CODE || rec.SKU || 'Unknown',
      rec => (rec.key && rec.key.WEEK) ? rec.key.WEEK : rec.WEEK || rec.ACTUALFIRSTDAYOFWEEK || '',
      rec => rec
    );
    if (horiz) { wrapper.innerHTML = horiz; return; }
    html += '<th>Change</th><th>SKU</th><th>Week</th><th>Field</th><th>A</th><th>B</th><th>Delta</th>';
  } else {
    const first = records[0];
    const keys = Object.keys(first).slice(0,8);
    for (const k of keys) html += `<th>${esc(k)}</th>`;
  }
  html += '</tr></thead><tbody>';

  for (const rec of records) {
    const ct = rec.change_type || 'MODIFY';
    const ctLower = ct.toLowerCase().includes('add') ? 'add' : ct.toLowerCase().includes('del') ? 'del' : ct.toLowerCase().includes('inconsistent') ? 'del' : 'mod';
    const badge = ct.includes('INCONSISTENT') ? 'INCONSISTENT' : ct;
    html += `<tr class="diff-${ctLower}">`;

    const key = rec.key || {};
    if (tableName === 'bom') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.PARENT_PN_CODE||rec.PARENT_PN_CODE||'')}</td>`;
      html += `<td>${esc(key.ITEM_NO||rec.ITEM_NO||'')}</td>`;
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${esc(rec.value_a||rec.UNIT_NUM_A||'')}</td>`;
      html += `<td>${esc(rec.value_b||rec.UNIT_NUM_B||'')}</td>`;
    } else if (tableName === 'fcst') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.PN_CODE||rec.PN_CODE||rec.SKU||'')}</td>`;
      html += `<td>${esc(key.WEEK||rec.WEEK||rec.ACTUALFIRSTDAYOFWEEK||'')}</td>`;
      html += `<td>${esc(rec.field||'ACTUALWEEKVALUE')}</td>`;
      html += `<td>${rec.value_a||rec.ACTUALWEEKVALUE_A||0}</td>`;
      html += `<td>${rec.value_b||rec.ACTUALWEEKVALUE_B||0}</td>`;
      html += `<td style="${(rec.delta||rec.diff||0)>0?'color:#16a34a':(rec.delta||rec.diff||0)<0?'color:#dc2626':''}">${rec.delta||rec.diff||''}</td>`;
    } else if (tableName === 'plan_config') {
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${esc(rec.value_a||'')}</td>`;
      html += `<td>${esc(rec.value_b||'')}</td>`;
      html += `<td><span class="v2v-change-badge mod">MODIFY</span></td>`;
    } else if (tableName === 'actual_io') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.LINE_CODE||rec.LINE_CODE||'')}</td>`;
      html += `<td>${esc(key.SKU||rec.SKU||'')}</td>`;
      html += `<td>${esc(key.PLAN_DATE||key._MERGE_DATE||rec.PLAN_DATE||rec._MERGE_DATE||'')}</td>`;
      html += `<td>${esc(key.SHIFT_NAME||rec.SHIFT_NAME||'')}</td>`;
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${rec.value_a||rec.PLAN_VALUE_A||''}</td>`;
      html += `<td>${rec.value_b||rec.PLAN_VALUE_B||''}</td>`;
      html += `<td style="${(rec.delta||rec.diff||0)>0?'color:#16a34a':(rec.delta||rec.diff||0)<0?'color:#dc2626':''}">${rec.delta||rec.diff||''}</td>`;
    } else if (tableName === 'supply') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.PN_CODE||rec.PN_CODE||'')}</td>`;
      html += `<td>${esc(key.KITTING_DATE||key.WEEK||key._MERGE_DATE||rec.KITTING_DATE||rec.WEEK||rec.ACTUALFIRSTDAYOFWEEK||'')}<br><small>${key.GRANULARITY||rec.GRANULARITY||''}</small></td>`;
      html += `<td>${esc(rec.field||'KITTING_VALUE')}</td>`;
      html += `<td>${rec.value_a||rec.KITTING_VALUE_A||rec.ACTUALWEEKVALUE_A||''}</td>`;
      html += `<td>${rec.value_b||rec.KITTING_VALUE_B||rec.ACTUALWEEKVALUE_B||''}</td>`;
      html += `<td style="${(rec.delta||rec.diff||0)>0?'color:#16a34a':(rec.delta||rec.diff||0)<0?'color:#dc2626':''}">${rec.delta||rec.diff||''}</td>`;
    } else if (tableName === 'switch') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.LINE_CODE||rec.LINE_CODE||'')}</td>`;
      html += `<td>${esc(key.BEFORE_PN_CODE||key.BEFORE||rec.BEFORE_PN_CODE||'')}</td>`;
      html += `<td>${esc(key.AFTER_PN_CODE||key.AFTER||rec.AFTER_PN_CODE||'')}</td>`;
      html += `<td>${esc(rec.field||'SWITCH_DURATION')}</td>`;
      html += `<td>${rec.value_a||rec.SWITCH_DURATION_A||''}</td>`;
      html += `<td>${rec.value_b||rec.SWITCH_DURATION_B||''}</td>`;
      html += `<td>${rec.delta||rec.diff||''}</td>`;
    } else if (tableName === 'calendar') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.LINE_CODE||rec.LINE_CODE||'')}</td>`;
      html += `<td>${esc(key.PLAN_TYPE||rec.PLAN_TYPE||'')}</td>`;
      html += `<td>${esc(key.PLAN_DATE||key.WEEK||key._DATE_STR||key._WEEK_STR||rec.PLAN_DATE||rec.WEEK||'')}</td>`;
      html += `<td>${esc(key.SHIFT_NAME||rec.SHIFT_NAME||'')}</td>`;
      html += `<td>${esc(key.PLAN_ITEM||rec.PLAN_ITEM||'')}</td>`;
      html += `<td>${rec.value_a||rec.PLAN_VALUE_A||''}</td>`;
      html += `<td>${rec.value_b||rec.PLAN_VALUE_B||''}</td>`;
      html += `<td style="${(rec.delta||rec.diff||0)>0?'color:#16a34a':(rec.delta||rec.diff||0)<0?'color:#dc2626':''}">${rec.delta||rec.diff||''}</td>`;
    } else if (tableName === 'item' || tableName === 'line') {
      const keyName = tableName==='item'?'ITEM_NO':'LINE_CODE';
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key[keyName]||JSON.stringify(key))}</td>`;
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${esc(rec.value_a||'')}</td>`;
      html += `<td>${esc(rec.value_b||'')}</td>`;
    } else if (tableName === 'plan_output') {
      const groupVals = rec._group_values || key;
      html += `<td>${esc(rec._WEEK||rec._DATE||rec.LINE_CODE||'')}${rec.SHIFT_NAME? ' '+rec.SHIFT_NAME:''}</td>`;
      html += `<td>${Object.entries(groupVals).map(([k,v])=>`<div><small>${k}:</small> ${esc(v||'')}</div>`).join('')}</td>`;
      html += `<td>${rec.PLAN_VALUE_A||0}</td>`;
      html += `<td>${rec.PLAN_VALUE_B||0}</td>`;
      html += `<td style="${(rec.diff||0)>0?'color:#16a34a':(rec.diff||0)<0?'color:#dc2626':''};font-weight:600">${rec.diff||0}</td>`;
      html += `<td>${rec.diff_pct? rec.diff_pct.toFixed(1)+'%':''}</td>`;
      const drill = rec._drill || {};
      let drillBtn = '';
      if (drill.can_drill_day || drill.can_drill_shift) {
        const nextGran = drill.next_granularity || 'day';
        drillBtn = `<button class="v2v-drill-btn" onclick="drillDownOutput('${nextGran}', ${JSON.stringify(groupVals).replace(/"/g,'&quot;')})">▶ ${nextGran}</button>`;
      }
      html += `<td>${drillBtn}</td>`;
    } else if (tableName === 'balance') {
      const groupVals = rec._group_values || key;
      html += `<td>${esc(rec._WEEK||rec._DATE||rec.ITEM_CODE||'')}</td>`;
      html += `<td>${Object.entries(groupVals).map(([k,v])=>`<div><small>${k}:</small> ${esc(v||'')}</div>`).join('')}</td>`;
      const displayA = rec.BALANCE_QTY_A !== undefined ? rec.BALANCE_QTY_A : (rec[rec.compare_field+'_A']||rec.PLAN_VALUE_A||0);
      const displayB = rec.BALANCE_QTY_B !== undefined ? rec.BALANCE_QTY_B : (rec[rec.compare_field+'_B']||rec.PLAN_VALUE_B||0);
      html += `<td>${displayA}</td>`;
      html += `<td>${displayB}</td>`;
      html += `<td style="${(rec.diff||0)>0?'color:#16a34a':(rec.diff||0)<0?'color:#dc2626':''};font-weight:600">${rec.diff||0}</td>`;
      html += `<td>${rec.diff_pct? rec.diff_pct.toFixed(1)+'%':''}${rec.is_negative? '<br><span style="color:#dc2626;font-weight:700">⚠️ Negative Stock</span>':''}</td>`;
      const drill = rec._drill || {};
      let drillBtn = '';
      if (drill.can_drill_day || drill.can_drill_shift) {
        const nextGran = drill.next_granularity || 'day';
        drillBtn = `<button class="v2v-drill-btn" onclick="drillDownOutput('${nextGran}', ${JSON.stringify(groupVals).replace(/"/g,'&quot;')})">▶ ${nextGran}</button>`;
      }
      html += `<td>${drillBtn}</td>`;
    } else if (tableName === 'plan_input') {
      const groupVals = rec._group_values || key;
      html += `<td>${esc(rec._WEEK||rec._MONTH||rec._DATE||rec.PN_CODE||rec.PN_CODE||'')}</td>`;
      html += `<td>${Object.entries(groupVals).map(([k,v])=>`<div><small>${k}:</small> ${esc(v||'')}</div>`).join('')}</td>`;
      html += `<td>${rec.ACTUALWEEKVALUE_A||rec.PLAN_VALUE_A||0}</td>`;
      html += `<td>${rec.ACTUALWEEKVALUE_B||rec.PLAN_VALUE_B||0}</td>`;
      html += `<td style="${(rec.diff||0)>0?'color:#16a34a':(rec.diff||0)<0?'color:#dc2626':''};font-weight:600">${rec.diff||0}</td>`;
      html += `<td>${rec.diff_pct? rec.diff_pct.toFixed(1)+'%':''}</td>`;
      const drill = rec._drill || {};
      let drillBtn = '';
      if (drill.can_drill_day) {
        drillBtn = `<button class="v2v-drill-btn" onclick="drillDownOutput('${drill.next_granularity}', ${JSON.stringify(groupVals).replace(/"/g,'&quot;')})">▶ ${drill.next_granularity}</button>`;
      }
      html += `<td>${drillBtn}</td>`;
    } else {
      for (const [k,v] of Object.entries(rec).slice(0,8)) {
        html += `<td>${esc(String(v||'').substring(0,100))}</td>`;
      }
    }
    html += '</tr>';
  }
  html += '</tbody></table></div>';

  if (pagination.total > pagination.page_size) {
    const totalPages = Math.ceil(pagination.total / pagination.page_size);
    html += `<div style="margin-top:12px;display:flex;gap:8px;align-items:center"><button class="btn btn-sm" ${pagination.page<=1?'disabled':''} onclick="v2vState.currentPage--; loadV2VDetail('${tableName}')">‹ Prev</button><span style="font-size:12px">${pagination.page} / ${totalPages} (Total ${pagination.total})</span><button class="btn btn-sm" ${pagination.page>=totalPages?'disabled':''} onclick="v2vState.currentPage++; loadV2VDetail('${tableName}')">Next ›</button></div>`;
  }

  wrapper.innerHTML = html;
}

function renderV2VBreadcrumb() {
  const el = document.getElementById('v2v-breadcrumb');
  if (!el) return;
  let html = '';
  v2vState.breadcrumbs.forEach((bc, idx)=>{
    if (idx>0) html += '<span class="v2v-breadcrumb-sep">›</span>';
    const isLast = idx===v2vState.breadcrumbs.length-1;
    html += `<span class="v2v-breadcrumb-item ${isLast?'active':''}" onclick="drillTo(${idx})">${bc.label} (${bc.granularity})</span>`;
  });
  el.innerHTML = html;
}

function drillTo(index) {
  // Drill back to breadcrumb index
  v2vState.breadcrumbs = v2vState.breadcrumbs.slice(0, index+1);
  const bc = v2vState.breadcrumbs[index];
  v2vState.granularity = bc.granularity;
  // Update toggle
  document.querySelectorAll('.v2v-granularity-toggle button').forEach(b=>b.classList.toggle('active', b.dataset.granularity===bc.granularity));
  document.querySelectorAll('#v2v-output-granularity button').forEach(b=>b.classList.toggle('active', b.dataset.granularity===bc.granularity));
  loadV2VDetail(v2vState.activeTable);
}

function drillDownOutput(nextGranularity, groupValues) {
  // groupValues is object like {LINE_CODE: 'AL6-Frame', _WEEK: '2026-07-12'}
  // Push breadcrumb
  const current = v2vState.breadcrumbs[v2vState.breadcrumbs.length-1];
  const labelParts = [];
  for (const [k,v] of Object.entries(groupValues)) {
    if (k.startsWith('_')) continue;
    if (v) labelParts.push(`${k}=${v}`);
  }
  const label = labelParts.join(', ') || `${nextGranularity}`;
  v2vState.breadcrumbs.push({
    label: label,
    granularity: nextGranularity,
    filters: {...(current.filters||{}), ...groupValues}
  });
  v2vState.granularity = nextGranularity;
  // Update UI toggles
  document.querySelectorAll('.v2v-granularity-toggle button').forEach(b=>b.classList.toggle('active', b.dataset.granularity===nextGranularity));
  document.querySelectorAll('#v2v-output-granularity button').forEach(b=>b.classList.toggle('active', b.dataset.granularity===nextGranularity));
  loadV2VDetail(v2vState.activeTable);
}

let v2vChartInstance = null;

function showV2VChart(tableName) {
  const cont = document.getElementById('v2v-chart-container');
  if (!cont) return;
  cont.style.display = cont.style.display === 'none' ? 'block' : 'none';
  if (cont.style.display === 'block') {
    loadV2VChart(tableName);
  }
}

async function loadV2VChart(tableName) {
  const keyInput = document.getElementById('v2v-chart-key');
  const keyVal = keyInput ? keyInput.value.trim() : '';
  const canvas = document.getElementById('v2v-chart');
  if (!canvas) return;

  const status = document.getElementById('v2v-status');
  // Build query
  let params = new URLSearchParams({job_id: v2vState.jobId});
  if (tableName === 'supply' && keyVal) params.append('pn_code', keyVal);
  if (tableName === 'calendar' && keyVal) params.append('line_code', keyVal);
  // For calendar, also try plan_type detection
  if (tableName === 'calendar') {
    params.append('plan_type', 'UPH');
  }
  if (tableName === 'actual_io' && keyVal) {
    // keyVal could be LINE_CODE
    if (keyVal.includes('-')) params.append('line_code', keyVal);
    else params.append('sku', keyVal);
  }

  try {
    const resp = await fetch(`/v2v/api/chart/${tableName}?${params}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);

    const dates = data.dates || [];
    const aVals = data.values_a || [];
    const bVals = data.values_b || [];

    if (v2vChartInstance) {
      v2vChartInstance.destroy();
    }

    const ctx = canvas.getContext('2d');
    v2vChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: dates,
        datasets: [
          {label: 'Previous (' + (v2vState.versionA?.name||'Prev') + ')', data: aVals, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', tension: 0.1},
          {label: 'Latest (' + (v2vState.versionB?.name||'Latest') + ')', data: bVals, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', tension: 0.1}
        ]
      },
      options: {
        responsive: true,
        interaction: {mode: 'index', intersect: false},
        plugins: {
          title: {display: true, text: `${tableName} - ${keyVal||'Aggregated'} Comparison`},
          legend: {position: 'top'}
        },
        scales: {
          x: {display: true, title: {display: true, text: 'Date'}},
          y: {display: true, title: {display: true, text: 'Value'}}
        }
      }
    });

  } catch(e) {
    console.error('Chart load failed', e);
    const cont = document.getElementById('v2v-chart-container');
    if (cont) cont.innerHTML += `<div class="v2v-status error">Chart failed: ${e.message}</div>`;
  }
}

function handleV2VRowChart(tableName, groupValues) {
  // groupValues is object like {PN_CODE: 'xxx'} or {LINE_CODE: '...'}
  console.log('Row chart click', tableName, groupValues);
  const cont = document.getElementById('v2v-chart-container');
  if (cont) cont.style.display = 'block';
  const keyInput = document.getElementById('v2v-chart-key');
  if (keyInput) {
    // Set input to key for user feedback
    if (groupValues.PN_CODE) keyInput.value = groupValues.PN_CODE;
    else if (groupValues.LINE_CODE) keyInput.value = groupValues.LINE_CODE;
    else if (groupValues.ITEM_CODE) keyInput.value = groupValues.ITEM_CODE;
    else if (groupValues.SKU) keyInput.value = groupValues.SKU;
    else keyInput.value = JSON.stringify(groupValues);
  }
  // Build params and load chart
  let params = new URLSearchParams({job_id: v2vState.jobId});
  if (tableName === 'supply' && groupValues.PN_CODE) params.append('pn_code', groupValues.PN_CODE);
  if (tableName === 'calendar') {
    if (groupValues.LINE_CODE) params.append('line_code', groupValues.LINE_CODE);
    if (groupValues.PLAN_TYPE) params.append('plan_type', groupValues.PLAN_TYPE);
  }
  if (tableName === 'actual_io') {
    if (groupValues.LINE_CODE) params.append('line_code', groupValues.LINE_CODE);
    if (groupValues.SKU) params.append('sku', groupValues.SKU);
  }
  if (tableName === 'plan_output') {
    if (groupValues.LINE_CODE) params.append('line_code', groupValues.LINE_CODE);
    if (groupValues.SKU) params.append('sku', groupValues.SKU);
    // granularity from current state
    params.append('granularity', v2vState.granularity);
  }
  if (tableName === 'balance') {
    if (groupValues.ITEM_CODE) params.append('item_code', groupValues.ITEM_CODE);
    params.append('granularity', v2vState.granularity);
  }
  if (tableName === 'plan_input') {
    if (groupValues.PN_CODE) params.append('pn_code', groupValues.PN_CODE);
    if (groupValues.SKU) params.append('pn_code', groupValues.SKU);
    params.append('granularity', v2vState.granularity);
  }

  // For plan_output/balance we need to pass filters via chart API? Our chart API for those uses filters via kwargs
  // We'll call /v2v/api/chart/<table>?job_id=...
  (async () => {
    try {
      const resp = await fetch(`/v2v/api/chart/${tableName}?${params}`);
      const data = await resp.json();
      if (data.error) throw new Error(data.error);
      const canvas = document.getElementById('v2v-chart');
      if (!canvas) return;
      if (v2vChartInstance) v2vChartInstance.destroy();
      const ctx = canvas.getContext('2d');
      v2vChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
          labels: data.dates || [],
          datasets: [
            {label: 'A', data: data.values_a || [], borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', tension: 0.1},
            {label: 'B', data: data.values_b || [], borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', tension: 0.1}
          ]
        },
        options: {
          responsive: true,
          interaction: {mode: 'index', intersect: false},
          plugins: {
            title: {display: true, text: `${tableName} - ${JSON.stringify(groupValues)}`},
            legend: {position: 'top'}
          },
          scales: {
            x: {display: true, title: {display: true, text: 'Date'}, ticks: {maxTicksLimit: 20}},
            y: {display: true, title: {display: true, text: 'Value'}}
          }
        }
      });
    } catch(e) {
      console.error('Row chart failed', e);
    }
  })();
}

async function loadPlanOutputMatrix() {
  const wrapper = document.getElementById('v2v-po-matrix-wrapper');
  const statusEl = document.getElementById('v2v-po-matrix-status');
  if (!wrapper) return;

  const skuPrefix = document.getElementById('v2v-po-sku-prefix') ? document.getElementById('v2v-po-sku-prefix').value : 'SK';
  const lineFilter = document.getElementById('v2v-po-line-filter') ? document.getElementById('v2v-po-line-filter').value : '';
  const exactSku = document.getElementById('v2v-po-exact-sku') ? document.getElementById('v2v-po-exact-sku').value.trim() : '';
  const granularity = document.getElementById('v2v-po-granularity') ? document.getElementById('v2v-po-granularity').value : 'day';
  const cum = document.getElementById('v2v-po-cum') ? document.getElementById('v2v-po-cum').checked : true;

  if (!v2vState.jobId) {
    if (statusEl) statusEl.innerHTML = '<span style="color:#dc2626">No job, please compare first</span>';
    return;
  }

  wrapper.innerHTML = '<div class="v2v-loading"><div class="v2v-spinner"></div>Loading detailed matrix... (may take 10-20s for 20w rows)</div>';
  if (statusEl) statusEl.textContent = `Loading matrix for SKU prefix ${skuPrefix}${exactSku?' exact '+exactSku:''}, Line ${lineFilter||'All'}, Granularity ${granularity}, Cum ${cum}...`;

  try {
    const params = new URLSearchParams({
      job_id: v2vState.jobId,
      sku_prefix: skuPrefix,
      line_filter: lineFilter,
      granularity: granularity,
      cum: cum ? 'true' : 'false'
    });
    if (exactSku) params.append('exact_sku', exactSku);

    const resp = await fetch(`/v2v/api/plan_output/matrix?${params}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);

    console.log('Matrix data', data.summary);

    const dates = data.dates || [];
    const skuList = data.sku_list || [];
    const weeks = data.weeks || [];
    const months = data.months || [];
    const matrixData = data.data || {};

    if (skuList.length === 0 || dates.length === 0) {
      wrapper.innerHTML = `<div style="padding:20px;text-align:center;color:#64748b">No data for filters: SKU prefix ${skuPrefix}, Line ${lineFilter||'All'}<br>Try ALL prefix or empty line filter</div>`;
      if (statusEl) statusEl.textContent = `No data: ${data.summary ? JSON.stringify(data.summary) : ''}`;
      return;
    }

    // Build table with frozen SKU column and daily columns grouped by week
    let html = '';
    // Summary
    html += `<div style="font-size:12px;color:#64748b;margin-bottom:8px">SKUs: ${skuList.length} | Dates: ${dates.length} | Weeks: ${weeks.length} | Range: ${data.summary ? data.summary.date_range : ''} | Cum: ${cum ? 'Yes (prioritized)' : 'No'}</div>`;

    // Table header with week grouping
    html += '<div class="v2v-table-wrapper" style="max-height:600px"><table class="v2v-table"><thead>';
    // First header row: week grouping
    html += '<tr><th style="min-width:150px;left:0;position:sticky;z-index:20;background:#1e293b">SKU / Date</th>';
    if (granularity === 'day') {
      // Group by weeks for header
      for (const wk of weeks) {
        html += `<th colspan="${wk.dates.length}" style="text-align:center;background:#334155;min-width:${wk.dates.length*80}px">${esc(wk.week_label)} (${wk.dates.length}d)</th>`;
      }
    } else if (granularity === 'week') {
      html += `<th colspan="${weeks.length}" style="text-align:center;background:#334155">Weekly (${weeks.length} weeks)</th>`;
    } else if (granularity === 'monthly' || granularity === 'month') {
      html += `<th colspan="${months.length}" style="text-align:center;background:#334155">Monthly (${months.length} months)</th>`;
    }
    html += '</tr>';

    // Second header row: dates
    html += '<tr><th style="left:0;position:sticky;z-index:15;background:#1e293b">SKU</th>';
    if (granularity === 'day') {
      for (const d of dates) {
        html += `<th style="min-width:80px;font-size:11px">${esc(d.slice(5))}</th>`; // MM-DD
      }
    } else if (granularity === 'week') {
      for (const wk of weeks) {
        html += `<th style="min-width:90px;font-size:11px">${esc(wk.week_start_sunday.slice(5))}</th>`;
      }
    } else if (granularity === 'monthly' || granularity === 'month') {
      for (const mo of months) {
        html += `<th style="min-width:80px">${esc(mo.month)}</th>`;
      }
    }
    html += '</tr></thead><tbody>';

    // For performance, only show first 100 SKUs initially
    const displaySkus = skuList.slice(0, 100);
    for (const sku of displaySkus) {
      // Action buttons for drill-down: BOM children (FG -> GB/LT/FR/RT) and Line/Shift breakdown - Chart removed per user request
      const skuEsc = esc(sku).replace(/'/g, "\\'");
      html += `<tr><td style="left:0;position:sticky;background:white;z-index:10;font-weight:600;min-width:220px" class="frozen">
        <div style="display:flex;flex-direction:column;gap:2px">
          <span>${esc(sku)}</span>
          <div style="display:flex;gap:2px;flex-wrap:wrap">
            <button class="v2v-drill-btn" style="font-size:10px;padding:2px 6px" onclick="showBOMChildren('${skuEsc}')" title="Show BOM children: FG -> GB -> FR/LT/RT">🔍 BOM</button>
            <button class="v2v-drill-btn" style="font-size:10px;padding:2px 6px" onclick="showBreakdown('${skuEsc}', '')" title="Breakdown by Line/Shift">📊 Line/Shift</button>
          </div>
        </div>
      </td>`;
      if (granularity === 'day') {
        for (const d of dates) {
          const cell = matrixData[sku] && matrixData[sku][d] ? matrixData[sku][d] : {a:0,b:0,diff:0,cum_a:0,cum_b:0,cum_diff:0};
          const val = cum ? cell.cum_diff : cell.diff;
          const cls = val > 0 ? 'num-pos' : val < 0 ? 'num-neg' : '';
          const displayVal = cum ? `${cell.cum_a.toFixed(0)}/${cell.cum_b.toFixed(0)}<br><small style="color:${val>0?'#16a34a':val<0?'#dc2626':'#64748b'}">${val>0?'+':''}${val.toFixed(0)}</small>` : `${cell.a.toFixed(0)}/${cell.b.toFixed(0)}<br><small style="color:${val>0?'#16a34a':val<0?'#dc2626':'#64748b'}">${val>0?'+':''}${cell.diff.toFixed(0)}</small>`;
          html += `<td class="data-cell ${cls}" style="font-size:11px;text-align:center;min-width:80px;cursor:pointer" onclick="showBreakdown('${skuEsc}', '${d}')" title="Click to see Line/Shift breakdown for ${esc(sku)} on ${d}">${displayVal}</td>`;
        }
      } else if (granularity === 'week') {
        // Weekly data
        const weeklyData = data.weekly_data || {};
        for (const wk of weeks) {
          const wkData = weeklyData[sku] && weeklyData[sku][wk.week_start_sunday] ? weeklyData[sku][wk.week_start_sunday] : {a:0,b:0,diff:0,cum_a:0,cum_b:0,cum_diff:0};
          const val = cum ? wkData.cum_diff : wkData.diff;
          const displayVal = cum ? `${wkData.cum_a.toFixed(0)}/${wkData.cum_b.toFixed(0)}<br><small>${val>0?'+':''}${val.toFixed(0)}</small>` : `${wkData.a.toFixed(0)}/${wkData.b.toFixed(0)}<br><small>${wkData.diff.toFixed(0)}</small>`;
          html += `<td style="text-align:center;min-width:90px;cursor:pointer" onclick="showBreakdown('${esc(sku).replace(/'/g, "\\'")}', '${wk.week_start_sunday}')" title="Click to see Line/Shift breakdown for ${esc(sku)} week ${wk.week_start_sunday}">${displayVal}</td>`;
        }
      } else if (granularity === 'monthly' || granularity === 'month') {
        const monthlyData = data.monthly_data || {};
        for (const mo of months) {
          const moData = monthlyData[sku] && monthlyData[sku][mo.month] ? monthlyData[sku][mo.month] : {a:0,b:0,diff:0};
          const val = cum ? moData.cum_diff : moData.diff;
          const displayVal = `${moData.a.toFixed(0)}/${moData.b.toFixed(0)}<br><small>${val>0?'+':''}${val.toFixed(0)}</small>`;
          html += `<td style="text-align:center;cursor:pointer" onclick="showBreakdown('${esc(sku).replace(/'/g, "\\'")}', '${mo.month}-01')" title="Monthly breakdown">${displayVal}</td>`;
        }
      }
      html += '</tr>';
    }

    html += '</tbody></table></div>';

    if (skuList.length > 100) {
      html += `<div style="margin-top:8px;font-size:12px;color:#64748b">Showing first 100 of ${skuList.length} SKUs. Use SKU filter to narrow down (e.g., SK, GB, LT) or search.</div>`;
    }

    wrapper.innerHTML = html;
    if (statusEl) statusEl.innerHTML = `<span style="color:#16a34a">✅ Loaded matrix: ${skuList.length} SKUs × ${dates.length} dates | ${weeks.length} weeks | Cum: ${cum ? 'Yes' : 'No'} | <button class="btn btn-sm" onclick="loadPlanOutputMatrix()">Reload</button> <button class="btn btn-sm" onclick="document.getElementById('v2v-po-matrix-wrapper').scrollLeft=0">Scroll to start</button></span>`;

  } catch(e) {
    console.error('Matrix load failed', e);
    wrapper.innerHTML = `<div class="v2v-status error">❌ Failed to load matrix: ${e.message}</div>`;
    if (statusEl) statusEl.textContent = `Error: ${e.message}`;
  }
}

async function showBOMChildren(parentPn) {
  const modal = document.getElementById('v2v-bom-modal');
  const titleEl = document.getElementById('v2v-bom-title');
  const bodyEl = document.getElementById('v2v-bom-body');
  if (!modal || !titleEl || !bodyEl) return;

  titleEl.textContent = `BOM Children for ${parentPn}`;
  bodyEl.innerHTML = '<div class="v2v-loading"><div class="v2v-spinner"></div>Loading BOM children...</div>';
  modal.style.display = 'flex';

  try {
    const params = new URLSearchParams({job_id: v2vState.jobId, pn_code: parentPn, recursive: 'true', max_depth: '2'});
    const resp = await fetch(`/v2v/api/bom/children?${params}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);

    let html = `<div style="margin-bottom:12px;font-size:12px;color:#64748b">Parent: <b>${esc(parentPn)}</b> | Children A: ${data.total_a} | Children B: ${data.total_b} | Added: ${data.added.length} | Deleted: ${data.deleted.length}</div>`;

    if (data.added.length > 0) {
      html += `<div style="background:#f0fdf4;border:1px solid #bbf7d0;padding:8px;border-radius:4px;margin-bottom:8px"><b>Added in B:</b> ${data.added.map(esc).join(', ')}</div>`;
    }
    if (data.deleted.length > 0) {
      html += `<div style="background:#fef2f2;border:1px solid #fecaca;padding:8px;border-radius:4px;margin-bottom:8px"><b>Deleted in B:</b> ${data.deleted.map(esc).join(', ')}</div>`;
    }

    html += '<table class="v2v-table"><thead><tr><th>Level</th><th>Child PN</th><th>Type</th><th>Unit Num</th><th>Loss Rate</th><th>Parent Chain</th><th>Action</th></tr></thead><tbody>';

    const allChildren = [...(data.children_a || []), ...(data.children_b || [])];
    // Deduplicate by child
    const seen = new Set();
    for (const child of allChildren) {
      const childPn = child.child;
      if (seen.has(childPn)) continue;
      seen.add(childPn);
      const isAdded = data.added.includes(childPn);
      const isDeleted = data.deleted.includes(childPn);
      const rowClass = isAdded ? 'diff-add' : isDeleted ? 'diff-del' : '';
      html += `<tr class="${rowClass}"><td>${child.level}</td><td style="font-weight:600">${esc(child.child)}</td><td><span class="v2v-change-badge ${child.type==='GB'?'add':''}">${esc(child.type)}</span></td><td>${child.unit_num||''}</td><td>${child.loss_rate||''}</td><td style="font-size:11px;color:#64748b">${esc(child.parent_chain||child.parent||'')}</td><td><button class="v2v-drill-btn" onclick="document.getElementById('v2v-bom-modal').style.display='none'; document.getElementById('v2v-po-sku-prefix').value='${child.type==='GB'?'GB':child.type==='LT'?'LT':child.type==='FR'?'FR':child.type==='RT'?'RT':'SK'}'; loadPlanOutputMatrix();">📋 View Plan</button> <button class="v2v-drill-btn" onclick="showBOMChildren('${esc(child.child)}')">▶ Children</button></td></tr>`;
    }

    html += '</tbody></table>';
    html += `<div style="margin-top:12px;font-size:11px;color:#64748b">💡 Click "Children" to drill down further (e.g., SK → GB → FR/LT/RT). Click "View Plan" to see plan output for that intermediate SKU.</div>`;

    bodyEl.innerHTML = html;

  } catch(e) {
    bodyEl.innerHTML = `<div class="v2v-status error">Failed to load BOM children: ${e.message}</div>`;
  }
}

async function showBreakdown(sku, date) {
  const modal = document.getElementById('v2v-breakdown-modal');
  const titleEl = document.getElementById('v2v-breakdown-title');
  const bodyEl = document.getElementById('v2v-breakdown-body');
  if (!modal || !titleEl || !bodyEl) return;

  titleEl.textContent = `Breakdown by Line/Shift for ${sku} on ${date||'All dates'}`;
  bodyEl.innerHTML = '<div class="v2v-loading"><div class="v2v-spinner"></div>Loading breakdown...</div>';
  modal.style.display = 'flex';

  try {
    const params = new URLSearchParams({job_id: v2vState.jobId, sku: sku});
    if (date) params.append('date', date);
    const resp = await fetch(`/v2v/api/plan_output/breakdown?${params}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);

    let html = `<div style="margin-bottom:12px;font-size:12px;color:#64748b">SKU: <b>${esc(sku)}</b> | Date: <b>${esc(date||'All')}</b> | Total A: ${data.total_a} | Total B: ${data.total_b} | Breakdown rows: ${data.count}</div>`;
    html += '<table class="v2v-table"><thead><tr><th>Line</th><th>Shift</th><th>Plan Item</th><th>A</th><th>B</th><th>Diff</th></tr></thead><tbody>';

    for (const row of (data.breakdown||[]).slice(0,100)) {
      const diff = row.diff || 0;
      const cls = diff > 0 ? 'num-pos' : diff < 0 ? 'num-neg' : '';
      html += `<tr><td>${esc(row.LINE_CODE||'')}</td><td>${esc(row.SHIFT_NAME||'')}</td><td>${esc(row.PLAN_ITEM||'')}</td><td>${row.PLAN_VALUE_A||0}</td><td>${row.PLAN_VALUE_B||0}</td><td class="${cls}" style="font-weight:600">${diff>0?'+':''}${diff}</td></tr>`;
    }

    html += '</tbody></table>';
    if (data.count > 100) {
      html += `<div style="margin-top:8px;font-size:11px;color:#64748b">Showing first 100 of ${data.count} breakdown rows</div>`;
    }

    bodyEl.innerHTML = html;

  } catch(e) {
    bodyEl.innerHTML = `<div class="v2v-status error">Failed to load breakdown: ${e.message}</div>`;
  }
}

function esc(s) {
  if (s==null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Expose for inline handlers
window.selectV2VTable = selectV2VTable;
window.drillTo = drillTo;
window.drillDownOutput = drillDownOutput;
window.handleV2VRowChart = handleV2VRowChart;
window.v2vState = v2vState;
window.loadV2VDetail = loadV2VDetail;
window.v2vInit = v2vInit;
window.showV2VChart = showV2VChart;
window.loadV2VChart = loadV2VChart;
window.applyV2VOutputQuery = applyV2VOutputQuery;
window.resetV2VOutputQuery = resetV2VOutputQuery;
window.setV2VQuickQuery = setV2VQuickQuery;
window.updateV2VBuilderForTable = updateV2VBuilderForTable;
window.downloadV2VCurrentView = downloadV2VCurrentView;
window.exportV2VHtmlReport = exportV2VHtmlReport;
window.loadPlanOutputMatrix = loadPlanOutputMatrix;
window.showBOMChildren = showBOMChildren;
window.showBreakdown = showBreakdown;

// Auto init if on V2V page
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', v2vInit);
} else {
  v2vInit();
}
