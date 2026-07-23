// V2V Module Frontend - v4 Horizontal continuous time axis for FCST/BOH/Plan Input/Plan Output
// - Time horizontal, continuous (empty if no diff)
// - SKU category filter: Material(3010*), Frame(FR-), GB, LT, RT, FG(SK-)
// - Line category for Plan Input/Output: AL1..AL10, ML2, ML5
// - Yellow for diff, green for no diff, no gray

const V2V_TABLE_DEFS = {
  bom: {name: 'BOM Snapshot', cat: 'input', icon: '📦'},
  fcst: {name: 'FCST', cat: 'input', icon: '📊', horizontal: true},
  supply: {name: 'Supply', cat: 'input', icon: '🚚'},
  switch: {name: 'Switch Matrix', cat: 'input', icon: '🔀'},
  item: {name: 'Item Master', cat: 'input', icon: '🏷️'},
  line: {name: 'Line Master', cat: 'input', icon: '🧵'},
  calendar: {name: 'Line Calendar', cat: 'input', icon: '📅'},
  plan_config: {name: 'Plan Config', cat: 'input', icon: '⚙️'},
  plan_input: {name: 'Plan Input', cat: 'output', icon: '📥', horizontal: true, needsSkuLine: true},
  plan_output: {name: 'Plan Output', cat: 'output', icon: '📋', horizontal: true, needsSkuLine: true},
  balance: {name: 'BOH', cat: 'output', icon: '📦', horizontal: true, needsSku: true},
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
  filters: {changeType: 'ALL', onlyDiff: true, skuCategory: 'ALL', lineCategory: 'ALL'}
};

function v2vInit() {
  console.log('V2V Init v4 horizontal continuous + persistence');
  setupV2VGranularity();
  setupV2VServerVersions();
  setupV2VFilters();
  fetch('/v2v/templates/schema').then(r=>r.json()).then(data=>{
    console.log('V2V schema loaded', Object.keys(data).length);
  }).catch(()=>{});
  // Try restore previous comparison from localStorage (to prevent loss on swipe/refresh)
  setTimeout(()=>{ tryRestoreV2VFromStorage(); }, 500);
}

function saveV2VToStorage() {
  try {
    const data = {
      jobId: v2vState.jobId,
      a_path: v2vState.a_path || null,
      b_path: v2vState.b_path || null,
      versionAName: v2vState.versionA?.name || v2vState.versionAName || null,
      versionBName: v2vState.versionB?.name || v2vState.versionBName || null,
      granularity: v2vState.granularity,
      activeTable: v2vState.activeTable,
      filters: v2vState.filters,
      timestamp: new Date().toISOString()
    };
    localStorage.setItem('v2v_last_compare', JSON.stringify(data));
    localStorage.setItem('v2v_has_saved', '1');
    console.log('V2V state saved', data.jobId);
    updateRestoreBanner();
  } catch(e) { console.log('Save storage failed', e); }
}

function clearV2VStorage() {
  try {
    localStorage.removeItem('v2v_last_compare');
    localStorage.removeItem('v2v_has_saved');
    console.log('V2V storage cleared');
    updateRestoreBanner();
  } catch(e) {}
}

function updateRestoreBanner() {
  const banner = document.getElementById('v2v-restore-banner');
  if (!banner) return;
  // Simplified: hide banner to avoid duplicate status display
  banner.style.display = 'none';
}

async function tryRestoreV2VFromStorage(force=false) {
  try {
    const savedStr = localStorage.getItem('v2v_last_compare');
    if (!savedStr) { updateRestoreBanner(); return; }
    const saved = JSON.parse(savedStr);
    if (!saved.jobId || !saved.a_path || !saved.b_path) { updateRestoreBanner(); return; }

    // If already have a job and not forced, don't auto-restore if current job is same
    if (!force && v2vState.jobId && v2vState.jobId === saved.jobId) {
      console.log('Already on saved job, skip restore');
      updateRestoreBanner();
      return;
    }

    // If we already have a job and user didn't force, don't auto overwrite, just show banner
    if (!force && v2vState.jobId) {
      console.log('Has active job, show banner only');
      updateRestoreBanner();
      return;
    }

    const statusEl = document.getElementById('v2v-status');
    if (statusEl && !v2vState.jobId) {
      statusEl.innerHTML = `<div class="v2v-status info">Loading: ${esc(saved.versionAName||'Prev')} vs ${esc(saved.versionBName||'Latest')}</div>`;
    }

    // Try to fetch existing job
    try {
      const jobResp = await fetch(`/v2v/api/job/${saved.jobId}`);
      if (jobResp.ok) {
        const jobData = await jobResp.json();
        console.log('Restoring from existing job', saved.jobId);
        const fakeData = {
          job_id: saved.jobId,
          summary: jobData.summary || {},
          diffs: jobData.diffs || {},
          overall: jobData.overall || {},
          folders: {a: saved.a_path, b: saved.b_path}
        };
        v2vState.a_path = saved.a_path;
        v2vState.b_path = saved.b_path;
        v2vState.versionAName = saved.versionAName;
        v2vState.versionBName = saved.versionBName;
        v2vState.granularity = saved.granularity || 'week';
        v2vState.activeTable = saved.activeTable || 'bom';
        v2vState.filters = saved.filters || {changeType:'ALL', onlyDiff:true, skuCategory:'ALL', lineCategory:'ALL'};
        document.querySelectorAll('.v2v-granularity-toggle button').forEach(b=>b.classList.toggle('active', b.dataset.granularity===v2vState.granularity));
        const skuSel = document.getElementById('v2v-sku-category'); if (skuSel && v2vState.filters.skuCategory) skuSel.value = v2vState.filters.skuCategory;
        const lineSel = document.getElementById('v2v-line-category'); if (lineSel && v2vState.filters.lineCategory) lineSel.value = v2vState.filters.lineCategory;
        const changeSel = document.getElementById('v2v-filter-changetype'); if (changeSel && v2vState.filters.changeType) changeSel.value = v2vState.filters.changeType;
        // Restore server selects if possible
        const selA = document.getElementById('v2v-server-a'); if (selA && saved.a_path) { try { selA.value = saved.a_path; } catch(e){} }
        const selB = document.getElementById('v2v-server-b'); if (selB && saved.b_path) { try { selB.value = saved.b_path; } catch(e){} }
        handleCompareResult(fakeData);
        if (statusEl) statusEl.innerHTML = `<div class="v2v-status success">Ready</div>`;
        updateRestoreBanner();
        return;
      }
    } catch(e) {
      console.log('Fetch existing job failed, will re-compare', e);
    }

    console.log('Job not in memory, re-comparing using saved paths', saved.a_path, saved.b_path);
    if (statusEl) statusEl.innerHTML = `<div class="v2v-status info">Loading: ${esc(saved.versionAName||'Prev')} vs ${esc(saved.versionBName||'Latest')}</div>`;
    const resp = await fetch('/v2v/api/compare', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({a_path: saved.a_path, b_path: saved.b_path, granularity: saved.granularity || 'week'})
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    v2vState.filters = saved.filters || v2vState.filters;
    v2vState.granularity = saved.granularity || 'week';
    v2vState.activeTable = saved.activeTable || 'bom';
    handleCompareResult(data);
    if (statusEl) statusEl.innerHTML = `<div class="v2v-status success">Ready</div>`;
    updateRestoreBanner();

  } catch(e) {
    console.log('Restore failed', e);
    const statusEl = document.getElementById('v2v-status');
    if (statusEl) statusEl.innerHTML = `<div class="v2v-status warn">Not Ready</div>`;
    updateRestoreBanner();
  }
}

function setupV2VGranularity() {
  document.querySelectorAll('.v2v-granularity-toggle button').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      document.querySelectorAll('.v2v-granularity-toggle button').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      v2vState.granularity = btn.dataset.granularity;
      v2vState.currentPage = 1;
      saveV2VToStorage();
      if (v2vState.jobId) {
        if (isHorizontalTable(v2vState.activeTable)) {
          loadHorizontalMatrix(v2vState.activeTable);
        } else {
          loadV2VDetail(v2vState.activeTable);
        }
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
      saveV2VToStorage();
      if (v2vState.jobId) {
        if (isHorizontalTable(v2vState.activeTable)) {
          loadHorizontalMatrix(v2vState.activeTable);
        } else {
          loadV2VDetail(v2vState.activeTable);
        }
      }
    });
  }

  // Multi-select setup for SKU and Line
  setupMultiSelect('sku', ['ALL','MATERIAL','FRAME','GB','LT','RT','FG'], getDefaultSkuCategories());
  setupMultiSelect('line', ['ALL','AL1','AL2','AL3','AL4','AL5','AL6','AL7','AL8','AL9','AL10','ML2','ML5'], ['ALL']);

  const dlBtn = document.getElementById('v2v-btn-download');
  if (dlBtn) dlBtn.addEventListener('click', downloadV2VCurrentView);
  const exportBtn = document.getElementById('v2v-btn-export-html');
  if (exportBtn) exportBtn.addEventListener('click', exportV2VHtmlReport);

  // Close multi-select menus when clicking outside
  document.addEventListener('click', (e)=>{
    if (!e.target.closest('.v2v-multi-select')) {
      document.querySelectorAll('.v2v-multi-menu').forEach(m=>m.style.display='none');
    }
  });
}

