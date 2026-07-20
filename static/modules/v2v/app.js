// V2V Module Frontend
// Handles folder upload, compare, summary cards, detail tabs with drill-down

const V2V_TABLE_DEFS = {
  bom: {icon: '📦', name: 'BOM快照', cat: 'input'},
  fcst: {icon: '📊', name: 'FCST', cat: 'input'},
  actual_io: {icon: '🏭', name: 'I_O实际值', cat: 'input'},
  supply: {icon: '🚚', name: 'Supply供应', cat: 'input'},
  switch: {icon: '🔀', name: '切换矩阵', cat: 'input'},
  item: {icon: '🏷️', name: '料号快照', cat: 'input'},
  line: {icon: '🧵', name: '线体快照', cat: 'input'},
  calendar: {icon: '📅', name: '线体日历', cat: 'input'},
  plan_config: {icon: '⚙️', name: '计划设置', cat: 'input'},
  plan_output: {icon: '📋', name: '排产结果输出', cat: 'output'},
  balance: {icon: '📦', name: '结存输出', cat: 'output'},
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
      if (nameEl) nameEl.textContent = `📁 ${folderName} - 点击可重新选择`;

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
        statusEl.innerHTML = `<div class="v2v-status info">✅ Version ${version} (${folderName}) loaded: ${xlsxCount} xlsx, ${Object.keys(identified).length} recognized. ${v2vState.versionA && v2vState.versionB ? 'Ready to compare!' : '请再选择另一个版本'}</div>`;
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
        alert('Please select both versions');
        return;
      }
      if (aPath === bPath) {
        alert('Please select different versions');
        return;
      }
      await compareServerVersions(aPath, bPath);
    });
  }

  // Load available versions on init
  fetch('/v2v/api/versions').then(r=>r.json()).then(data=>{
    const versions = data.versions || [];
    const selA = document.getElementById('v2v-server-a');
    const selB = document.getElementById('v2v-server-b');
    if (!selA || !selB) return;
    selA.innerHTML = '<option value="">Select Version A</option>';
    selB.innerHTML = '<option value="">Select Version B</option>';
    versions.forEach(v=>{
      const optA = document.createElement('option');
      optA.value = v.path;
      optA.textContent = `${v.name} (${v.file_count} files, ${v.recognized} recognized)`;
      selA.appendChild(optA);
      const optB = document.createElement('option');
      optB.value = v.path;
      optB.textContent = `${v.name} (${v.file_count} files, ${v.recognized} recognized)`;
      selB.appendChild(optB);
    });
    if (versions.length >= 2) {
      // Auto select first two for demo
      // selA.selectedIndex = 1;
      // selB.selectedIndex = 2;
    }
  }).catch(e=>{
    console.log('Failed to load server versions', e);
  });
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
    if (btn) { btn.disabled = false; btn.textContent = '▶ Compare Server Versions'; }
  }
}