function getDefaultSkuCategories() {
  const table = v2vState.activeTable;
  if (table === 'balance' || table === 'boh') {
    return ['GB','FG']; // BOH default GB+FG per user request
  } else if (table === 'plan_input' || table === 'plan_output') {
    return ['FG']; // Plan Input/Output default FG
  } else {
    // FCST and others default ALL
    return ['ALL'];
  }
}

function getDefaultLineCategories() {
  // Plan Input/Output default ALL lines per user request
  return ['ALL'];
}

function setupMultiSelect(type, allValues, defaultSelected) {
  console.log(`[V2V] setupMultiSelect ${type} called, default:`, defaultSelected);
  const btnId = type === 'sku' ? 'v2v-sku-btn' : 'v2v-line-btn';
  const menuId = type === 'sku' ? 'v2v-sku-menu' : 'v2v-line-menu';
  const btn = document.getElementById(btnId);
  const menu = document.getElementById(menuId);
  console.log(`[V2V] btn ${btnId}:`, !!btn, `menu ${menuId}:`, !!menu);
  if (!btn || !menu) {
    console.warn(`[V2V] Multi-select elements not found for ${type}`);
    return;
  }

  const checkboxes = menu.querySelectorAll('input[type="checkbox"]');
  console.log(`[V2V] Found ${checkboxes.length} checkboxes for ${type}`);

  // Set initial defaults if no saved filter
  const savedFilter = type === 'sku' ? v2vState.filters.skuCategory : v2vState.filters.lineCategory;
  let initial = defaultSelected;
  if (savedFilter && savedFilter !== 'ALL') {
    const savedList = savedFilter.split(',').map(s=>s.trim()).filter(Boolean);
    if (savedList.length>0) initial = savedList;
  } else if (savedFilter === 'ALL') {
    initial = ['ALL'];
  } else {
    initial = getDefaultSkuCategoriesForType(type);
  }
  console.log(`[V2V] Initial for ${type}:`, initial, 'savedFilter:', savedFilter);

  // Apply initial checked state
  checkboxes.forEach(cb=>{
    cb.checked = initial.includes(cb.value);
  });

  updateMultiSelectButtonText(type);

  if (type === 'sku') {
    v2vState.filters.skuCategory = initial.includes('ALL') ? 'ALL' : initial.join(',');
  } else {
    v2vState.filters.lineCategory = initial.includes('ALL') ? 'ALL' : initial.join(',');
  }

  // Remove old listeners by cloning button (to avoid duplicate listeners on re-init)
  const newBtn = btn.cloneNode(true);
  btn.parentNode.replaceChild(newBtn, btn);
  const freshBtn = document.getElementById(btnId);

  freshBtn.addEventListener('click', (e)=>{
    console.log(`[V2V] ${type} button clicked`);
    e.stopPropagation();
    e.preventDefault();
    document.querySelectorAll('.v2v-multi-menu').forEach(m=>{
      if (m.id !== menuId) m.style.display='none';
    });
    const isHidden = menu.style.display === 'none' || !menu.style.display || menu.style.display === '';
    menu.style.display = isHidden ? 'block' : 'none';
    console.log(`[V2V] ${type} menu display set to ${menu.style.display}`);
  });

  // Handle checkbox changes - select all supports both forward and reverse
  checkboxes.forEach(cb=>{
    if (cb.dataset.listenerAttached) return;
    cb.dataset.listenerAttached = '1';
    cb.addEventListener('change', (e)=>{
      console.log(`[V2V] ${type} checkbox ${cb.value} changed to ${cb.checked}`);
      const value = cb.value;
      const isChecked = cb.checked;
      const allCb = menu.querySelector('input[value="ALL"]');

      if (value === 'ALL') {
        // Forward: click All -> check/uncheck all
        checkboxes.forEach(other=>{
          other.checked = isChecked;
        });
      } else {
        // Reverse: update All based on individuals
        const allIndividuals = Array.from(checkboxes).filter(c=>c.value !== 'ALL');
        const allChecked = allIndividuals.every(c=>c.checked);
        const anyChecked = allIndividuals.some(c=>c.checked);
        if (allCb) {
          if (allChecked) {
            allCb.checked = true;
          } else {
            allCb.checked = false;
          }
        }
        if (!anyChecked) {
          // If none checked, auto-check ALL to avoid empty filter (both directions)
          if (allCb) allCb.checked = true;
          allIndividuals.forEach(c=>{ c.checked = false; });
        }
      }

      // Determine final filter
      const isAllChecked = allCb ? allCb.checked : false;
      const selectedIndividuals = Array.from(checkboxes).filter(c=>c.checked && c.value !== 'ALL').map(c=>c.value);

      let finalSelected;
      if (isAllChecked) {
        finalSelected = ['ALL'];
      } else {
        finalSelected = selectedIndividuals.length ? selectedIndividuals : ['ALL'];
      }

      // For UX when ALL is selected, keep all checkboxes visually checked to show select-all state
      // Comment out if you prefer ALL exclusive
      if (finalSelected.includes('ALL')) {
        // Keep visual as all checked for select-all indication, but filter is ALL
        // To avoid confusion, we will keep all checked when ALL is checked
        if (isAllChecked) {
          checkboxes.forEach(c=>{ c.checked = true; });
        }
      }

      updateMultiSelectButtonText(type);

      if (type === 'sku') {
        v2vState.filters.skuCategory = finalSelected.includes('ALL') ? 'ALL' : finalSelected.join(',');
      } else {
        v2vState.filters.lineCategory = finalSelected.includes('ALL') ? 'ALL' : finalSelected.join(',');
      }

      console.log(`[V2V] ${type} new filter:`, type==='sku'?v2vState.filters.skuCategory:v2vState.filters.lineCategory, 'changeType:', v2vState.filters.changeType);

      v2vState.currentPage = 1;
      saveV2VToStorage();
      // Ensure any filter change reloads data - for both vertical and horizontal tables
      if (v2vState.jobId) {
        if (isHorizontalTable(v2vState.activeTable)) {
          loadHorizontalMatrix(v2vState.activeTable);
        } else {
          loadV2VDetail(v2vState.activeTable);
        }
      }
    });
  });
}

function getDefaultSkuCategoriesForType(type) {
  if (type === 'sku') {
    const table = v2vState.activeTable;
    if (table === 'balance' || table === 'boh') return ['GB','FG'];
    if (table === 'plan_input' || table === 'plan_output') return ['FG'];
    return ['ALL'];
  } else {
    return ['ALL'];
  }
}

function updateMultiSelectButtonText(type) {
  const btnId = type === 'sku' ? 'v2v-sku-btn' : 'v2v-line-btn';
  const menuId = type === 'sku' ? 'v2v-sku-menu' : 'v2v-line-menu';
  const btn = document.getElementById(btnId);
  const menu = document.getElementById(menuId);
  if (!btn || !menu) return;
  const checked = Array.from(menu.querySelectorAll('input[type="checkbox"]:checked')).map(c=>c.value);
  if (checked.length === 0 || checked.includes('ALL')) {
    btn.textContent = type === 'sku' ? 'All SKU ▾' : 'All Lines ▾';
  } else if (checked.length === 1) {
    btn.textContent = checked[0] + ' ▾';
  } else if (checked.length <= 2) {
    btn.textContent = checked.join('+') + ` (${checked.length}) ▾`;
  } else {
    btn.textContent = `${checked[0]}+${checked.length-1} more ▾`;
  }
}

// Update defaults when switching table
function updateMultiSelectDefaultsForTable(tableName) {
  // For BOH, default GB+FG
  // For Plan Input/Output, SKU FG, Line ALL
  // We only set defaults if current selection is ALL or empty, not overriding user custom selection? But user requested defaults, so we should set defaults on table switch
  const skuMenu = document.getElementById('v2v-sku-menu');
  const lineMenu = document.getElementById('v2v-line-menu');
  if (!skuMenu || !lineMenu) return;

  let skuDefault, lineDefault;
  if (tableName === 'balance' || tableName === 'boh') {
    skuDefault = ['GB','FG'];
    lineDefault = ['ALL'];
  } else if (tableName === 'plan_input' || tableName === 'plan_output') {
    skuDefault = ['FG'];
    lineDefault = ['ALL'];
  } else if (tableName === 'fcst') {
    skuDefault = ['ALL'];
    lineDefault = ['ALL'];
  } else {
    return; // For non-horizontal, keep current
  }

  // Only apply defaults if current filter is ALL or previously not set for this table type?
  // We will apply defaults when switching to table: set checkboxes to defaults
  // But to respect user's previous multi-select for same table, we could check if current filter is from different table default and override
  // Simplest: Always set to defaults on table switch as per user request for default presentation
  const skuCheckboxes = skuMenu.querySelectorAll('input[type="checkbox"]');
  skuCheckboxes.forEach(cb=>{
    cb.checked = skuDefault.includes(cb.value) || (skuDefault.includes('ALL') && cb.value==='ALL');
  });
  // Special: if skuDefault is ['GB','FG'], we need to uncheck ALL
  if (!skuDefault.includes('ALL')) {
    const allCb = skuMenu.querySelector('input[value="ALL"]');
    if (allCb) allCb.checked = false;
  }

  const lineCheckboxes = lineMenu.querySelectorAll('input[type="checkbox"]');
  lineCheckboxes.forEach(cb=>{
    cb.checked = lineDefault.includes(cb.value);
  });
  if (!lineDefault.includes('ALL')) {
    const allCb = lineMenu.querySelector('input[value="ALL"]');
    if (allCb) allCb.checked = false;
  }

  // Update button texts and filters
  updateMultiSelectButtonText('sku');
  updateMultiSelectButtonText('line');
  v2vState.filters.skuCategory = skuDefault.includes('ALL') ? 'ALL' : skuDefault.join(',');
  v2vState.filters.lineCategory = lineDefault.includes('ALL') ? 'ALL' : lineDefault.join(',');
  saveV2VToStorage();
}

function isHorizontalTable(tableName) {
  const def = V2V_TABLE_DEFS[tableName];
  return def && def.horizontal;
}

function updateSkuLineFilterVisibility(tableName) {
  const skuLabel = document.getElementById('v2v-sku-filter-label');
  const lineLabel = document.getElementById('v2v-line-filter-label');
  const def = V2V_TABLE_DEFS[tableName];
  if (!skuLabel || !lineLabel) return;
  if (def && def.horizontal) {
    skuLabel.style.display = 'inline-flex';
    if (tableName === 'balance' || tableName === 'boh' || tableName === 'fcst') {
      lineLabel.style.display = 'none';
    } else if (tableName === 'plan_input' || tableName === 'plan_output') {
      lineLabel.style.display = 'inline-flex';
    } else {
      lineLabel.style.display = 'none';
    }
    // Apply default selections per user request when switching tables
    // BOH default GB+FG, Plan Input/Output default SKU FG + Line ALL
    // We only apply defaults if no saved custom selection for this table, or always for default presentation?
    // Per user: default presentation should be GB+FG for BOH, FG+ALL for Plan Output/Input
    // So we set defaults on table switch, but respect saved storage if exists
    const saved = localStorage.getItem('v2v_last_compare');
    let shouldApplyDefault = true;
    if (saved) {
      try {
        const d = JSON.parse(saved);
        // If saved filters exist and activeTable matches current table, don't override with defaults
        // But if switching to different table type, apply defaults for that table
        if (d.filters && d.activeTable === tableName) {
          shouldApplyDefault = false;
        }
      } catch(e){}
    }
    if (shouldApplyDefault) {
      updateMultiSelectDefaultsForTable(tableName);
    } else {
      // Restore from saved filters
      updateMultiSelectButtonText('sku');
      updateMultiSelectButtonText('line');
    }
  } else {
    skuLabel.style.display = 'none';
    lineLabel.style.display = 'none';
  }
}

async function downloadV2VCurrentView() {
  if (!v2vState.jobId) { alert('No comparison job yet'); return; }
  const btn = document.getElementById('v2v-btn-download');
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Downloading...'; }
  try {
    const payload = {
      job_id: v2vState.jobId,
      table: v2vState.activeTable,
      granularity: v2vState.granularity,
      filters: {},
      only_diff: 'true',
      change_type: v2vState.filters.changeType || 'ALL',
      sku_category: v2vState.filters.skuCategory || 'ALL',
      line_category: v2vState.filters.lineCategory || 'ALL'
    };
    const lastCrumb = v2vState.breadcrumbs[v2vState.breadcrumbs.length-1];
    if (lastCrumb && lastCrumb.filters) payload.filters = {...payload.filters, ...lastCrumb.filters};
    const resp = await fetch('/v2v/api/download/current_view', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!resp.ok) { const err = await resp.json(); throw new Error(err.error || `HTTP ${resp.status}`); }
    const blob = await resp.blob();
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `V2V_${payload.table}_${v2vState.jobId.slice(0,6)}.xlsx`; a.click(); URL.revokeObjectURL(a.href);
  } catch(e){ alert('Download failed: '+e.message); console.error(e); }
  finally { if (btn) { btn.disabled=false; btn.textContent=orig||'📥 Download Current View'; } }
}

async function exportV2VHtmlReport() {
  if (!v2vState.jobId) { alert('No comparison job yet'); return; }
  const btn = document.getElementById('v2v-btn-export-html');
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled=true; btn.textContent='⏳ Exporting HTML...'; }
  try {
    const resp = await fetch('/v2v/api/export/html', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_id:v2vState.jobId})});
    if (!resp.ok) { const err=await resp.json(); throw new Error(err.error||`HTTP ${resp.status}`); }
    const blob = await resp.blob();
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=`V2V_Report_${v2vState.jobId.slice(0,6)}.html`; a.click(); URL.revokeObjectURL(a.href);
  } catch(e){ alert('Export failed: '+e.message); }
  finally { if (btn){ btn.disabled=false; btn.textContent=orig||'📄 Export HTML Report'; } }
}