document.addEventListener('DOMContentLoaded', ()=>{
  const btnCompare = document.getElementById('v2v-btn-compare');
  if (btnCompare) {
    btnCompare.addEventListener('click', async ()=>{
      if (!v2vState.versionA || !v2vState.versionB) {
        alert('Please select both Version A and Version B folders');
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
          <div class="v2v-stat-row"><span class="v2v-stat-label">Version A</span><span class="v2v-stat-value">${s.total_a||0} rows</span></div>
          <div class="v2v-stat-row"><span class="v2v-stat-label">Version B</span><span class="v2v-stat-value">${s.total_b||0} rows</span></div>
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
  let html = '';
  for (const [key, s] of Object.entries(summary)) {
    const def = V2V_TABLE_DEFS[key] || {icon:'📄', name:key};
    const totalDiff = (s.added||0)+(s.deleted||0)+(s.modified||0);
    const hasDiff = totalDiff>0;
    html += `<button class="v2v-detail-tab ${v2vState.activeTable===key?'active':''} ${hasDiff?'has-diff':''}" data-table="${key}" onclick="selectV2VTable('${key}')">${def.icon} ${def.name} <span class="count-badge">${totalDiff}</span></button>`;
  }
  tabsEl.innerHTML = html;
}

function selectV2VTable(tableName) {
  v2vState.activeTable = tableName;
  v2vState.currentPage = 1;
  v2vState.breadcrumbs = [{label:'All', granularity:v2vState.granularity, filters:{}}];
  
  // Update active states
  document.querySelectorAll('.v2v-summary-card').forEach(c=> c.classList.toggle('active', c.dataset.table===tableName));
  document.querySelectorAll('.v2v-detail-tab').forEach(t=> t.classList.toggle('active', t.dataset.table===tableName));
  
  // Show/hide output builder for plan_output and balance
  updateV2VBuilderForTable(tableName);

  loadV2VDetail(tableName);
}

function updateV2VBuilderForTable(tableName) {
  const builder = document.getElementById('v2v-output-builder');
  if (!builder) return;
  if (tableName === 'plan_output' || tableName === 'balance') {
    builder.style.display = 'block';
    // Populate groupby options
    const optionsEl = document.getElementById('v2v-groupby-options');
    if (optionsEl) {
      let opts = [];
      if (tableName === 'plan_output') {
        opts = [
          {val: 'LINE_CODE', label: 'LINE_CODE'},
          {val: 'SKU', label: 'SKU'},
          {val: 'PLAN_ITEM', label: 'PLAN_ITEM'},
          {val: 'PLAN_TYPE', label: 'PLAN_TYPE'}
        ];
      } else {
        opts = [
          {val: 'ITEM_CODE', label: 'ITEM_CODE'},
          {val: 'SHIFT_NAME', label: 'SHIFT'}
        ];
      }
      optionsEl.innerHTML = opts.map(o=>`<label style="font-size:12px;display:flex;align-items:center;gap:4px"><input type="checkbox" class="v2v-groupby-cb" value="${o.val}" checked> ${o.label}</label>`).join('');
    }
  } else {
    builder.style.display = 'none';
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
  const threshAbs = document.getElementById('v2v-threshold-abs') ? document.getElementById('v2v-threshold-abs').value : '0';

  v2vState.granularity = granularity;
  v2vState.currentPage = 1;
  // Store in state for loadV2VDetail to use
  v2vState.outputQuery = {group_by: groupBy, only_diff: onlyDiff, threshold_abs: threshAbs, granularity: granularity};

  loadV2VDetail(v2vState.activeTable);
}

function resetV2VOutputQuery() {
  v2vState.outputQuery = null;
  v2vState.granularity = 'week';
  document.querySelectorAll('#v2v-output-granularity button').forEach(b=>b.classList.remove('active'));
  const weekBtn = document.querySelector('#v2v-output-granularity button[data-granularity="week"]');
  if (weekBtn) weekBtn.classList.add('active');
  if (document.getElementById('v2v-only-diff')) document.getElementById('v2v-only-diff').checked = true;
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
    if ((tableName === 'plan_output' || tableName === 'balance') && v2vState.outputQuery) {
      if (v2vState.outputQuery.group_by) params.append('group_by', v2vState.outputQuery.group_by);
      params.append('only_diff', v2vState.outputQuery.only_diff ? 'true' : 'false');
      if (v2vState.outputQuery.threshold_abs) params.append('threshold_abs', v2vState.outputQuery.threshold_abs);
      if (v2vState.outputQuery.threshold_pct) params.append('threshold_pct', v2vState.outputQuery.threshold_pct);
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
      <div style="margin-top:12px"><button class="btn btn-sm" onclick="showV2VChart('${tableName}')">📈 Show Chart (if applicable)</button></div>
      <div id="v2v-chart-container" style="margin-top:16px;display:none"><canvas id="v2v-chart"></canvas></div>
    `;
    return;
  }

  // Header with actions
  let html = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><div style="font-size:12px;color:#64748b">Showing ${records.length} of ${pagination.total||records.length} records | Page ${pagination.page||1} | Table: ${def.name}</div><div><button class="btn btn-sm" onclick="showV2VChart('${tableName}')">📈 Chart</button></div></div>`;
  html += `<div id="v2v-chart-container" style="margin:12px 0;display:none;padding:12px;background:white;border:1px solid #e2e8f0;border-radius:6px"><canvas id="v2v-chart" style="max-height:300px"></canvas><div style="margin-top:8px;display:flex;gap:8px"><input type="text" id="v2v-chart-key" placeholder="Enter ${tableName==='supply'?'PN_CODE': tableName==='calendar'?'LINE_CODE': tableName==='actual_io'?'LINE_CODE or leave blank': 'Key for chart'}" style="padding:6px;border:1px solid #cbd5e1;border-radius:4px;flex:1"><button class="btn btn-sm" onclick="loadV2VChart('${tableName}')">Load Chart</button></div></div>`;
  html += '<div class="v2v-table-wrapper"><table class="v2v-table"><thead><tr>';

  // Headers per table
  if (tableName === 'bom') {
    html += '<th>Change</th><th>Parent PN</th><th>Item No</th><th>Field</th><th>A</th><th>B</th>';
  } else if (tableName === 'fcst') {
    html += '<th>Change</th><th>SKU</th><th>Week</th><th>Field</th><th>A</th><th>B</th><th>Delta</th>';
  } else if (tableName === 'plan_config') {
    html += '<th>Field</th><th>A</th><th>B</th><th>Change</th>';
  } else if (tableName === 'actual_io') {
    html += '<th>Change</th><th>Line</th><th>SKU</th><th>Date</th><th>Shift</th><th>Field</th><th>A</th><th>B</th><th>Delta</th><th>Chart</th>';
  } else if (tableName === 'supply') {
    html += '<th>Change</th><th>PN_CODE</th><th>Date/Week</th><th>Field</th><th>A</th><th>B</th><th>Delta</th><th>Chart</th>';
  } else if (tableName === 'switch') {
    html += '<th>Change</th><th>Line</th><th>Before PN</th><th>After PN</th><th>Field</th><th>A</th><th>B</th><th>Delta</th>';
  } else if (tableName === 'calendar') {
    html += '<th>Change</th><th>Line</th><th>Type</th><th>Date</th><th>Shift</th><th>Item</th><th>A</th><th>B</th><th>Delta</th><th>Chart</th>';
  } else if (tableName === 'item') {
    html += '<th>Change</th><th>Item No</th><th>Field</th><th>A</th><th>B</th>';
  } else if (tableName === 'line') {
    html += '<th>Change</th><th>Line Code</th><th>Field</th><th>A</th><th>B</th>';
  } else if (tableName === 'plan_output') {
    html += '<th>Time</th><th>Group</th><th>A Total</th><th>B Total</th><th>Diff</th><th>Diff%</th><th>Drill</th><th>Chart</th>';
  } else if (tableName === 'balance') {
    html += '<th>Time</th><th>Group</th><th>A Balance</th><th>B Balance</th><th>Diff</th><th>Diff%/Neg</th><th>Drill</th><th>Chart</th>';
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
      html += `<td>${esc(key.PARENT_PN_CODE||'')}</td>`;
      html += `<td>${esc(key.ITEM_NO||'')}</td>`;
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${esc(rec.value_a||'')}</td>`;
      html += `<td>${esc(rec.value_b||'')}</td>`;
    } else if (tableName === 'fcst') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.PN_CODE||'')}</td>`;
      html += `<td>${esc(key.WEEK||'')}</td>`;
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${rec.value_a||0}</td>`;
      html += `<td>${rec.value_b||0}</td>`;
      html += `<td style="${(rec.delta||0)>0?'color:#16a34a':(rec.delta||0)<0?'color:#dc2626':''}">${rec.delta||''}</td>`;
    } else if (tableName === 'plan_config') {
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${esc(rec.value_a||'')}</td>`;
      html += `<td>${esc(rec.value_b||'')}</td>`;
      html += `<td><span class="v2v-change-badge mod">MODIFY</span></td>`;
    } else if (tableName === 'actual_io') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.LINE_CODE||'')}</td>`;
      html += `<td>${esc(key.SKU||'')}</td>`;
      html += `<td>${esc(key.PLAN_DATE||key._MERGE_DATE||'')}</td>`;
      html += `<td>${esc(key.SHIFT_NAME||'')}</td>`;
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${rec.value_a||''}</td>`;
      html += `<td>${rec.value_b||''}</td>`;
      html += `<td style="${(rec.delta||0)>0?'color:#16a34a':(rec.delta||0)<0?'color:#dc2626':''}">${rec.delta||''}</td>`;
    } else if (tableName === 'supply') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.PN_CODE||'')}</td>`;
      html += `<td>${esc(key.KITTING_DATE||key.WEEK||key._MERGE_DATE||'')}<br><small>${key.GRANULARITY||''}</small></td>`;
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${rec.value_a||''}</td>`;
      html += `<td>${rec.value_b||''}</td>`;
      html += `<td style="${(rec.delta||0)>0?'color:#16a34a':(rec.delta||0)<0?'color:#dc2626':''}">${rec.delta||''}</td>`;
      html += `<td><button class="v2v-drill-btn" onclick="handleV2VRowChart('supply', {pn_code:'${esc(key.PN_CODE||'')}'})">📈</button></td>`;
    } else if (tableName === 'switch') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.LINE_CODE||'')}</td>`;
      html += `<td>${esc(key.BEFORE_PN_CODE||key.BEFORE||'')}</td>`;
      html += `<td>${esc(key.AFTER_PN_CODE||key.AFTER||'')}</td>`;
      html += `<td>${esc(rec.field||'')}</td>`;
      html += `<td>${rec.value_a||''}</td>`;
      html += `<td>${rec.value_b||''}</td>`;
      html += `<td>${rec.delta||''}</td>`;
    } else if (tableName === 'calendar') {
      html += `<td><span class="v2v-change-badge ${ctLower}">${badge}</span></td>`;
      html += `<td>${esc(key.LINE_CODE||'')}</td>`;
      html += `<td>${esc(key.PLAN_TYPE||'')}</td>`;
      html += `<td>${esc(key.PLAN_DATE||key.WEEK||key._DATE_STR||key._WEEK_STR||'')}</td>`;
      html += `<td>${esc(key.SHIFT_NAME||'')}</td>`;
      html += `<td>${esc(key.PLAN_ITEM||'')}</td>`;
      html += `<td>${rec.value_a||''}</td>`;
      html += `<td>${rec.value_b||''}</td>`;
      html += `<td style="${(rec.delta||0)>0?'color:#16a34a':(rec.delta||0)<0?'color:#dc2626':''}">${rec.delta||''}</td>`;
      html += `<td><button class="v2v-drill-btn" onclick="handleV2VRowChart('calendar', {line_code:'${esc(key.LINE_CODE||'')}', plan_type:'${esc(key.PLAN_TYPE||'UPH')}'})">📈</button></td>`;
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
      html += `<td><button class="v2v-drill-btn" onclick="handleV2VRowChart('plan_output', ${JSON.stringify(groupVals).replace(/"/g,'&quot;')})">📈</button></td>`;
    } else if (tableName === 'balance') {
      const groupVals = rec._group_values || key;
      html += `<td>${esc(rec._WEEK||rec._DATE||rec.ITEM_CODE||'')}</td>`;
      html += `<td>${Object.entries(groupVals).map(([k,v])=>`<div><small>${k}:</small> ${esc(v||'')}</div>`).join('')}</td>`;
      const displayA = rec.BALANCE_QTY_A !== undefined ? rec.BALANCE_QTY_A : (rec[rec.compare_field+'_A']||rec.PLAN_VALUE_A||0);
      const displayB = rec.BALANCE_QTY_B !== undefined ? rec.BALANCE_QTY_B : (rec[rec.compare_field+'_B']||rec.PLAN_VALUE_B||0);
      html += `<td>${displayA}</td>`;
      html += `<td>${displayB}</td>`;
      html += `<td style="${(rec.diff||0)>0?'color:#16a34a':(rec.diff||0)<0?'color:#dc2626':''};font-weight:600">${rec.diff||0}</td>`;
      html += `<td>${rec.diff_pct? rec.diff_pct.toFixed(1)+'%':''}${rec.is_negative? '<br><span style="color:#dc2626;font-weight:700">⚠️负库存</span>':''}</td>`;
      const drill = rec._drill || {};
      let drillBtn = '';
      if (drill.can_drill_day || drill.can_drill_shift) {
        const nextGran = drill.next_granularity || 'day';
        drillBtn = `<button class="v2v-drill-btn" onclick="drillDownOutput('${nextGran}', ${JSON.stringify(groupVals).replace(/"/g,'&quot;')})">▶ ${nextGran}</button>`;
      }
      html += `<td>${drillBtn}</td>`;
      html += `<td><button class="v2v-drill-btn" onclick="handleV2VRowChart('balance', ${JSON.stringify(groupVals).replace(/"/g,'&quot;')})">📈</button></td>`;
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
          {label: 'Version A (' + (v2vState.versionA?.name||'A') + ')', data: aVals, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', tension: 0.1},
          {label: 'Version B (' + (v2vState.versionB?.name||'B') + ')', data: bVals, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', tension: 0.1}
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
            x: {display: true, title: {display: true, text: 'Date'}},
                ticks: {maxTicksLimit: 20}},
            y: {display: true, title: {display: true, text: 'Value'}}
          }
        }
      });
    } catch(e) {
      console.error('Row chart failed', e);
    }
  })();
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

// Auto init if on V2V page
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', v2vInit);
} else {
  v2vInit();
}