async function loadServerVersions() {
  const selA = document.getElementById('v2v-server-a');
  const selB = document.getElementById('v2v-server-b');
  const scanTimeEl = document.getElementById('v2v-scan-time');
  if (!selA || !selB) return;
  const prevA = selA.value; const prevB = selB.value;
  try {
    selA.innerHTML='<option>Loading...</option>'; selB.innerHTML='<option>Loading...</option>';
    const resp=await fetch('/v2v/api/versions'); const data=await resp.json(); const versions=data.versions||[];
    const scannedAt=data.scanned_at?`Last scan: ${new Date(data.scanned_at).toLocaleTimeString()}`:'';
    if (scanTimeEl) scanTimeEl.textContent=`${scannedAt} | Found ${versions.length} version folders`;
    selA.innerHTML='<option value="">Select Previous Version</option>'; selB.innerHTML='<option value="">Select Latest Version</option>';
    versions.forEach(v=>{
      const optA=document.createElement('option'); optA.value=v.path; optA.textContent=`${v.name} (${v.file_count} files, ${v.recognized} recog)`; if(v.path===prevA) optA.selected=true; selA.appendChild(optA);
      const optB=document.createElement('option'); optB.value=v.path; optB.textContent=`${v.name} (${v.file_count} files, ${v.recognized} recog)`; if(v.path===prevB) optB.selected=true; selB.appendChild(optB);
    });
    return versions;
  } catch(e){ console.log('Failed to load server versions', e); selA.innerHTML='<option value="">Failed to load</option>'; selB.innerHTML='<option value="">Failed to load</option>'; return []; }
}

function setupV2VServerVersions() {
  const loadBtn=document.getElementById('v2v-btn-load-server');
  if (loadBtn) loadBtn.addEventListener('click', async ()=>{
    const selA=document.getElementById('v2v-server-a'); const selB=document.getElementById('v2v-server-b');
    if (!selA||!selB) return; const aPath=selA.value; const bPath=selB.value;
    if (!aPath||!bPath){ alert('Please select both Previous and Latest versions'); return; }
    if (aPath===bPath){ alert('Please select different versions'); return; }
    await compareServerVersions(aPath,bPath);
  });
  const refreshBtn=document.getElementById('v2v-btn-refresh');
  if (refreshBtn) refreshBtn.addEventListener('click', async ()=>{
    refreshBtn.disabled=true; refreshBtn.textContent='⏳ Scanning...'; await loadServerVersions(); refreshBtn.disabled=false; refreshBtn.textContent='🔄 Refresh';
    const statusEl=document.getElementById('v2v-status'); if(statusEl) statusEl.innerHTML='<div class="v2v-status success">✅ Refreshed folder list.</div>';
  });
  loadServerVersions();
}

async function compareServerVersions(aPath,bPath){
  const statusEl=document.getElementById('v2v-status'); const btn=document.getElementById('v2v-btn-load-server');
  const shortA = aPath.split('/').pop(); const shortB = bPath.split('/').pop();
  if(statusEl) statusEl.innerHTML=`<div class="v2v-status info">Loading: ${esc(shortA)} vs ${esc(shortB)}</div>`;
  if(btn){ btn.disabled=true; btn.textContent='Loading...'; }
  try{
    const resp=await fetch('/v2v/api/compare',{method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({a_path:aPath,b_path:bPath,granularity:v2vState.granularity})});
    const data=await resp.json(); if(data.error) throw new Error(data.error);
    v2vState.a_path = aPath;
    v2vState.b_path = bPath;
    v2vState.versionAName = aPath.split('/').pop();
    v2vState.versionBName = bPath.split('/').pop();
    handleCompareResult(data);
  }catch(e){ if(statusEl) statusEl.innerHTML=`<div class="v2v-status error">Not Ready: ${esc(e.message)}</div>`; }
  finally{ if(btn){ btn.disabled=false; btn.textContent='▶ Compare'; } }
}

function handleCompareResult(data){
  console.log('Compare result', data);
  v2vState.jobId=data.job_id; v2vState.summary=data.summary||{}; v2vState.diffs=data.diffs||{};
  // Preserve a_path/b_path if provided in data.folders or already in state
  if (data.folders) {
    if (data.folders.a) v2vState.a_path = data.folders.a;
    if (data.folders.b) v2vState.b_path = data.folders.b;
    if (!v2vState.versionAName && data.folders.a) v2vState.versionAName = data.folders.a.split('/').pop();
    if (!v2vState.versionBName && data.folders.b) v2vState.versionBName = data.folders.b.split('/').pop();
  }
  const statusEl=document.getElementById('v2v-status');
  if(statusEl){ statusEl.innerHTML=`<div class="v2v-status success">Ready: ${Object.keys(data.summary).length} tables</div>`; }
  const summarySection=document.getElementById('v2v-summary-section'); if(summarySection) summarySection.style.display='block';
  renderSummaryCards(data);
  const detailSection=document.getElementById('v2v-detail-section'); if(detailSection) detailSection.style.display='block';
  renderDetailTabs(data);
  const firstTable=Object.keys(data.summary)[0]||'bom';
  // If we have saved activeTable, use that, otherwise first
  const targetTable = v2vState.activeTable && data.summary[v2vState.activeTable] ? v2vState.activeTable : firstTable;
  v2vState.activeTable = targetTable;
  updateSkuLineFilterVisibility(targetTable);
  // Save to localStorage for persistence
  saveV2VToStorage();
  if (isHorizontalTable(targetTable)) {
    loadHorizontalMatrix(targetTable);
  } else {
    loadV2VDetail(targetTable);
  }
}

function renderSummaryCards(data){
  const grid=document.getElementById('v2v-summary-grid'); if(!grid) return;
  const summary=data.summary||{};
  const sortedKeys=Object.keys(summary).sort((a,b)=>{
    const defA=V2V_TABLE_DEFS[a]||{cat:'input'}; const defB=V2V_TABLE_DEFS[b]||{cat:'input'};
    if(defA.cat!==defB.cat) return defA.cat==='input'?-1:1;
    const totA=(summary[a].total_a||0); const totB=(summary[b].total_a||0);
    return totB-totA;
  });
  let html='';
  for(const key of sortedKeys){
    const s=summary[key]; const def=V2V_TABLE_DEFS[key]||{icon:'📄', name:key, cat:'input'};
    const displayName=key==='balance'?'BOH':def.name;
    let hasDiff = (s.total_a !== s.total_b) || ((s.added||0)+(s.deleted||0)+(s.modified||0) > 0);
    if(key==='plan_input'){
      const fcst = summary['fcst'];
      if(fcst && ((fcst.added||0)+(fcst.deleted||0)+(fcst.modified||0)>0 || fcst.total_a!==fcst.total_b)) hasDiff=true;
    }
    const cardClass = hasDiff ? 'has-diff' : 'no-diff';
    html+=`<div class="v2v-summary-card ${v2vState.activeTable===key?'active':''} ${cardClass}" data-table="${key}" onclick="selectV2VTable('${key}')">
        <div class="v2v-summary-card-header">
          <span class="v2v-summary-card-title"><span class="v2v-summary-card-icon">${def.icon||'📄'}</span> ${displayName}</span>
          <span class="v2v-summary-card-category ${def.cat}">${def.cat}</span>
        </div>
        <div class="v2v-summary-stats">
          <div class="v2v-stat-row"><span class="v2v-stat-label">Previous</span><span class="v2v-stat-value">${s.total_a||0} rows</span></div>
          <div class="v2v-stat-row"><span class="v2v-stat-label">Latest</span><span class="v2v-stat-value">${s.total_b||0} rows</span></div>
          ${!s.fast_summary ? `
          <div style="height:1px;background:#f1f5f9;margin:4px 0"></div>
          <div class="v2v-stat-row"><span class="v2v-stat-label">Added</span><span class="v2v-stat-value add">+${s.added||0}</span></div>
          <div class="v2v-stat-row"><span class="v2v-stat-label">Deleted</span><span class="v2v-stat-value del">-${s.deleted||0}</span></div>
          <div class="v2v-stat-row"><span class="v2v-stat-label">Modified</span><span class="v2v-stat-value mod">${s.modified||0}</span></div>
          ` : `<div style="font-size:11px;margin-top:6px;padding:4px 6px;border-radius:4px;${hasDiff ? 'background:#fffbeb;color:#92400e' : 'background:#f0fdf4;color:#166534'}">${hasDiff ? '⚠️ Has diff - click tab' : '✅ No diff'}</div>`}
        </div>
        <div class="v2v-progress"><div class="v2v-progress-bar ${hasDiff?'has-diff':''}" style="width:${hasDiff?'100%':'0%'}"></div></div>
      </div>`;
  }
  grid.innerHTML=html;
}

function renderDetailTabs(data){
  const tabsEl=document.getElementById('v2v-detail-tabs'); if(!tabsEl) return;
  const summary=data.summary||{}; const groups={input:[], output:[]};
  for(const [key,s] of Object.entries(summary)){
    if(key==='actual_io') continue;
    const def=V2V_TABLE_DEFS[key]||{name:key, cat:'input'}; const cat=def.cat||'input';
    if(!groups[cat]) groups[cat]=[]; groups[cat].push([key,s]);
  }
  let html='';
  if(groups.input && groups.input.length>0){
    html+='<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-bottom:8px"><span style="font-size:12px;font-weight:600;color:#0f172a;margin-right:8px;min-width:50px">Input:</span>';
    for(const [key,s] of groups.input){
      const def=V2V_TABLE_DEFS[key]||{name:key}; const displayName=key==='balance'?'BOH':def.name;
      let hasDiff = (s.total_a!==s.total_b) || ((s.added||0)+(s.deleted||0)+(s.modified||0)>0);
      if(key==='plan_input'){
        const fcst = summary['fcst'];
        if(fcst && ((fcst.added||0)+(fcst.deleted||0)+(fcst.modified||0)>0 || fcst.total_a!==fcst.total_b)) hasDiff=true;
      }
      const cls = hasDiff ? 'has-diff' : 'no-diff';
      html+=`<button class="v2v-detail-tab ${v2vState.activeTable===key?'active':''} ${cls}" data-table="${key}" onclick="selectV2VTable('${key}')">${displayName}</button>`;
    }
    html+='</div>';
  }
  if(groups.output && groups.output.length>0){
    html+='<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px"><span style="font-size:12px;font-weight:600;color:#0f172a;margin-right:8px;min-width:50px">Output:</span>';
    for(const [key,s] of groups.output){
      const def=V2V_TABLE_DEFS[key]||{name:key}; const displayName=key==='balance'?'BOH':def.name;
      let hasDiff = (s.total_a!==s.total_b) || ((s.added||0)+(s.deleted||0)+(s.modified||0)>0);
      if(key==='plan_input'){
        const fcst = summary['fcst'];
        if(fcst && ((fcst.added||0)+(fcst.deleted||0)+(fcst.modified||0)>0 || fcst.total_a!==fcst.total_b)) hasDiff=true;
      }
      const cls = hasDiff ? 'has-diff' : 'no-diff';
      html+=`<button class="v2v-detail-tab ${v2vState.activeTable===key?'active':''} ${cls}" data-table="${key}" onclick="selectV2VTable('${key}')">${displayName}</button>`;
    }
    html+='</div>';
  }
  tabsEl.innerHTML=html;
}

function selectV2VTable(tableName){
  v2vState.activeTable=tableName; v2vState.currentPage=1;
  v2vState.breadcrumbs=[{label:'All', granularity:v2vState.granularity, filters:{}}];
  document.querySelectorAll('.v2v-summary-card').forEach(c=>c.classList.toggle('active', c.dataset.table===tableName));
  document.querySelectorAll('.v2v-detail-tab').forEach(t=>t.classList.toggle('active', t.dataset.table===tableName));
  updateSkuLineFilterVisibility(tableName);
  saveV2VToStorage();
  const detailSection=document.getElementById('v2v-detail-section');
  if(detailSection){ setTimeout(()=>detailSection.scrollIntoView({behavior: 'smooth', block: 'start'}),100); }
  if (isHorizontalTable(tableName)) {
    loadHorizontalMatrix(tableName);
  } else {
    loadV2VDetail(tableName);
  }
}

async function loadV2VDetail(tableName){
  const wrapper=document.getElementById('v2v-detail-content'); if(!wrapper) return;
  const displayName=tableName==='balance'?'BOH':(V2V_TABLE_DEFS[tableName]?.name||tableName);
  wrapper.innerHTML=`<div class="v2v-loading"><div class="v2v-spinner"></div>Loading ${displayName} (${v2vState.granularity})...</div>`;
  try{
    if (!v2vState.jobId) throw new Error('No job_id - please Compare first');
    const params=new URLSearchParams({
      job_id:v2vState.jobId,
      granularity:v2vState.granularity,
      change_type:v2vState.filters.changeType||'ALL',
      only_diff:'true',
      page:v2vState.currentPage,
      page_size:100
    });
    const lastCrumb=v2vState.breadcrumbs[v2vState.breadcrumbs.length-1];
    if(lastCrumb && lastCrumb.filters){ for(const [k,v] of Object.entries(lastCrumb.filters)){ if(v) params.append(k,v); } }
    const resp=await fetch(`/v2v/api/diff/${tableName}?${params}`); const data=await resp.json(); if(data.error) throw new Error(data.error);
    renderV2VTableDetail(data, tableName); renderV2VBreadcrumb();
  }catch(e){
    console.error(e);
    if (e.message && e.message.includes('Invalid job_id')) {
      wrapper.innerHTML=`<div class="v2v-status warn">⚠️ Job expired (server restarted) - attempting auto-restore...<br><small>Plan Input needs FCST data, ensure both versions have FCST files</small></div>`;
      try {
        await tryRestoreV2VFromStorage(true);
        if (v2vState.jobId) setTimeout(()=>loadV2VDetail(tableName), 1500);
      } catch(re) {
        wrapper.innerHTML=`<div class="v2v-status error">❌ Failed to load: ${esc(e.message)}<br><br>💡 Server restarted, job expired. Please re-select versions and Compare again. For Plan Input, ensure Previous and Latest both contain FCST_Main and FCST_Detail xlsx.</div>`;
      }
    } else {
      wrapper.innerHTML=`<div class="v2v-status error">❌ Failed to load: ${esc(e.message)}<br>${tableName==='plan_input' ? '<small>💡 Plan Input = FCST aggregated. Requires FCST_Main + FCST_Detail in both versions. Check if files exist and file count shows recognized >=2.</small>':''}</div>`;
    }
  }
}

// New: Horizontal continuous matrix for FCST/BOH/Plan Input/Plan Output
async function loadHorizontalMatrix(tableName) {
  const wrapper=document.getElementById('v2v-detail-content'); if(!wrapper) return;
  const displayName=tableName==='balance'?'BOH':(V2V_TABLE_DEFS[tableName]?.name||tableName);
  const skuCat = v2vState.filters.skuCategory || 'ALL';
  const lineCat = v2vState.filters.lineCategory || 'ALL';
  const changeType = v2vState.filters.changeType || 'ALL';
  wrapper.innerHTML=`<div class="v2v-loading"><div class="v2v-spinner"></div>Loading ${displayName} horizontal matrix - ${v2vState.granularity} continuous | SKU: ${skuCat} | Line: ${lineCat} | Change: ${changeType} | Time horizontal, empty if no diff...</div>`;
  try {
    if (!v2vState.jobId) throw new Error('No job_id - please Compare first');
    const params = new URLSearchParams({
      job_id: v2vState.jobId,
      granularity: v2vState.granularity,
      sku_category: skuCat,
      line_category: lineCat,
      only_diff: 'true',
      change_type: changeType
    });
    let apiTable = tableName;
    if (apiTable === 'balance') apiTable = 'balance';
    const resp = await fetch(`/v2v/api/matrix/${apiTable}?${params}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    renderHorizontalTable(data, tableName);
  } catch(e) {
    console.error(e);
    if (e.message && e.message.includes('Invalid job_id')) {
      wrapper.innerHTML=`<div class="v2v-status warn">⚠️ Job expired (server restarted) - attempting auto-restore for ${displayName}...<br><small>Saved version: ${esc(v2vState.versionAName||'Prev')} vs ${esc(v2vState.versionBName||'Latest')}</small></div>`;
      try {
        await tryRestoreV2VFromStorage(true);
        // After restore, retry once
        if (v2vState.jobId) {
          setTimeout(()=>loadHorizontalMatrix(tableName), 1500);
        }
      } catch(re) {
        wrapper.innerHTML=`<div class="v2v-status error">❌ Failed to load horizontal matrix: ${e.message}<br><br>💡 Server was restarted and job expired. Please re-select Previous and Latest versions and click <b>▶ Compare</b> again.<br><small>Tip: Data is auto-saved in localStorage, click Restore banner above to re-compare.</small></div>`;
      }
    } else {
      wrapper.innerHTML=`<div class="v2v-status error">❌ Failed to load horizontal matrix: ${esc(e.message)}<br><br>💡 If job expired, please re-select versions and Compare again.</div>`;
    }
  }
}

function renderHorizontalTable(data, tableName) {
  const wrapper=document.getElementById('v2v-detail-content'); if(!wrapper) return;
  const displayName=tableName==='balance'?'BOH':(V2V_TABLE_DEFS[tableName]?.name||tableName);
  const timeBuckets = data.time_buckets || [];
  const bucketLabels = data.bucket_labels || timeBuckets;
  const skuList = data.sku_list || [];
  const matrix = data.matrix || {};
  const summary = data.summary || {};
  const gran = (data.granularity || v2vState.granularity || 'week');

  if (!timeBuckets || timeBuckets.length===0 || skuList.length===0) {
    wrapper.innerHTML=`<div class="v2v-status success">✅ No diff for ${displayName} with filters SKU:${data.params?.sku_category||'ALL'} Line:${data.params?.line_category||'ALL'} Granularity:${gran} - All gaps 0 or filtered out</div>
      <div style="padding:12px;font-size:12px;color:#64748b">Time buckets continuous: ${bucketLabels.length} | SKU count after filter: ${summary.total_skus||0} (original ${summary.total_original_skus||0}) | Try different SKU category like ALL or FG</div>`;
    return;
  }

  const displayMode = data.display_mode || (['week','month','monthly'].includes(gran) && ['balance','boh','plan_input','plan_output'].includes(tableName) ? 'has_change' : 'detailed');
  const isHasChangeMode = displayMode === 'has_change';

  // Fixed color legend - adapt for has_change mode
  let html = '';
  if (isHasChangeMode) {
    html = `<div class="v2v-legend">
      <div class="v2v-legend-item"><div class="v2v-legend-color modify" style="background:#fef9c3;border-color:#facc15"></div><span style="font-weight:600">🟡 Has Change in this ${gran==='week'?'Week':'Month'} (any ADD/DEL/MOD inside period)</span></div>
      <div style="margin-left:auto;font-size:11px;color:#64748b">${displayName} | Time: <b>${gran}</b> (${isHasChangeMode?'Yellow-only indicator, no numbers':'Detailed'}) continuous ${bucketLabels.length} buckets | SKU: <b>${(data.params?.sku_category||data.sku_category||'ALL')}</b> | Line: <b>${(data.params?.line_category||data.line_category||'ALL')}</b> | Empty = no diff in period</div>
    </div>`;
  } else {
    html = `<div class="v2v-legend">
      <div class="v2v-legend-item"><div class="v2v-legend-color added"></div><span>ADDED (new, from 0 to X, e.g., +89k)</span></div>
      <div class="v2v-legend-item"><div class="v2v-legend-color deleted"></div><span>DELETED (X to 0, negative, e.g., -89k)</span></div>
      <div class="v2v-legend-item"><div class="v2v-legend-color modify"></div><span>MODIFY (change X→Y, diff)</span></div>
      <div style="margin-left:auto;font-size:11px;color:#64748b">${displayName} | Time: <b>${gran}</b> continuous ${bucketLabels.length} buckets | SKU: <b>${data.params?.sku_category||'ALL'}</b> | Line: <b>${data.params?.line_category||'ALL'}</b> | Empty = no diff</div>
    </div>`;
  }

  // For performance, limit columns displayed if too many? User wants continuous, but we can show all with scroll
  // Show first 100 time buckets? But user wants continuous, so we should show all, but limit to first 200 for performance? We'll show all but with warning if >100 columns
  const maxCols = 200;
  let displayBuckets = bucketLabels;
  let displayTimeBuckets = timeBuckets;
  let truncated = false;
  if (bucketLabels.length > maxCols) {
    // For day granularity, could be 180+ days, still okay to show 200, but if 365 days, truncate? We'll show first 100 and provide note
    // Instead, we show all but with horizontal scroll, but limit to 150 to avoid browser crash
    // Let's show first maxCols and indicate truncated
    displayBuckets = bucketLabels.slice(0, maxCols);
    if (Array.isArray(timeBuckets) && typeof timeBuckets[0] === 'object') {
      displayTimeBuckets = timeBuckets.slice(0, maxCols);
    } else {
      displayTimeBuckets = timeBuckets.slice(0, maxCols);
    }
    truncated = true;
  }

  html += `<div class="v2v-table-wrapper" style="max-height:650px;max-width:100%;overflow:auto"><table class="v2v-table"><thead><tr>`;
  html += `<th style="min-width:200px;position:sticky;left:0;z-index:20;background:#1e293b">SKU / Time →<br><small style="font-weight:400">Vertical SKU, Horizontal Time (continuous)</small></th>`;
  // Time headers
  for (let i=0;i<displayBuckets.length;i++) {
    const label = displayBuckets[i];
    // For month, show YYYY-MM, for week show MM-DD, for day show MM-DD
    let shortLabel = label;
    if (typeof label === 'string' && label.length > 10) {
      shortLabel = label.slice(0,10);
    } else if (typeof label === 'object' && label.label) {
      shortLabel = label.label;
    }
    // Show only date part for day/week
    if (gran === 'day' && typeof shortLabel === 'string' && shortLabel.includes('-')) {
      shortLabel = shortLabel.slice(5); // MM-DD
    } else if (gran === 'week' && typeof shortLabel === 'string') {
      shortLabel = shortLabel.slice(5);
    }
    html += `<th class="col-center" style="min-width:90px;font-size:11px" title="${esc(label)}">${esc(shortLabel)}</th>`;
  }
  if (truncated) {
    html += `<th style="min-width:100px;background:#fef3c7;color:#92400e">... +${bucketLabels.length - maxCols} more (too many, showing first ${maxCols})</th>`;
  }
  html += `</tr></thead><tbody>`;

  // Rows - support has_change yellow-only mode for weekly/monthly BOH/Plan Input/Plan Output
  const displaySkus = skuList.slice(0, 200);
  for (const sku of displaySkus) {
    const rowData = matrix[sku] || {};
    html += `<tr><td style="position:sticky;left:0;background:white;z-index:10;font-weight:600;min-width:200px" class="frozen">${esc(sku)}</td>`;
    for (let i=0;i<displayBuckets.length;i++) {
      const tb = displayBuckets[i];
      const cell = rowData[tb];
      if (!cell) {
        html += `<td class="col-center" style="background:#f8fafc"></td>`;
      } else {
        // Check if has_change mode
        const isHC = cell.has_change || cell.display_mode==='has_change' || cell.tag==='HAS_CHANGE' || isHasChangeMode;
        if (isHC) {
          const changedDays = cell.changed_days || cell.changed_weeks || [];
          const changedCount = cell.changed_count || changedDays.length || 0;
          const tooltipDays = changedDays.length ? changedDays.slice(0,10).join(', ') + (changedDays.length>10?` +${changedDays.length-10} more`: '') : '';
          const tooltip = `Has change in this ${gran} - ${changedCount} ${gran==='month'?'days':'days/weeks'} changed${tooltipDays?' - e.g. '+tooltipDays:''} (yellow)`;
          html += `<td class="col-center" style="background:#fef08a;border:1px solid #facc15;text-align:center;min-width:90px" title="${esc(tooltip)}">
            <div style="font-size:12px;font-weight:700;color:#854d0e">●</div>
          </td>`;
        } else {
          const diff = cell.diff || 0;
          const prev = cell.prev || 0;
          const latest = cell.latest || 0;
          const tag = cell.tag || 'MODIFY';
          let cellClass = '';
          let diffDisplay = '';
          let tooltip = '';
          if (tag === 'ADDED') {
            cellClass = 'cell-added';
            diffDisplay = `+${Number(latest).toLocaleString()}`;
            tooltip = `ADDED: New SKU, from 0 to ${latest}, total ${latest} (green)`;
          } else if (tag === 'DELETED') {
            cellClass = 'cell-deleted';
            diffDisplay = `${Number(diff).toLocaleString()}`;
            tooltip = `DELETED: ${prev} → 0, diff ${diff} (red, negative)`;
          } else {
            cellClass = 'cell-modify';
            diffDisplay = `${Number(prev).toLocaleString()}→${Number(latest).toLocaleString()}`;
            tooltip = `MODIFY: ${prev} → ${latest}, diff ${diff>0?'+':''}${diff}`;
          }
          if (diff === 0 && tag === 'UNCHANGED') {
            html += `<td class="col-center" style="background:#f8fafc" title="${esc(tooltip)}"></td>`;
          } else {
            if (tag === 'MODIFY') {
              html += `<td class="col-center ${cellClass}" style="text-align:center;min-width:110px" title="${esc(tooltip)}">
                <div style="font-size:11px;color:#0f172a;font-weight:600">${esc(diffDisplay)}</div>
                <div style="font-size:10px;color:${diff>0?'#16a34a':'#dc2626'};font-weight:700">${diff>0?'+':''}${Number(diff).toLocaleString()}</div>
              </td>`;
            } else {
              const diffColor = tag === 'ADDED' ? '#166534' : '#991b1b';
              html += `<td class="col-center ${cellClass}" style="text-align:center;min-width:90px" title="${esc(tooltip)}">
                <div style="font-weight:700;color:${diffColor};font-size:12px">${esc(diffDisplay)}</div>
              </td>`;
            }
          }
        }
      }
    }
    if (truncated) {
      html += `<td style="background:#fef3c7"></td>`;
    }
    html += `</tr>`;
  }

  html += `</tbody></table></div>`;

  if (skuList.length > 200) {
    html += `<div style="margin-top:8px;font-size:11px;color:#64748b">Showing first 200 of ${skuList.length} SKUs (only diff). Use SKU Category filter to narrow down: Material(3010*), Frame(FR-*), GB, LT, RT, FG(SK-*).</div>`;
  }
  if (truncated) {
    html += `<div style="margin-top:8px;font-size:11px;color:#92400e;background:#fffbeb;padding:6px;border-radius:4px">⚠️ Time buckets continuous but too many (${bucketLabels.length}), showing first ${maxCols}. For day granularity over long period, consider switching to Week or Month to reduce columns.</div>`;
  }

  html += `<div style="margin-top:8px;font-size:11px;color:#64748b">Total SKUs (only diff after filter): ${skuList.length} / Original ${summary.total_original_skus||skuList.length} | Time buckets: ${bucketLabels.length} continuous (${summary.time_range||''}) | Empty cell = no diff / no data for that time bucket</div>`;

  wrapper.innerHTML = html;
}

function renderV2VTableDetail(data, tableName){
  const wrapper=document.getElementById('v2v-detail-content'); if(!wrapper) return;
  const records=data.records||[]; const pagination=data.pagination||{}; const def=V2V_TABLE_DEFS[tableName]||{name:tableName};
  const displayName=tableName==='balance'?'BOH':def.name;
  const gran=(data.granularity||v2vState.granularity||'week').toLowerCase();
  const granLabelMap={week:'Week', day:'Day', month:'Month', monthly:'Month', shift:'Shift'}; const granLabel=granLabelMap[gran]||gran;

  if(records.length===0){
    wrapper.innerHTML=`<div class="v2v-status success">✅ No differences for ${displayName} (${granLabel}) - All SKU gaps are 0</div>
      <div style="padding:12px;font-size:12px;color:#64748b">Total after filter: ${pagination.total||0} | Granularity: ${gran}</div>`;
    return;
  }

  let html=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px">
    <div style="font-size:12px;color:#64748b">Showing ${records.length} of ${pagination.total||records.length} | Page ${pagination.page||1} | ${displayName} - ${granLabel}</div>
    <div style="font-size:11px;color:#64748b">Tag: <span class="v2v-change-badge add">ADDED</span> <span class="v2v-change-badge del">DELETED</span> <span class="v2v-change-badge mod">MODIFY</span></div>
  </div>`;

  html+='<div class="v2v-table-wrapper" style="max-height:600px"><table class="v2v-table"><thead><tr>';

  if(tableName==='bom'){
    html+='<th>Tag</th><th>Parent PN</th><th>Item No</th><th>Field</th><th class="col-center">Previous</th><th class="col-center">Latest</th><th class="col-center">Diff</th>';
  }else if(tableName==='fcst'){
    html+='<th class="col-center">Tag</th><th>SKU</th><th>Week</th><th>Field</th><th class="col-center">Previous</th><th class="col-center">Latest</th><th class="col-center">Diff</th>';
  }else if(tableName==='plan_config'){
    html+='<th>Field</th><th class="col-center">Previous</th><th class="col-center">Latest</th><th class="col-center">Tag</th>';
  }else if(tableName==='supply'){
    html+='<th class="col-center">Tag</th><th>PN_CODE</th><th>Date</th><th>Field</th><th class="col-center">Previous</th><th class="col-center">Latest</th><th class="col-center">Diff</th>';
  }else if(tableName==='switch'){
    html+='<th class="col-center">Tag</th><th>Line</th><th>Before PN</th><th>After PN</th><th>Field</th><th class="col-center">Previous</th><th class="col-center">Latest</th><th class="col-center">Diff</th>';
  }else if(tableName==='calendar'){
    html+='<th class="col-center">Tag</th><th>Line</th><th>Type</th><th>Date</th><th>Shift</th><th>Item</th><th class="col-center">Previous</th><th class="col-center">Latest</th><th class="col-center">Diff</th>';
  }else if(tableName==='item'){
    html+='<th class="col-center">Tag</th><th>ITEM_NO</th><th>Field</th><th>Previous</th><th>Latest</th>';
  }else if(tableName==='line'){
    html+='<th class="col-center">Tag</th><th>Line Code</th><th>Field</th><th class="col-center">Previous</th><th class="col-center">Latest</th>';
  }else{
    const first=records[0]; const keys=Object.keys(first).slice(0,8);
    for(const k of keys) html+=`<th>${esc(k)}</th>`;
  }
  html+='</tr></thead><tbody>';

  for(const rec of records){
    const ctRaw=rec.change_type||rec.change_tag||rec.TAG||'MODIFY'; const ct=String(ctRaw).toUpperCase();
    const ctLower=ct.includes('ADD')?'add':ct.includes('DEL')?'del':'mod'; const badge=ct; const key=rec.key||{};
    if(tableName==='bom'){
      html+=`<tr class="diff-${ctLower}"><td class="col-center"><span class="v2v-change-badge ${ctLower}">${badge}</span></td><td>${esc(key.PARENT_PN_CODE||rec.PARENT_PN_CODE||'')}</td><td>${esc(key.ITEM_NO||rec.ITEM_NO||'')}</td><td>${esc(rec.field||'')}</td><td class="col-center">${esc(rec.value_a||rec.PREV||'')}</td><td class="col-center">${esc(rec.value_b||rec.LATEST||'')}</td><td class="col-center">${rec.diff||rec.DIFF||''}</td></tr>`;
    }else if(tableName==='fcst'){
      html+=`<tr class="diff-${ctLower}"><td class="col-center"><span class="v2v-change-badge ${ctLower}">${badge}</span></td><td>${esc(key.PN_CODE||rec.PN_CODE||rec.SKU||'')}</td><td>${esc(key.WEEK||rec.WEEK||rec._WEEK||rec.TIME||'')}</td><td>${esc(rec.field||'ACTUALWEEKVALUE')}</td><td class="col-center">${rec.value_a||rec.PREV||0}</td><td class="col-center">${rec.value_b||rec.LATEST||0}</td><td class="col-center">${rec.delta||rec.diff||''}</td></tr>`;
    }else if(tableName==='plan_config'){
      html+=`<tr><td>${esc(rec.field||'')}</td><td class="col-center">${esc(rec.value_a||'')}</td><td class="col-center">${esc(rec.value_b||'')}</td><td class="col-center"><span class="v2v-change-badge mod">MODIFY</span></td></tr>`;
    }else if(tableName==='supply'){
      html+=`<tr class="diff-${ctLower}"><td class="col-center"><span class="v2v-change-badge ${ctLower}">${badge}</span></td><td>${esc(key.PN_CODE||rec.PN_CODE||'')}</td><td>${esc(key.KITTING_DATE||key.WEEK||rec.WEEK||rec.TIME||'')}</td><td>${esc(rec.field||'KITTING_VALUE')}</td><td class="col-center">${rec.value_a||rec.PREV||''}</td><td class="col-center">${rec.value_b||rec.LATEST||''}</td><td class="col-center">${rec.diff||''}</td></tr>`;
    }else if(tableName==='switch'){
      html+=`<tr class="diff-${ctLower}"><td class="col-center"><span class="v2v-change-badge ${ctLower}">${badge}</span></td><td>${esc(key.LINE_CODE||rec.LINE_CODE||'')}</td><td>${esc(key.BEFORE_PN_CODE||rec.BEFORE_PN_CODE||'')}</td><td>${esc(key.AFTER_PN_CODE||rec.AFTER_PN_CODE||'')}</td><td>${esc(rec.field||'SWITCH_DURATION')}</td><td class="col-center">${rec.value_a||''}</td><td class="col-center">${rec.value_b||''}</td><td class="col-center">${rec.diff||''}</td></tr>`;
    }else if(tableName==='calendar'){
      html+=`<tr class="diff-${ctLower}"><td class="col-center"><span class="v2v-change-badge ${ctLower}">${badge}</span></td><td>${esc(key.LINE_CODE||rec.LINE_CODE||'')}</td><td>${esc(key.PLAN_TYPE||rec.PLAN_TYPE||'')}</td><td>${esc(key.PLAN_DATE||key.WEEK||rec._DATE||rec.TIME||'')}</td><td>${esc(key.SHIFT_NAME||rec.SHIFT_NAME||'')}</td><td>${esc(key.PLAN_ITEM||rec.PLAN_ITEM||'')}</td><td class="col-center">${rec.value_a||''}</td><td class="col-center">${rec.value_b||''}</td><td class="col-center">${rec.diff||''}</td></tr>`;
    }else if(tableName==='item'){
      const itemNo=rec.key?.ITEM_NO||rec.ITEM_NO||'Unknown'; const field=rec.field||''; const prev=rec.value_a||''; const latest=rec.value_b||'';
      html+=`<tr class="diff-${ctLower}"><td class="col-center"><span class="v2v-change-badge ${ctLower}">${badge}</span></td><td style="font-weight:600">${esc(itemNo)}</td><td>${esc(field)}</td><td>${esc(String(prev).substring(0,200))}</td><td>${esc(String(latest).substring(0,200))}</td></tr>`;
    }else if(tableName==='line'){
      html+=`<tr class="diff-${ctLower}"><td class="col-center"><span class="v2v-change-badge ${ctLower}">${badge}</span></td><td>${esc(key.LINE_CODE||rec.LINE_CODE||'')}</td><td>${esc(rec.field||'')}</td><td class="col-center">${esc(rec.value_a||'')}</td><td class="col-center">${esc(rec.value_b||'')}</td></tr>`;
    }else{
      html+=`<tr class="diff-${ctLower}">`; for(const [k,v] of Object.entries(rec).slice(0,8)) html+=`<td>${esc(String(v||'').substring(0,100))}</td>`; html+=`</tr>`;
    }
  }
  html+='</tbody></table></div>';

  if(pagination.total>pagination.page_size){
    const totalPages=Math.ceil(pagination.total/pagination.page_size);
    html+=`<div style="margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap"><button class="btn btn-sm" ${pagination.page<=1?'disabled':''} onclick="v2vState.currentPage--; loadV2VDetail('${tableName}')">‹ Prev</button><span style="font-size:12px">${pagination.page} / ${totalPages} (Total ${pagination.total})</span><button class="btn btn-sm" ${pagination.page>=totalPages?'disabled':''} onclick="v2vState.currentPage++; loadV2VDetail('${tableName}')">Next ›</button></div>`;
  }else{
    html+=`<div style="margin-top:8px;font-size:11px;color:#64748b">Total ${pagination.total||records.length} records</div>`;
  }
  wrapper.innerHTML=html;
}

function renderV2VBreadcrumb(){
  const el=document.getElementById('v2v-breadcrumb'); if(!el) return;
  let html=''; v2vState.breadcrumbs.forEach((bc,idx)=>{ if(idx>0) html+='<span class="v2v-breadcrumb-sep">›</span>'; const isLast=idx===v2vState.breadcrumbs.length-1; html+=`<span class="v2v-breadcrumb-item ${isLast?'active':''}" onclick="drillTo(${idx})">${bc.label} (${bc.granularity})</span>`; });
  el.innerHTML=html;
}
function drillTo(index){
  v2vState.breadcrumbs=v2vState.breadcrumbs.slice(0,index+1); const bc=v2vState.breadcrumbs[index]; v2vState.granularity=bc.granularity;
  document.querySelectorAll('.v2v-granularity-toggle button').forEach(b=>b.classList.toggle('active', b.dataset.granularity===bc.granularity));
  if (isHorizontalTable(v2vState.activeTable)) {
    loadHorizontalMatrix(v2vState.activeTable);
  } else {
    loadV2VDetail(v2vState.activeTable);
  }
}
function esc(s){ if(s==null) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
window.selectV2VTable=selectV2VTable; window.drillTo=drillTo; window.v2vState=v2vState; window.loadV2VDetail=loadV2VDetail; window.v2vInit=v2vInit;
window.downloadV2VCurrentView=downloadV2VCurrentView; window.exportV2VHtmlReport=exportV2VHtmlReport;
window.loadHorizontalMatrix=loadHorizontalMatrix;
window.saveV2VToStorage=saveV2VToStorage; window.clearV2VStorage=clearV2VStorage; window.tryRestoreV2VFromStorage=tryRestoreV2VFromStorage; window.updateRestoreBanner=updateRestoreBanner;
if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', v2vInit); }else{ v2vInit(); }
