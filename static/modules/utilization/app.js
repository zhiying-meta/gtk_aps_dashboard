/**
 * Utilization Report - Matrix view like Packout report
 * Line fixed, Version Type colored, thick border per line
 * Filters: Version Type, Line | Columns: toggles for extra info
 */

(() => {
  const API_STATUS = '/api/utilization/status';
  const API_META = '/api/utilization/meta';
  const API_PIVOT = '/api/utilization/pivot';
  const API_UPLOAD = '/api/utilization/upload';
  const API_DEMO = '/api/utilization/demo/load';
  const API_CLEAR = '/api/utilization/clear';

  let meta = null;
  let currentMode = 'day';
  let currentVersion = 'all';
  let pivotCache = null;
  let selectedVersionTypes = new Set(['Gated','Ungated']);
  let selectedLines = new Set();

  function esc(s){ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }
  function escAttr(s){ return esc(s).replace(/'/g,'&#39;'); }
  function getRoot(){ return document.getElementById('utilization-section'); }

  // Static offline mode like campus-planning-system/frontend/dist — fully preserves format and filtering
  function getStaticUtilDB(){
    try{
      if(window.STATIC_DB && window.STATIC_DB.utilization) return window.STATIC_DB.utilization;
      if(window.UTILIZATION_STATIC_DB) return window.UTILIZATION_STATIC_DB;
    }catch(e){}
    return null;
  }
  function isStaticUtilMode(){
    const db = getStaticUtilDB();
    return !!(db && (db.gated || db.ungated || db._pivot_day || db._pivot_shift));
  }

  async function fetchJSON(url, opts){
    const r = await fetch(url, opts);
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  }

  async function checkStatus(){
    const staticDB = getStaticUtilDB();
    if(staticDB && staticDB._meta){
      // Static mode: versions from _meta or keys
      const vers = staticDB._meta.versions || Object.keys(staticDB).filter(k=> !k.startsWith('_'));
      return {loaded: vers.length>0, versions: vers, details: {}, files_found: vers, statusBadge: 'static'};
    }
    if(staticDB && (staticDB.gated || staticDB.ungated)){
      const vers = Object.keys(staticDB).filter(k=> !k.startsWith('_'));
      return {loaded: vers.length>0, versions: vers, details: {}, files_found: vers, statusBadge: 'static'};
    }
    try{ return await fetchJSON(API_STATUS); }catch(e){ return {loaded:false}; }
  }

  async function loadMeta(){
    const staticDB = getStaticUtilDB();
    if(staticDB && staticDB._meta){
      // Use embedded meta for offline full filtering
      meta = {
        lines: staticDB._meta.lines || [],
        dates: [],
        shifts: [],
        versions: staticDB._meta.versions || [],
        date_min: staticDB._meta.dates?.min || '',
        date_max: staticDB._meta.dates?.max || ''
      };
      if(staticDB.gated && staticDB.gated.lines) meta.lines = [...new Set([...(meta.lines||[]), ...staticDB.gated.lines])];
      if(staticDB.ungated && staticDB.ungated.lines) meta.lines = [...new Set([...(meta.lines||[]), ...staticDB.ungated.lines])];
      return true;
    }
    try{
      meta = await fetchJSON(API_META);
      return true;
    }catch(e){ meta=null; return false; }
  }

  function statusBadgeHTML(status){
    const versions = (status && status.versions) ? status.versions : [];
    const filesFound = (status && status.files_found) ? status.files_found : [];
    const details = (status && status.details) ? status.details : {};
    let total = 0;
    Object.values(details).forEach(d=> total+=d.records_shift||0);

    const gatedReady = versions.includes('gated');
    const ungatedReady = versions.includes('ungated');
    const gatedFound = filesFound.includes('gated');
    const ungatedFound = filesFound.includes('ungated');

    const badge = (label, ready) => {
      if(ready) return `<span style="background:#dcfce7;color:#065f46;border:1px solid #86efac;padding:2px 8px;border-radius:12px;font-size:11px">✅ ${label}: Ready</span>`;
      else return `<span style="background:#fef2f2;color:#991b1b;border:1px solid #fecaca;padding:2px 8px;border-radius:12px;font-size:11px">❌ ${label}: Not Ready</span>`;
    };

    if(status && status.loaded){
      if(gatedReady && ungatedReady){
        return `<span style="display:inline-flex;gap:6px;align-items:center;flex-wrap:wrap">${badge('Gated', true)} ${badge('Ungated', true)} <span style="font-size:11px;color:#065f46;margin-left:4px">— ${total} recs — Showing both</span></span>`;
      }else if(gatedReady && !ungatedReady){
        return `<span style="display:inline-flex;gap:6px;align-items:center;flex-wrap:wrap">${badge('Gated', true)} ${badge('Ungated', false)} <span style="font-size:11px;color:#92400e;margin-left:4px">— ${total} recs — Showing Gated only (Ungated empty)</span></span>`;
      }else if(!gatedReady && ungatedReady){
        return `<span style="display:inline-flex;gap:6px;align-items:center;flex-wrap:wrap">${badge('Gated', false)} ${badge('Ungated', true)} <span style="font-size:11px;color:#92400e;margin-left:4px">— ${total} recs — Showing Ungated only (Gated empty)</span></span>`;
      }else{
        const vers = versions.join(', ')||'gated';
        return `<span class="util-status-badge ready">✅ Ready: ${vers} — ${total} recs</span>`;
      }
    }else if(filesFound.length>0){
      // Partial files but not yet computed
      const gatedInfo = gatedFound ? (gatedReady ? 'Ready' : 'Files found, not computed') : 'Not Ready';
      const ungatedInfo = ungatedFound ? (ungatedReady ? 'Ready' : 'Files found, not computed') : 'Not Ready';
      return `<span style="display:inline-flex;gap:6px;align-items:center;flex-wrap:wrap;background:#fffbeb;border:1px solid #fde68a;padding:4px 8px;border-radius:12px">
        ${gatedFound? `<span style="background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:10px;font-size:10px">⚠️ Gated: ${gatedInfo}</span>` : `<span style="background:#fef2f2;color:#991b1b;padding:2px 6px;border-radius:10px;font-size:10px">❌ Gated: Not Ready</span>`}
        ${ungatedFound? `<span style="background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:10px;font-size:10px">⚠️ Ungated: ${ungatedInfo}</span>` : `<span style="background:#fef2f2;color:#991b1b;padding:2px 6px;border-radius:10px;font-size:10px">❌ Ungated: Not Ready</span>`}
        <span style="font-size:10px;color:#92400e">— click Apply to compute (first time ~40s)</span></span>`;
    }else{
      return `<span style="display:inline-flex;gap:6px;align-items:center;flex-wrap:wrap"><span style="background:#fef2f2;color:#991b1b;border:1px solid #fecaca;padding:2px 8px;border-radius:12px;font-size:11px">❌ Gated: Not Ready</span><span style="background:#fef2f2;color:#991b1b;border:1px solid #fecaca;padding:2px 8px;border-radius:12px;font-size:11px">❌ Ungated: Not Ready</span><span style="font-size:11px;color:#64748b">No data — upload calendar+schedule, or zip, or demo</span></span>`;
    }
  }

  function updateCardStatuses(status){
    // Update per-card status divs based on latest status — ensures after clear/upload, card shows correct Ready/Not Ready
    const filesFound = (status && status.files_found) ? status.files_found : [];
    const loadedVers = (status && status.versions) ? status.versions : [];
    const hasGated = filesFound.includes('gated');
    const hasUngated = filesFound.includes('ungated');
    const isGatedReady = loadedVers.includes('gated');
    const isUngatedReady = loadedVers.includes('ungated');

    const gatedEl = document.getElementById('status-gated-files');
    const ungatedEl = document.getElementById('status-ungated-files');
    if(gatedEl){
      if(isGatedReady){
        gatedEl.style.background='#dcfce7'; gatedEl.style.border='1px solid #86efac'; gatedEl.style.color='#065f46';
        gatedEl.innerHTML='<span>✅ Gated: Ready — computed and will be shown in matrix</span><span style="font-size:10px;opacity:0.8">Status: Ready</span>';
      }else if(hasGated){
        gatedEl.style.background='#fef3c7'; gatedEl.style.border='1px solid #fde68a'; gatedEl.style.color='#92400e';
        gatedEl.innerHTML='<span>⚠️ Gated: Partial — files present but not computed, re-upload to complete</span><span style="font-size:10px;opacity:0.8">Status: Partial</span>';
      }else{
        gatedEl.style.background='#fef2f2'; gatedEl.style.border='1px solid #fecaca'; gatedEl.style.color='#991b1b';
        gatedEl.innerHTML='<span>❌ Gated: Not Ready — no files uploaded, matrix will show only Ungated if available. Re-upload supported.</span><span style="font-size:10px;opacity:0.8">Status: Not Ready</span>';
      }
    }
    if(ungatedEl){
      if(isUngatedReady){
        ungatedEl.style.background='#dcfce7'; ungatedEl.style.border='1px solid #86efac'; ungatedEl.style.color='#065f46';
        ungatedEl.innerHTML='<span>✅ Ungated: Ready — computed and will be shown</span><span style="font-size:10px;opacity:0.8">Status: Ready</span>';
      }else if(hasUngated){
        ungatedEl.style.background='#fef3c7'; ungatedEl.style.border='1px solid #fde68a'; ungatedEl.style.color='#92400e';
        ungatedEl.innerHTML='<span>⚠️ Ungated: Partial — files present but not computed</span><span style="font-size:10px;opacity:0.8">Status: Partial</span>';
      }else{
        ungatedEl.style.background='#fef2f2'; ungatedEl.style.border='1px solid #fecaca'; ungatedEl.style.color='#991b1b';
        ungatedEl.innerHTML='<span>❌ Ungated: Not Ready — no files uploaded, matrix will show only Gated if available (empty allowed). Re-upload supported.</span><span style="font-size:10px;opacity:0.8">Status: Not Ready</span>';
      }
    }
  }

  function buildUploadHTML(status){
    const filesFound = (status && status.files_found) ? status.files_found : [];
    const hasGated = filesFound.includes('gated');
    const hasUngated = filesFound.includes('ungated');
    const loadedVers = (status && status.versions) ? status.versions : [];
    const isGatedReady = loadedVers.includes('gated');
    const isUngatedReady = loadedVers.includes('ungated');
    return `
      <div class="section">
        <div class="section-header">
          <span class="section-title">⚙️ Line Utilization — Upload (Independent Modules)</span>
          <span id="util-status-badge">${statusBadgeHTML(status)}</span>
        </div>
        <div style="padding:12px;background:#f8fafc;border:1px dashed #cbd5e1;border-radius:6px;font-size:12px;color:#475569;margin-bottom:12px">
          <div><b>Formula:</b> <code>Capacity = UPH × Efficiency × Working Hours</code> | <code>Load = Σ INPUT (schedule)</code> | <code>Util% = Load / Capacity</code> capped at 100% — Each module (Gated / Ungated) uploads independently. If only Gated uploaded, show Gated only, Ungated stays empty (Not Ready).</div>
        </div>

        <!-- What to upload & Schema — concise, View Schema is single source of truth -->
        <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:14px;margin-bottom:14px">
          <div style="font-weight:700;font-size:13px;margin-bottom:8px;color:#0c4a6e">📋 What to Upload — Required Files (English)</div>
          <div style="font-size:12px;color:#334155;line-height:1.6">
            <div>• <b>Per independent module (Gated / Ungated)</b> you need <b>2 files</b>: <code>Calendar (工作日历快照.xlsx)</code> + <code>Schedule (排产结果表.xlsx)</code> — or 1 zip containing both.</div>
            <div>• <b>Calendar</b> defines capacity: <code>Capacity = UPH × Efficiency × Working Hours</code> per line/date/shift.</div>
            <div>• <b>Schedule</b> defines load: <code>Load = Σ INPUT</code> per line/date/shift.</div>
            <div>• <b>Utilization = Load / Capacity</b> capped at 100%. You can upload only Gated — matrix will show Gated only, Ungated stays <b>Not Ready (empty)</b>.</div>
          </div>
          <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:#fff;border:1px dashed #cbd5e1;border-radius:6px;padding:8px">
            <b style="font-size:11px">📦 Download (no duplication):</b>
            <a href="/api/utilization/templates/template" class="btn btn-sm">📦 Template Zip (Empty)</a>
            <a href="/api/utilization/templates/demo" class="btn btn-sm" style="background:#fef3c7;border-color:#fde68a;color:#92400e">📦 Demo Zip (Gated) — Downloadable like Template</a>
            <button id="btn-view-schema" class="btn btn-sm util-btn-outline">🔍 View Json Schema (Single Source of Truth)</button>
            <span style="font-size:10px;color:#64748b">Template and Demo are downloadable like other modules. Click View Json Schema to see required columns and formulas — no duplicate schema shown elsewhere.</span>
          </div>
          <div id="schema-detail" style="display:none;margin-top:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px;font-size:11px;max-height:400px;overflow:auto;white-space:pre-wrap"></div>
        </div>


        <div class="util-upload-grid">
          <!-- Gated independent one-click -->
          <div class="util-upload-card" id="card-gated" style="border:2px dashed #f59e0b;background:#fffbeb">
            <div class="util-upload-label">🟡 Gated — One-Click Upload <span style="font-size:10px;background:#f59e0b;color:#fff;padding:1px 6px;border-radius:8px">Independent</span></div>
            <div class="util-upload-hint">Select 2 xlsx (calendar + schedule) or 1 zip containing both. Auto-detects type. After upload, matrix shows immediately; Ungated can be empty.</div>
            <input type="file" id="input-gated" accept=".xlsx,.zip" multiple style="margin:8px 0">
            <div id="fname-gated" style="font-size:11px;color:#92400e;margin-top:6px;min-height:16px;word-break:break-all"></div>
            <div style="margin-top:8px;display:flex;gap:8px;justify-content:center;align-items:center;flex-wrap:wrap">
              <button class="util-btn" id="btn-upload-gated" disabled style="background:#f59e0b;border-color:#f59e0b">▶ Upload Gated</button>
              <button class="util-btn util-btn-outline" id="btn-clear-gated" style="border-color:#ef4444;color:#ef4444" title="Clear Gated cache — will become Not Ready">🗑️ Clear Gated</button>
              <span id="msg-gated" style="font-size:11px;color:#64748b"></span>
            </div>
            <div id="status-gated-files" style="font-size:11px;margin-top:8px;padding:6px 8px;border-radius:6px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;${isGatedReady? 'background:#dcfce7;color:#065f46;border:1px solid #86efac' : (hasGated? 'background:#fef3c7;color:#92400e;border:1px solid #fde68a' : 'background:#fef2f2;color:#991b1b;border:1px solid #fecaca')}">
              <span>${isGatedReady? '✅ Gated: Ready — computed and will be shown in matrix' : (hasGated? '⚠️ Gated: Partial — files present but not computed, re-upload to complete' : '❌ Gated: Not Ready — no files uploaded, matrix will show only Ungated if available')}</span>
              <span style="font-size:10px;opacity:0.8">${isGatedReady? 'Status: Ready' : 'Status: Not Ready'}</span>
            </div>
          </div>

          <!-- Ungated independent one-click -->
          <div class="util-upload-card" id="card-ungated" style="border:2px dashed #10b981;background:#ecfdf5">
            <div class="util-upload-label">🟢 Ungated — One-Click Upload <span style="font-size:10px;background:#10b981;color:#fff;padding:1px 6px;border-radius:8px">Independent</span></div>
            <div class="util-upload-hint">Same support: 2 files or zip one-click. Can be uploaded separately; if Gated missing, only Ungated will be displayed. If empty, matrix shows only uploaded version.</div>
            <input type="file" id="input-ungated" accept=".xlsx,.zip" multiple style="margin:8px 0">
            <div id="fname-ungated" style="font-size:11px;color:#065f46;margin-top:6px;min-height:16px;word-break:break-all"></div>
            <div style="margin-top:8px;display:flex;gap:8px;justify-content:center;align-items:center;flex-wrap:wrap">
              <button class="util-btn" id="btn-upload-ungated" disabled style="background:#10b981;border-color:#10b981">▶ Upload Ungated</button>
              <button class="util-btn util-btn-outline" id="btn-clear-ungated" style="border-color:#ef4444;color:#ef4444" title="Clear Ungated cache — will become Not Ready">🗑️ Clear Ungated</button>
              <span id="msg-ungated" style="font-size:11px;color:#64748b"></span>
            </div>
            <div id="status-ungated-files" style="font-size:11px;margin-top:8px;padding:6px 8px;border-radius:6px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;${isUngatedReady? 'background:#dcfce7;color:#065f46;border:1px solid #86efac' : (hasUngated? 'background:#fef3c7;color:#92400e;border:1px solid #fde68a' : 'background:#fef2f2;color:#991b1b;border:1px solid #fecaca')}">
              <span>${isUngatedReady? '✅ Ungated: Ready — computed and will be shown' : (hasUngated? '⚠️ Ungated: Partial — files present but not computed' : '❌ Ungated: Not Ready — no files uploaded, matrix will show only Gated if available (empty allowed)')}</span>
              <span style="font-size:10px;opacity:0.8">${isUngatedReady? 'Status: Ready' : 'Status: Not Ready'}</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function buildMatrixSection(){
    return `
      <div class="section">
        <div class="section-header">
          <span class="section-title">📊 Line Utilization — Matrix</span>
          <div class="section-actions">
            <span id="util-matrix-badge" style="font-size:11px;color:#64748b"></span>
            <span style="font-size:11px;display:flex;gap:6px;align-items:center">
              <span style="background:transparent;color:#94a3b8;padding:2px 6px;border-radius:10px;border:1px dashed #e2e8f0">0% no color</span>
              <span style="background:#fef2f2;color:#991b1b;padding:2px 6px;border-radius:10px;border:1px solid #fecaca">0-60% red</span>
              <span style="background:#fffbeb;color:#92400e;padding:2px 6px;border-radius:10px">60-80% yellow</span>
              <span style="background:#ecfdf5;color:#065f46;padding:2px 6px;border-radius:10px">80%+ green</span>
            </span>
            <button id="btn-download-static-util" class="btn btn-sm btn-outline" style="margin-left:8px">📥 Download Static HTML</button>
          </div>
        </div>

        <div class="toolbar" style="border:none;padding:8px 0">
          <div class="panels-row">
            <div class="panel panel-filter">
              <div class="panel-label">🔍 Filters <span style="font-weight:400;text-transform:none;color:#94a3b8"> — Filter functionality: version type & line</span> <span id="btn-clear-util-filters" style="font-size:10px;font-weight:400;cursor:pointer;color:#64748b;margin-left:6px;padding:1px 6px;border:1px solid #cbd5e1;border-radius:3px">✕ Clear</span></div>
              <div class="filter-row">
                <div class="filter-group dropdown-filter">
                  <label>Version Type <span id="util-vtype-count" class="tag-count"></span></label>
                  <button class="dropdown-btn" id="util-vtype-btn">All</button>
                  <div class="dropdown-menu" id="util-vtype-menu"></div>
                </div>
                <div class="filter-group dropdown-filter">
                  <label>Line <span id="util-line-count" class="tag-count"></span></label>
                  <button class="dropdown-btn" id="util-line-btn">All</button>
                  <div class="dropdown-menu" id="util-line-menu"></div>
                </div>
                <div class="filter-group">
                  <label>Date From</label>
                  <input type="date" id="util-filter-from" style="padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px">
                </div>
                <div class="filter-group">
                  <label>Date To</label>
                  <input type="date" id="util-filter-to" style="padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px">
                </div>
                <div class="filter-group">
                  <label>&nbsp;</label>
                  <button class="util-btn" id="btn-apply-pivot">Apply</button>
                </div>
              </div>
            </div>
            <div class="panel panel-cols">
              <div class="panel-label">📋 Columns <span style="font-weight:400;text-transform:none;color:#94a3b8"> — Column dimension: Day / Shift like I/O Report</span></div>
              <div class="cols-row" style="align-items:center">
                <div class="util-toggle-group">
                  <button id="btn-mode-day" class="${currentMode==='day'?'active':''}">Day</button>
                  <button id="btn-mode-shift" class="${currentMode==='shift'?'active':''}">Shift</button>
                </div>
                <span style="font-size:11px;color:#64748b;margin-left:8px">Switches date columns between daily aggregated and per-shift</span>
              </div>
            </div>
          </div>
        </div>

        <div id="util-matrix-wrapper" class="table-wrapper" style="max-height:calc(100vh - 320px)">
          <div style="text-align:center;padding:30px;color:#94a3b8">Loading matrix...</div>
        </div>
      </div>
    `;
  }

  function setupVersionTypeDropdown(){
    const btn = document.getElementById('util-vtype-btn');
    const menu = document.getElementById('util-vtype-menu');
    const cnt = document.getElementById('util-vtype-count');
    if(!btn||!menu) return;
    const allTypes = ['Gated','Ungated'];
    function renderMenu(){
      const total = allTypes.length;
      const selected = selectedVersionTypes.size;
      const isAll = selected===total;
      cnt.textContent = isAll ? '' : `${selected}`;
      btn.textContent = isAll ? `All ${total}` : (selected===0?'(none)':`${selected} selected`);
      let html = `<div class="dropdown-all"><label><input type="checkbox" id="vtype-all" ${isAll?'checked':''}> All (${total})</label></div>`;
      allTypes.forEach(v=>{
        const checked = selectedVersionTypes.has(v);
        html += `<label><input type="checkbox" data-val="${escAttr(v)}" ${checked?'checked':''}> <span class="type-badge type-${esc(v)}">${esc(v)}</span></label>`;
      });
      menu.innerHTML = html;
      const allCb = menu.querySelector('#vtype-all');
      if(allCb){
        allCb.addEventListener('change', (e)=>{
          if(e.target.checked){
            selectedVersionTypes = new Set(allTypes);
          }else{
            selectedVersionTypes.clear();
          }
          renderMenu();
          applyPivot();
        });
      }
      menu.querySelectorAll('input[data-val]').forEach(cb=>{
        cb.addEventListener('change', (e)=>{
          const v = e.target.dataset.val;
          if(e.target.checked) selectedVersionTypes.add(v);
          else selectedVersionTypes.delete(v);
          renderMenu();
          applyPivot();
        });
      });
    }
    btn.onclick = (e)=>{ e.stopPropagation(); menu.classList.toggle('open'); renderMenu(); };
    document.addEventListener('click', ()=> menu.classList.remove('open'));
    menu.onclick = (e)=> e.stopPropagation();
    renderMenu();
  }

  function setupLineDropdown(lines){
    const btn = document.getElementById('util-line-btn');
    const menu = document.getElementById('util-line-menu');
    const cnt = document.getElementById('util-line-count');
    if(!btn||!menu) return;
    const allLines = lines || [];
    let searchTerm = '';

    function renderMenu(){
      const total = allLines.length;
      const isAll = selectedLines.size===0;
      cnt.textContent = isAll ? '' : `${selectedLines.size}`;
      btn.textContent = isAll ? `All ${total}` : `${selectedLines.size} selected`;
      const filtered = searchTerm ? allLines.filter(l=> l.toLowerCase().includes(searchTerm.toLowerCase())) : allLines;
      let html = `<div class="dropdown-search"><input type="text" id="util-line-search" placeholder="Search line..." value="${escAttr(searchTerm)}"></div>`;
      html += `<div class="dropdown-all"><label><input type="checkbox" id="line-all" ${isAll?'checked':''}> All (${total})</label></div>`;
      filtered.forEach(l=>{
        const checked = isAll || selectedLines.has(l);
        html += `<label><input type="checkbox" data-val="${escAttr(l)}" ${checked?'checked':''}> ${esc(l)}</label>`;
      });
      if(filtered.length===0) html += `<div style="padding:8px;color:#94a3b8;font-size:12px">No match</div>`;
      menu.innerHTML = html;

      const sInput = menu.querySelector('#util-line-search');
      if(sInput){
        sInput.focus();
        sInput.addEventListener('input', (e)=>{
          searchTerm = e.target.value;
          renderMenu();
        });
        sInput.addEventListener('click', (e)=> e.stopPropagation());
      }

      const allCb = menu.querySelector('#line-all');
      if(allCb){
        allCb.addEventListener('change', (e)=>{
          if(e.target.checked){
            selectedLines.clear();
          }else{
            // Uncheck all -> keep existing selection? For simplicity, select all individually (still means all, but we will treat as all)
            // To show none, user can uncheck all individually
            selectedLines = new Set(allLines);
          }
          renderMenu();
          applyPivot();
        });
      }

      menu.querySelectorAll('input[data-val]').forEach(cb=>{
        cb.addEventListener('change', (e)=>{
          const v = e.target.dataset.val;
          if(e.target.checked){
            if(selectedLines.size===0){
              // Was all, now we need to create set of all except those not checked
              // Actually if was all (empty), and user checks one (which already checked), we need to convert to set containing all except unchecked ones
              // Simpler: when was all and user unchecks one, we want to have all except that one
              // But this handler is for checking, so if was all, checking does nothing (already all)
              // So for checking when was all, do nothing
            }else{
              selectedLines.add(v);
              if(selectedLines.size===allLines.length) selectedLines.clear();
            }
          }else{
            if(selectedLines.size===0){
              // Was all, now unchecking one -> set = all except this
              selectedLines = new Set(allLines);
              selectedLines.delete(v);
            }else{
              selectedLines.delete(v);
            }
          }
          renderMenu();
          applyPivot();
        });
      });
    }

    btn.onclick = (e)=>{ e.stopPropagation(); menu.classList.toggle('open'); if(menu.classList.contains('open')) renderMenu(); };
    document.addEventListener('click', ()=> menu.classList.remove('open'));
    menu.onclick = (e)=> e.stopPropagation();
    renderMenu();
  }

  function renderMatrix(pivot){
    pivotCache = pivot;
    const cols = pivot.columns || [];
    const rows = pivot.rows || [];
    const detail = pivot.detail || {};
    const wrapper = document.getElementById('util-matrix-wrapper');
    if(!wrapper) return;

    if(pivot.not_ready){
      const reqVer = pivot.requested_version || 'requested version';
      wrapper.innerHTML = `<div style="text-align:center;padding:30px;color:#991b1b;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;margin:12px">
        <div style="font-weight:600;margin-bottom:6px">❌ ${esc(reqVer.charAt(0).toUpperCase()+reqVer.slice(1))}: Not Ready</div>
        <div style="font-size:12px;color:#92400e">${esc(pivot.message||'No data')}<br>Other module may be Ready — check upload status above. Matrix shows only Ready modules when Not Ready.</div>
      </div>`;
      // Also update badge to reflect not ready
      const badge = document.getElementById('util-matrix-badge');
      if(badge){
        badge.innerHTML = `<span style="color:#991b1b">❌ ${esc(reqVer)}: Not Ready — empty</span> | <span style="color:#065f46">Ready modules: ${(meta&&meta.versions? meta.versions.join(', ') : 'none')}</span>`;
      }
      return;
    }

    if(rows.length===0){
      // Determine if it's because one module not ready
      const readyVers = (meta && meta.versions) ? meta.versions : [];
      const gatedReady = readyVers.map(v=>v.toLowerCase()).includes('gated');
      const ungatedReady = readyVers.map(v=>v.toLowerCase()).includes('ungated');
      let extraInfo = '';
      if(!gatedReady || !ungatedReady){
        extraInfo = `<div style="margin-top:8px;font-size:11px;color:#991b1b">Status: ${gatedReady? '✅ Gated: Ready' : '❌ Gated: Not Ready (empty)'} | ${ungatedReady? '✅ Ungated: Ready' : '❌ Ungated: Not Ready (empty)'} — Matrix shows only Ready modules.</div>`;
      }
      wrapper.innerHTML = `<div style="text-align:center;padding:30px;color:#94a3b8">No matching data. Adjust filters.${extraInfo}</div>`;
      return;
    }

    const frozenCols = [
      {key:'line_code', label:'Line', width:130},
      {key:'version_type', label:'Version Type', width:110},
    ];
    const allFrozen = frozenCols;
    let left = 0;
    allFrozen.forEach(c=>{ c._left = left; left+=c.width; });
    const dividerLeft = left;

    let thead = '<tr>';
    allFrozen.forEach(c=>{
      thead += `<th class="frozen" style="left:${c._left}px;min-width:${c.width}px">${esc(c.label)}</th>`;
    });
    thead += `<th class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px"></th>`;
    cols.forEach(col=>{
      let label = col;
      let sub = '';
      if(col.includes('|')){
        const parts = col.split('|');
        label = parts[0];
        sub = parts[1];
        try{
          const d = new Date(label);
          if(!isNaN(d)) label = `${d.getMonth()+1}/${d.getDate()}`;
        }catch(e){}
      }else{
        try{
          const d = new Date(col);
          if(!isNaN(d)) label = `${d.getMonth()+1}/${d.getDate()}`;
        }catch(e){}
      }
      thead += `<th style="min-width:68px;text-align:center" title="${esc(col)}">${esc(label)}${sub?`<br><span style="font-size:9px;color:#cbd5e1">${esc(sub)}</span>`:''}</th>`;
    });
    thead += '</tr>';

    let tbody = '';
    rows.forEach(r=>{
      const isNewLine = r.is_new_line;
      const vType = r.version_type||'';
      const rowClass = `row-${esc(vType)} ${isNewLine?'row-new-line':''}`;
      tbody += `<tr class="${rowClass}">`;
      allFrozen.forEach(c=>{
        const isLast = c===allFrozen[allFrozen.length-1];
        const extraCls = isLast ? ' frozen-last' : '';
        let val = '';
        if(c.key==='line_code') val = esc(r.line_code);
        else if(c.key==='version_type') val = `<span class="type-badge type-${esc(vType)}">${esc(vType)}</span>`;
        tbody += `<td class="frozen data-cell${extraCls}" style="left:${c._left}px;min-width:${c.width}px">${val}</td>`;
      });
      tbody += `<td class="divider-col frozen" style="left:${dividerLeft}px"></td>`;
      cols.forEach(col=>{
        const keyStr = `${r.line_code}||${vType}`;
        const cellDetail = detail[keyStr] && detail[keyStr][col];
        const cellVal = r[col];
        if(cellVal==null){
          tbody += `<td class="data-cell" style="background:#f8fafc"></td>`;
        }else{
          const raw = cellDetail ? cellDetail.util_raw : cellVal;
          const load = cellDetail ? cellDetail.load : '';
          const cap = cellDetail ? cellDetail.capacity : '';
          let cls = '';
          // New coloring: 0% no color, 0-60% red, 60-80% yellow, 80%+ green
          if(cellVal===0 || cellVal==null){
            cls='util-cell-zero';
          }else if(cellVal<60){
            cls='util-cell-red';
          }else if(cellVal<80){
            cls='util-cell-yellow';
          }else{
            cls='util-cell-green';
          }
          // No (raw) after 100%, just show capped %
          let display = `${Math.round(cellVal)}%`;
          if(cellVal===0) display = '0%';
          tbody += `<td class="data-cell ${cls}" title="Line:${esc(r.line_code)} Ver:${esc(vType)} Date:${esc(col)} Load:${load} Cap:${cap} Raw:${raw}% (capped at 100%)">${display}</td>`;
        }
      });
      tbody += '</tr>';
    });

    wrapper.innerHTML = `<table><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;

    const badge = document.getElementById('util-matrix-badge');
    if(badge){
      const truncInfo = pivot.truncated ? ` (showing first ${pivot.total_cols}/${pivot.total_cols_before} cols, use Date filters to see more)` : '';
      // Determine ready status from meta or pivot.versions
      const readyVers = (meta && meta.versions) ? meta.versions : (pivot.versions||[]);
      const gatedReady = readyVers.map(v=>v.toLowerCase()).includes('gated');
      const ungatedReady = readyVers.map(v=>v.toLowerCase()).includes('ungated');
      let readyInfo = '';
      if(gatedReady && ungatedReady){
        readyInfo = '✅ Gated: Ready | ✅ Ungated: Ready — Showing both';
      }else if(gatedReady && !ungatedReady){
        readyInfo = '✅ Gated: Ready | ❌ Ungated: Not Ready (empty) — Showing Gated only';
      }else if(!gatedReady && ungatedReady){
        readyInfo = '❌ Gated: Not Ready (empty) | ✅ Ungated: Ready — Showing Ungated only';
      }else if(pivot.rows && pivot.rows.length===0){
        readyInfo = '❌ No data — upload at least one module';
      }
      badge.innerHTML = `${pivot.total_lines} rows × ${pivot.total_cols} cols${truncInfo} | Thick border per Line<br><span style="font-size:10px;color:#64748b">${readyInfo}</span>`;
    }
  }

  async function applyPivot(){
    const from = document.getElementById('util-filter-from')?.value || '';
    const to = document.getElementById('util-filter-to')?.value || '';
    let versionParam = 'all';
    if(selectedVersionTypes.size===1){
      versionParam = Array.from(selectedVersionTypes)[0].toLowerCase();
    }else if(selectedVersionTypes.size===0){
      document.getElementById('util-matrix-wrapper').innerHTML = `<div style="text-align:center;padding:30px;color:#94a3b8">No version type selected</div>`;
      return;
    }

    let lineParam = '';
    if(selectedLines.size>0){
      lineParam = Array.from(selectedLines).join(',');
    }

    const params = new URLSearchParams({
      mode: currentMode,
      version: versionParam,
      line_code: lineParam,
      date_from: from,
      date_to: to,
    });

    const wrapper = document.getElementById('util-matrix-wrapper');
    if(wrapper) wrapper.innerHTML = `<div style="text-align:center;padding:30px;color:#94a3b8">Loading pivot matrix...</div>`;

    try{
      // Static offline mode: use embedded pivot data with client-side filtering (full format and filtering preserved like campus-planning-system/dist)
      const staticDB = getStaticUtilDB();
      if(staticDB && (staticDB._pivot_day || staticDB._pivot_shift)){
        const pivotData = currentMode==='day' ? (staticDB._pivot_day || staticDB._pivot_shift) : (staticDB._pivot_shift || staticDB._pivot_day);
        if(pivotData){
          // Client-side filtering for static mode (version, line, date)
          let filtered = {
            columns: [...(pivotData.columns||[])],
            rows: [...(pivotData.rows||[])],
            detail: {...(pivotData.detail||{})},
            versions: pivotData.versions||[],
            lines: pivotData.lines||[],
            total_lines: pivotData.total_lines||0,
            total_cols: pivotData.total_cols||0,
            total_cols_before: pivotData.total_cols_before||0,
            truncated: pivotData.truncated||false,
            mode: pivotData.mode||currentMode
          };
          // Filter by version
          if(versionParam!=='all'){
            filtered.rows = filtered.rows.filter(r=> (r.version_type||'').toLowerCase()===versionParam);
          }else{
            // Filter by selectedVersionTypes set
            if(selectedVersionTypes.size>0 && selectedVersionTypes.size<2){
              const sel = Array.from(selectedVersionTypes).map(v=>v.toLowerCase());
              filtered.rows = filtered.rows.filter(r=> sel.includes((r.version_type||'').toLowerCase()));
            }
          }
          // Filter by line
          if(lineParam){
            const lineFilters = lineParam.toLowerCase().split(',').map(s=>s.trim()).filter(Boolean);
            if(lineFilters.length>0){
              filtered.rows = filtered.rows.filter(r=>{
                const lc = (r.line_code||'').toLowerCase();
                return lineFilters.some(f=> lc.includes(f));
              });
            }
          }
          // Filter columns by date
          if(from || to){
            filtered.columns = pivotData.columns.filter(col=>{
              let d = col;
              if(col.includes('|')) d = col.split('|')[0];
              if(from && d < from) return false;
              if(to && d > to) return false;
              return true;
            });
            // Filter rows to only keep cols that remain
            filtered.rows = filtered.rows.map(r=>{
              const nr = {...r};
              // Keep only filtered cols values, remove others? For simplicity keep all but render will only show filtered cols
              return nr;
            });
            filtered.total_cols = filtered.columns.length;
          }
          filtered.total_lines = filtered.rows.length;
          renderMatrix(filtered);
          return;
        }
      }
      const res = await fetchJSON(`${API_PIVOT}?${params.toString()}`);
      renderMatrix(res);
    }catch(e){
      if(wrapper) wrapper.innerHTML = `<div style="color:#dc2626;padding:12px">Error: ${esc(e.message)}</div>`;
    }
  }

  async function render(){
    const root = getRoot();
    if(!root) return;
    const status = await checkStatus();

    // Auto adjust selected version types based on ready status: show only ready modules
    if(status && status.versions && status.versions.length>0){
      // If only one version ready, select only that one -> matrix shows only that, other stays empty (Not Ready)
      if(status.versions.length===1){
        const v = status.versions[0];
        selectedVersionTypes = new Set([v.charAt(0).toUpperCase()+v.slice(1).toLowerCase()]);
      }else{
        // Both ready
        selectedVersionTypes = new Set(status.versions.map(v=> v.charAt(0).toUpperCase()+v.slice(1).toLowerCase()));
      }
    }else{
      // No ready versions yet, keep both selected but will show empty
      selectedVersionTypes = new Set(['Gated','Ungated']);
    }

    let html = '';
    html += buildUploadHTML(status);
    html += buildMatrixSection();
    root.innerHTML = html;

    await loadMeta();
    const lines = (meta && meta.lines) ? meta.lines : [];

    setupVersionTypeDropdown();
    setupLineDropdown(lines);

    // ===== Independent one-click per version (Gated / Ungated) =====
    const bindIndependentUpload = (ver) => {
      const inputId = `input-${ver}`;
      const btnId = `btn-upload-${ver}`;
      const fnameId = `fname-${ver}`;
      const msgId = `msg-${ver}`;
      const input = document.getElementById(inputId);
      const btn = document.getElementById(btnId);
      const fnameEl = document.getElementById(fnameId);
      const msgEl = document.getElementById(msgId);
      let selectedFiles = [];

      if (!input || !btn) return;

      input.addEventListener('change', () => {
        selectedFiles = Array.from(input.files || []);
        if (selectedFiles.length === 0) {
          if (fnameEl) fnameEl.textContent = '';
          btn.disabled = true;
          return;
        }
        const names = selectedFiles.map(f => f.name).join(', ');
        if (fnameEl) fnameEl.textContent = `✓ ${selectedFiles.length} file(s): ${names}`;
        btn.disabled = false;
      });

      btn.addEventListener('click', async () => {
        if (selectedFiles.length === 0) {
          alert('Please select files first (calendar + schedule or zip)');
          return;
        }
        if (msgEl) msgEl.textContent = 'Uploading (independent module)...';
        try {
          const fd = new FormData();
          selectedFiles.forEach(f => fd.append('file', f));
          // Force version to this module, so backend only touches this version folder
          const r = await fetch(`${API_UPLOAD}?version=${ver}`, { method: 'POST', body: fd });
          const j = await r.json();
          if (!r.ok) throw new Error(j.error || 'upload failed');
          const res = j.results && j.results[ver] ? j.results[ver] : {};
          if (res.ready) {
            if (msgEl) msgEl.textContent = `✅ ${ver} Ready: ${res.lines || '?'} lines — can be displayed immediately, other module can stay empty`;
          } else if (res.partial) {
            if (msgEl) msgEl.textContent = `⚠️ Partial: cal=${res.has_calendar} sched=${res.has_schedule} — upload missing file to complete. Need both files to display`;
          } else {
            if (msgEl) msgEl.textContent = `✅ Uploaded — ${JSON.stringify(j.results || j)}`;
          }
          // Refresh status and matrix after upload — ensure per-card Ready/Not Ready updated correctly
          setTimeout(async () => {
            try {
              const st = await checkStatus();
              const badge = document.getElementById('util-status-badge');
              if (badge) badge.innerHTML = statusBadgeHTML(st);
              // Update per-card status divs using single source helper
              updateCardStatuses(st);
              if (st.loaded) {
                await loadMeta();
                const newLines = (meta && meta.lines) ? meta.lines : lines;
                setupLineDropdown(newLines);
                // Adjust selectedVersionTypes to remaining ready modules for correct matrix display
                if(st.versions && st.versions.length>0){
                  if(st.versions.length===1){
                    selectedVersionTypes = new Set([st.versions[0].charAt(0).toUpperCase()+st.versions[0].slice(1).toLowerCase()]);
                  }else{
                    selectedVersionTypes = new Set(st.versions.map(v=> v.charAt(0).toUpperCase()+v.slice(1).toLowerCase()));
                  }
                  setupVersionTypeDropdown();
                }
                applyPivot();
              } else {
                // No ready versions yet — show empty matrix with Not Ready hint
                const wrapper = document.getElementById('util-matrix-wrapper');
                if(wrapper) wrapper.innerHTML = `<div style="text-align:center;padding:30px;color:#991b1b;background:#fef2f2;border:1px solid #fecaca;border-radius:6px">❌ No Ready modules. Upload at least one module (Gated or Ungated).<br><span style="font-size:11px;color:#92400e">Current status: ${st.files_found && st.files_found.length>0 ? 'Files found but not computed — re-upload to complete' : 'No files'}</span></div>`;
                const mbadge = document.getElementById('util-matrix-badge');
                if(mbadge) mbadge.innerHTML = `<span style="color:#991b1b">❌ Gated: Not Ready | ❌ Ungated: Not Ready — empty</span>`;
              }
            } catch (e) { console.warn(e); }
          }, 800);
        } catch (e) {
          if (msgEl) msgEl.textContent = '❌ ' + e.message;
        }
      });
    };

    bindIndependentUpload('gated');
    bindIndependentUpload('ungated');

    // ===== Clear functionality — set module to Not Ready, support re-upload =====
    const resetUploadInput = (ver) => {
      const input = document.getElementById(`input-${ver}`);
      const fname = document.getElementById(`fname-${ver}`);
      const uploadBtn = document.getElementById(`btn-upload-${ver}`);
      if(input) input.value = '';
      if(fname) fname.textContent = '';
      if(uploadBtn) uploadBtn.disabled = true;
      // Also clear internal selectedFiles by triggering change event? We handle via closure reset in bindUpload, but we reset via input event
      // For safety, set msg to hint re-upload
      const msg = document.getElementById(`msg-${ver}`);
      if(msg) msg.textContent = 'Cleared — you can re-select files and upload again';
    };

    const bindClear = (ver) => {
      const btn = document.getElementById(`btn-clear-${ver}`);
      if(!btn) return;
      btn.addEventListener('click', async () => {
        const confirmMsg = `Clear ${ver.toUpperCase()} module cache? It will become Not Ready (empty), matrix will show only remaining Ready module. After clear, you can re-upload new files for this module.`;
        if(!confirm(confirmMsg)) return;
        const msgEl = document.getElementById(`msg-${ver}`) || document.getElementById('msg-clear');
        if(msgEl) msgEl.textContent = `Clearing ${ver}...`;
        try{
          const r = await fetch(`${API_CLEAR}?version=${ver}`, { method: 'POST' });
          const j = await r.json();
          if(!r.ok) throw new Error(j.error||'clear failed');
          if(msgEl) msgEl.textContent = `✅ Cleared ${ver} — now Not Ready. You can re-upload new files.`;

          // Immediately reset file input to allow re-upload of same or new files
          resetUploadInput(ver);

          // Refresh UI — use single source helper for card statuses to avoid Ready/Not Ready mismatch
          setTimeout(async ()=>{
            const st = await checkStatus();
            const badge = document.getElementById('util-status-badge');
            if(badge) badge.innerHTML = statusBadgeHTML(st);
            // Update per-card status divs correctly
            updateCardStatuses(st);

            if(st.versions && st.versions.length===0){
              // Both cleared — show empty matrix, no values
              await loadMeta().catch(()=>{});
              setupLineDropdown([]);
              setupVersionTypeDropdown();
              const wrapper = document.getElementById('util-matrix-wrapper');
              if(wrapper) wrapper.innerHTML = `<div style="text-align:center;padding:30px;color:#991b1b;background:#fef2f2;border:1px solid #fecaca;border-radius:6px">❌ All modules cleared — both Gated and Ungated are Not Ready (empty). You can re-upload new files for Gated or Ungated (independent one-click).</div>`;
              const mbadge = document.getElementById('util-matrix-badge');
              if(mbadge) mbadge.innerHTML = `<span style="color:#991b1b">❌ Gated: Not Ready | ❌ Ungated: Not Ready — empty — Re-upload supported</span>`;
            }else{
              // One module remains — show only that, other stays Not Ready (empty)
              await loadMeta();
              setupLineDropdown(meta?.lines||[]);
              if(st.versions.length===1){
                selectedVersionTypes = new Set([st.versions[0].charAt(0).toUpperCase()+st.versions[0].slice(1).toLowerCase()]);
              }else{
                selectedVersionTypes = new Set(st.versions.map(v=> v.charAt(0).toUpperCase()+v.slice(1).toLowerCase()));
              }
              setupVersionTypeDropdown();
              applyPivot();
            }
          }, 500);
        }catch(e){
          if(msgEl) msgEl.textContent = '❌ '+e.message;
        }
      });
    };
    bindClear('gated');
    bindClear('ungated');

    // View Schema — single source of truth, no duplicate schema elsewhere
    // Download buttons Template Zip and Demo Zip are in top info box (no duplication)
    document.getElementById('btn-view-schema')?.addEventListener('click', async ()=>{
      const detailEl = document.getElementById('schema-detail');
      if(!detailEl) return;
      if(detailEl.style.display!=='none' && detailEl.textContent){
        detailEl.style.display='none';
        return;
      }
      detailEl.style.display='block';
      detailEl.textContent='Loading schema...';
      try{
        const schema = await fetchJSON('/api/utilization/templates/schema');
        let html = '<div style="font-weight:600;margin-bottom:6px">📋 Detailed Schema (from /api/utilization/templates/schema)</div>';
        const fmt = (obj)=>{
          let s = `<div style="margin-bottom:10px"><b>${esc(obj.file||'File')}</b> — ${esc(obj.description||obj.note||'')}<br>`;
          if(obj.formula) s+=`<div style="color:#059669">Formula: ${esc(obj.formula)}</div>`;
          if(obj.fields){
            s+='<table style="width:100%;border-collapse:collapse;margin-top:4px;font-size:11px"><tr style="background:#f1f5f9"><th style="border:1px solid #e2e8f0;padding:3px">Field</th><th style="border:1px solid #e2e8f0;padding:3px">Type</th><th style="border:1px solid #e2e8f0;padding:3px">Desc</th><th style="border:1px solid #e2e8f0;padding:3px">Example</th></tr>';
            obj.fields.forEach(f=>{
              s+=`<tr><td style="border:1px solid #e2e8f0;padding:3px"><code>${esc(f[0])}</code></td><td style="border:1px solid #e2e8f0;padding:3px">${esc(f[1])}</td><td style="border:1px solid #e2e8f0;padding:3px">${esc(f[2])}</td><td style="border:1px solid #e2e8f0;padding:3px">${esc(f[3]||'')}</td></tr>`;
            });
            s+='</table>';
          }
          if(obj.upload_requirements){
            s+='<div style="margin-top:6px"><b>Upload Requirements:</b><br>';
            Object.entries(obj.upload_requirements).forEach(([k,v])=>{ s+=`• <b>${esc(k)}</b>: ${esc(v)}<br>`; });
            s+='</div>';
          }
          s+='</div>';
          return s;
        };
        if(schema.calendar) html+=fmt(schema.calendar);
        if(schema.schedule) html+=fmt(schema.schedule);
        if(schema.upload_requirements){
          html+=`<div style="margin-top:8px"><b>Upload Requirements</b>:<br>`;
          Object.entries(schema.upload_requirements).forEach(([k,v])=>{ html+=`• ${esc(k)}: ${esc(v)}<br>`; });
          html+=`</div>`;
        }
        detailEl.innerHTML = html;
      }catch(e){
        detailEl.textContent='Failed to load schema: '+e.message;
      }
    });

    // Column dimension toggle (Day / Shift) like I/O Report — bottom Load Demo and Clear All removed per user request, only top independent modules kept
    const bindModeToggle = (id)=>{
      const btn = document.getElementById(id);
      if(!btn) return;
      btn.addEventListener('click', ()=>{
        document.querySelectorAll('#utilization-section .util-toggle-group button').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = id.includes('day') ? 'day' : 'shift';
        applyPivot();
      });
    };
    bindModeToggle('btn-mode-day');
    bindModeToggle('btn-mode-shift');

    document.getElementById('btn-apply-pivot')?.addEventListener('click', applyPivot);
    document.getElementById('util-filter-from')?.addEventListener('change', applyPivot);
    document.getElementById('util-filter-to')?.addEventListener('change', applyPivot);
    document.getElementById('btn-clear-util-filters')?.addEventListener('click', ()=>{
      selectedVersionTypes = new Set(['Gated','Ungated']);
      selectedLines.clear();
      const fromEl = document.getElementById('util-filter-from');
      const toEl = document.getElementById('util-filter-to');
      if(fromEl) fromEl.value='';
      if(toEl) toEl.value='';
      setupVersionTypeDropdown();
      setupLineDropdown(lines);
      applyPivot();
    });

    // Download Static HTML with flexible filtering — calls export_static backend like campus-planning-system/frontend/dist
    document.getElementById('btn-download-static-util')?.addEventListener('click', async ()=>{
      const btn = document.getElementById('btn-download-static-util');
      const origText = btn ? btn.textContent : '';
      try{
        if(btn){ btn.textContent='⏳ Calling export static...'; btn.disabled=true; }
        // Try backend export_static endpoint first (like campus-planning-system reference)
        try{
          const resp = await fetch('/api/utilization/export/static');
          if(resp.ok){
            const blob = await resp.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            const cd = resp.headers.get('Content-Disposition');
            let fname = 'utilization_static_'+ new Date().toISOString().slice(0,10) + '.html';
            if(cd){
              const m = cd.match(/filename="?([^"]+)"?/);
              if(m) fname = m[1];
            }
            a.download = fname;
            a.click();
            setTimeout(()=> URL.revokeObjectURL(a.href), 1000);
            if(btn){ btn.textContent='✅ Exported via backend'; setTimeout(()=>{ btn.textContent=origText; btn.disabled=false; }, 1500); }
            return;
          }
        }catch(e){ console.warn('Backend export static failed, fallback to client-side', e); }
        if(btn){ btn.textContent='⏳ Preparing static HTML (client)...'; }
        // Fallback: client-side generation with flexible filtering
        const [statusData, metaData, pivotDay, pivotShift] = await Promise.all([
          fetchJSON(API_STATUS).catch(()=>({})),
          fetchJSON(API_META).catch(()=>({})),
          fetchJSON(`${API_PIVOT}?mode=day&version=all`).catch(()=>({columns:[],rows:[]})),
          fetchJSON(`${API_PIVOT}?mode=shift&version=all`).catch(()=>({columns:[],rows:[]}))
        ]);
        const now = new Date().toLocaleString();
        const staticData = {status: statusData, meta: metaData, pivotDay: pivotDay, pivotShift: pivotShift, currentMode: currentMode};

        // Build static HTML with embedded data and filtering logic
        // Exact copy of original module's filter UI from buildMatrixSection — preserves format
        const originalFilterHtml = document.querySelector('#utilization-section .toolbar') ? document.querySelector('#utilization-section .toolbar').outerHTML : `
        <div class="toolbar" style="border:none;padding:8px 0">
          <div class="panels-row">
            <div class="panel panel-filter">
              <div class="panel-label">🔍 Filters <span style="font-weight:400;text-transform:none;color:#94a3b8"> — Filter functionality: version type & line</span> <span id="btn-clear-util-filters" style="font-size:10px;font-weight:400;cursor:pointer;color:#64748b;margin-left:6px;padding:1px 6px;border:1px solid #cbd5e1;border-radius:3px">✕ Clear</span></div>
              <div class="filter-row">
                <div class="filter-group dropdown-filter">
                  <label>Version Type <span id="util-vtype-count" class="tag-count"></span></label>
                  <button class="dropdown-btn" id="util-vtype-btn">All</button>
                  <div class="dropdown-menu" id="util-vtype-menu"></div>
                </div>
                <div class="filter-group dropdown-filter">
                  <label>Line <span id="util-line-count" class="tag-count"></span></label>
                  <button class="dropdown-btn" id="util-line-btn">All</button>
                  <div class="dropdown-menu" id="util-line-menu"></div>
                </div>
                <div class="filter-group">
                  <label>Date From</label>
                  <input type="date" id="util-filter-from" style="padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px">
                </div>
                <div class="filter-group">
                  <label>Date To</label>
                  <input type="date" id="util-filter-to" style="padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px">
                </div>
                <div class="filter-group">
                  <label>&nbsp;</label>
                  <button class="util-btn" id="btn-apply-pivot">Apply</button>
                </div>
              </div>
            </div>
            <div class="panel panel-cols">
              <div class="panel-label">📋 Columns <span style="font-weight:400;text-transform:none;color:#94a3b8"> — Column dimension: Day / Shift like I/O Report</span></div>
              <div class="cols-row" style="align-items:center">
                <div class="util-toggle-group">
                  <button id="btn-mode-day" class="active">Day</button>
                  <button id="btn-mode-shift" class="">Shift</button>
                </div>
                <span style="font-size:11px;color:#64748b;margin-left:8px">Switches date columns between daily aggregated and per-shift</span>
              </div>
            </div>
          </div>
        </div>`;

        const staticHtml = `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Line Utilization - Static Report - ${now}</title>
<style>
body{font-family:Arial,sans-serif;margin:16px;background:#f8fafc;color:#1e293b}
h1{font-size:18px;margin-bottom:4px}
.sub{font-size:11px;color:#64748b;margin-bottom:10px}
.status{margin:10px 0;padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px}
.toolbar{border:none;padding:8px 0}
.panels-row{display:flex;flex-wrap:wrap;gap:12px}
.panel{flex:1;min-width:260px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px}
.panel-label{font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;margin-bottom:6px}
.filter-row{display:flex;flex-wrap:wrap;gap:10px}
.filter-group{position:relative;display:flex;flex-direction:column;gap:4px;min-width:140px}
.filter-group label{font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase}
.dropdown-btn{padding:5px 10px;border:1px solid #cbd5e1;border-radius:5px;background:#fff;cursor:pointer;font-size:12px;text-align:left}
.dropdown-menu{position:absolute;top:100%;left:0;background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:6px;display:none;z-index:100;max-height:250px;overflow:auto;min-width:180px;box-shadow:0 4px 12px rgba(0,0,0,0.1)}
.dropdown-menu.open{display:block}
.dropdown-search input{width:100%;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;font-size:11px}
.util-btn{padding:5px 12px;border:1px solid #3b82f6;background:#3b82f6;color:#fff;border-radius:5px;font-size:12px;cursor:pointer}
.util-toggle-group{display:inline-flex;border:1px solid #cbd5e1;border-radius:6px;overflow:hidden}
.util-toggle-group button{padding:5px 12px;font-size:12px;border:none;background:#fff;cursor:pointer;border-right:1px solid #cbd5e1}
.util-toggle-group button.active{background:#3b82f6;color:#fff}
.table-wrapper{overflow:auto;max-height:80vh;border:1px solid #e2e8f0;border-radius:6px;background:#fff;margin-top:10px}
table{border-collapse:collapse;font-size:12px;white-space:nowrap;width:max-content;min-width:100%}
th{background:#1e293b;color:#fff;padding:6px 8px;position:sticky;top:0;z-index:2;border-right:1px solid #334155}
td{padding:4px 6px;border-bottom:1px solid #e2e8f0;border-right:1px solid #f1f5f9;text-align:center;min-width:68px}
td.frozen{position:sticky;left:0;background:#fff;z-index:1;min-width:68px;text-align:left;font-weight:500}
td.frozen.divider-col{background:#475569 !important;width:5px;min-width:5px;max-width:5px;padding:0 !important}
th.frozen{left:0;z-index:3;background:#1e293b}
th.divider-col{background:#475569 !important;width:5px;min-width:5px;max-width:5px}
.util-cell-zero{color:#cbd5e1}
.util-cell-red{background:#fef2f2;color:#991b1b}
.util-cell-yellow{background:#fffbeb;color:#92400e}
.util-cell-green{background:#ecfdf5;color:#065f46;font-weight:600}
.type-Gated{background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:4px;font-size:11px}
.type-Ungated{background:#d1fae5;color:#065f46;padding:1px 6px;border-radius:4px;font-size:11px}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;margin-right:4px}
.badge-ready{background:#dcfce7;color:#065f46;border:1px solid #86efac}
.badge-notready{background:#fef2f2;color:#991b1b;border:1px solid #fecaca}
.tag-count{background:#f1f5f9;padding:1px 5px;border-radius:8px;font-size:9px}
</style></head><body>
<h1>⚙️ Line Utilization — Static Report (Exact Copy of Below Module)</h1>
<div class="sub">Generated: ${now} | Exact copy of below module — format and filtering preserved like campus-planning-system/frontend/dist | Day cols: \${(staticData.pivotDay.columns||[]).length}, Shift cols: \${(staticData.pivotShift.columns||[]).length}, Lines: \${(staticData.meta.lines||[]).length}</div>
<div class="status" id="static-status"></div>
${originalFilterHtml}
<div style="font-size:11px;color:#64748b;margin:4px 0">Formula: Capacity=UPH×Eff×WH | Load=Σ INPUT | Util%=Load/Capacity capped at 100% | Thick border per Line | Gated yellow, Ungated green</div>
<div id="static-badge" style="margin:8px 0;font-size:11px"></div>
<div class="table-wrapper" id="static-wrapper"><div style="text-align:center;padding:30px;color:#94a3b8">Loading...</div></div>
<script>
const STATIC_DATA = ${JSON.stringify(staticData).replace(/</g,'\\u003c')};

function esc(s){ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }

let currentMode = STATIC_DATA.currentMode || 'day';
let selectedVersions = new Set(['Gated','Ungated']);
let selectedLines = new Set();
let dateFrom = '';
let dateTo = '';

function escAttr(s){ return esc(s).replace(/'/g,'&#39;'); }

function getPivot(){ return currentMode==='day' ? STATIC_DATA.pivotDay : STATIC_DATA.pivotShift; }

function setupVersionTypeDropdown(){
  const btn = document.getElementById('util-vtype-btn');
  const menu = document.getElementById('util-vtype-menu');
  const cnt = document.getElementById('util-vtype-count');
  if(!btn||!menu) return;
  const allTypes = ['Gated','Ungated'];
  function renderMenu(){
    const total = allTypes.length;
    const selected = selectedVersions.size;
    const isAll = selected===total;
    if(cnt) cnt.textContent = isAll ? '' : ''+selected;
    btn.textContent = isAll ? 'All '+total : (selected===0?'(none)':selected+' selected');
    let html = '<div class="dropdown-all"><label><input type="checkbox" id="vtype-all" '+(isAll?'checked':'')+'> All ('+total+')</label></div>';
    allTypes.forEach(v=>{
      const checked = selectedVersions.has(v);
      html += '<label><input type="checkbox" data-val="'+escAttr(v)+'" '+(checked?'checked':'')+'> <span class="type-badge type-'+esc(v)+'">'+esc(v)+'</span></label>';
    });
    menu.innerHTML = html;
    const allCb = menu.querySelector('#vtype-all');
    if(allCb){
      allCb.addEventListener('change', (e)=>{
        if(e.target.checked){ selectedVersions = new Set(allTypes); }else{ selectedVersions.clear(); }
        renderMenu();
      });
    }
    menu.querySelectorAll('input[data-val]').forEach(cb=>{
      cb.addEventListener('change', (e)=>{
        const v = e.target.dataset.val;
        if(e.target.checked) selectedVersions.add(v);
        else selectedVersions.delete(v);
        renderMenu();
      });
    });
  }
  btn.onclick = (e)=>{ e.stopPropagation(); menu.classList.toggle('open'); renderMenu(); };
  document.addEventListener('click', ()=> menu.classList.remove('open'));
  menu.onclick = (e)=> e.stopPropagation();
  renderMenu();
}

function setupLineDropdown(){
  const btn = document.getElementById('util-line-btn');
  const menu = document.getElementById('util-line-menu');
  const cnt = document.getElementById('util-line-count');
  if(!btn||!menu) return;
  const allLines = (STATIC_DATA.meta && STATIC_DATA.meta.lines) ? STATIC_DATA.meta.lines : [];
  let searchTerm = '';
  function renderMenu(){
    const total = allLines.length;
    const isAll = selectedLines.size===0;
    if(cnt) cnt.textContent = isAll ? '' : ''+selectedLines.size;
    btn.textContent = isAll ? 'All '+total : selectedLines.size+' selected';
    const filtered = searchTerm ? allLines.filter(l=> l.toLowerCase().includes(searchTerm.toLowerCase())) : allLines;
    let html = '<div class="dropdown-search"><input type="text" id="line-search" placeholder="Search line..." value="'+escAttr(searchTerm)+'"></div>';
    html += '<div class="dropdown-all"><label><input type="checkbox" id="line-all" '+(isAll?'checked':'')+'> All ('+total+')</label></div>';
    filtered.forEach(l=>{
      const checked = isAll || selectedLines.has(l);
      html += '<label><input type="checkbox" data-val="'+escAttr(l)+'" '+(checked?'checked':'')+'> '+esc(l)+'</label>';
    });
    menu.innerHTML = html;
    const sInput = menu.querySelector('#line-search');
    if(sInput){ sInput.focus(); sInput.addEventListener('input', (e)=>{ searchTerm = e.target.value; renderMenu(); }); sInput.addEventListener('click', (e)=> e.stopPropagation()); }
    const allCb = menu.querySelector('#line-all');
    if(allCb){
      allCb.addEventListener('change', (e)=>{
        if(e.target.checked){ selectedLines.clear(); }else{ selectedLines = new Set(allLines); }
        renderMenu();
      });
    }
    menu.querySelectorAll('input[data-val]').forEach(cb=>{
      cb.addEventListener('change', (e)=>{
        const v = e.target.dataset.val;
        if(e.target.checked){
          if(selectedLines.size===0){ }else{ selectedLines.add(v); if(selectedLines.size===allLines.length) selectedLines.clear(); }
        }else{
          if(selectedLines.size===0){ selectedLines = new Set(allLines); selectedLines.delete(v); }else{ selectedLines.delete(v); }
        }
        renderMenu();
      });
    });
  }
  btn.onclick = (e)=>{ e.stopPropagation(); menu.classList.toggle('open'); if(menu.classList.contains('open')) renderMenu(); };
  document.addEventListener('click', ()=> menu.classList.remove('open'));
  menu.onclick = (e)=> e.stopPropagation();
  renderMenu();
}

function bindModeToggle(id){
  const btn = document.getElementById(id);
  if(!btn) return;
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('.util-toggle-group button').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    currentMode = id.includes('day') ? 'day' : 'shift';
    renderMatrix();
  });
}

function renderStatus(){
  const st = STATIC_DATA.status;
  const versions = (st && st.versions) ? st.versions : [];
  const gatedReady = versions.includes('gated');
  const ungatedReady = versions.includes('ungated');
  let html = '';
  if(gatedReady && ungatedReady) html = '<span class="badge badge-ready">✅ Gated: Ready</span><span class="badge badge-ready">✅ Ungated: Ready</span> — Showing both';
  else if(gatedReady) html = '<span class="badge badge-ready">✅ Gated: Ready</span><span class="badge badge-notready">❌ Ungated: Not Ready (empty)</span> — Showing Gated only';
  else if(ungatedReady) html = '<span class="badge badge-notready">❌ Gated: Not Ready</span><span class="badge badge-ready">✅ Ungated: Ready</span> — Showing Ungated only';
  else html = '<span class="badge badge-notready">❌ Gated: Not Ready</span><span class="badge badge-notready">❌ Ungated: Not Ready</span> — No data, re-upload needed';
  document.getElementById('static-status').innerHTML = html;
}

function renderMatrix(){
  const pivot = getPivot();
  const cols = pivot.columns || [];
  const rows = pivot.rows || [];
  const detail = pivot.detail || {};
  const wrapper = document.getElementById('static-wrapper');
  if(!rows || rows.length===0){
    wrapper.innerHTML = '<div style="text-align:center;padding:30px;color:#991b1b;background:#fef2f2;border:1px solid #fecaca;border-radius:6px">No data — both modules Not Ready or filtered out</div>';
    document.getElementById('static-badge').textContent = '0 rows';
    return;
  }
  // Filter rows by version and line — exact copy of original filtering logic
  let filteredRows = rows.filter(r=>{
    const v = (r.version_type||'').toLowerCase();
    if(v==='gated' && !selectedVersions.has('Gated')) return false;
    if(v==='ungated' && !selectedVersions.has('Ungated')) return false;
    if(selectedLines.size>0){
      if(!selectedLines.has(r.line_code)) return false;
    }
    return true;
  });
  // Filter columns by date — exact copy
  let filteredCols = cols;
  if(dateFrom || dateTo){
    filteredCols = cols.filter(c=>{
      let d = c;
      if(c.includes('|')) d = c.split('|')[0];
      if(dateFrom && d < dateFrom) return false;
      if(dateTo && d > dateTo) return false;
      return true;
    });
  }

  // Build header
  const frozenCols = [{key:'line_code',label:'Line',width:130},{key:'version_type',label:'Version Type',width:110}];
  let left=0; frozenCols.forEach(c=>{ c._left=left; left+=c.width; });
  const dividerLeft = left;
  let thead = '<tr>';
  frozenCols.forEach(c=>{ thead += '<th class="frozen" style="left:'+c._left+'px;min-width:'+c.width+'px">'+esc(c.label)+'</th>'; });
  thead += '<th class="frozen divider-col" style="left:'+dividerLeft+'px;min-width:5px"></th>';
  filteredCols.forEach(col=>{
    let label = col;
    let sub='';
    if(col.includes('|')){ const parts=col.split('|'); label=parts[0]; sub=parts[1]; try{ const d=new Date(label); if(!isNaN(d)) label=(d.getMonth()+1)+'/'+d.getDate(); }catch(e){} }else{ try{ const d=new Date(col); if(!isNaN(d)) label=(d.getMonth()+1)+'/'+d.getDate(); }catch(e){} }
    thead += '<th style="min-width:68px" title="'+esc(col)+'">'+esc(label)+(sub?'<br><span style="font-size:9px;color:#cbd5e1">'+esc(sub)+'</span>':'')+'</th>';
  });
  thead += '</tr>';

  let tbody='';
  let lastLine=null;
  filteredRows.forEach(r=>{
    const isNewLine = r.line_code !== lastLine;
    lastLine = r.line_code;
    const vType = r.version_type||'';
    tbody += '<tr class="'+(isNewLine?'row-new-line':'')+'">';
    frozenCols.forEach(c=>{
      const isLast = c===frozenCols[frozenCols.length-1];
      const extra = isLast ? ' frozen-last' : '';
      let val='';
      if(c.key==='line_code') val=esc(r.line_code);
      else if(c.key==='version_type') val='<span class="type-'+esc(vType)+'">'+esc(vType)+'</span>';
      tbody += '<td class="frozen data-cell'+extra+'" style="left:'+c._left+'px;min-width:'+c.width+'px">'+val+'</td>';
    });
    tbody += '<td class="divider-col frozen" style="left:'+dividerLeft+'px"></td>';
    filteredCols.forEach(col=>{
      const keyStr = r.line_code+'||'+vType;
      const cellDetail = detail[keyStr] && detail[keyStr][col];
      const cellVal = r[col];
      if(cellVal==null){ tbody += '<td class="data-cell" style="background:#f8fafc"></td>'; }
      else{
        let cls='';
        if(cellVal===0) cls='util-cell-zero';
        else if(cellVal<60) cls='util-cell-red';
        else if(cellVal<80) cls='util-cell-yellow';
        else cls='util-cell-green';
        tbody += '<td class="data-cell '+cls+'">'+Math.round(cellVal)+'%</td>';
      }
    });
    tbody += '</tr>';
  });

  wrapper.innerHTML = '<table><thead>'+thead+'</thead><tbody>'+tbody+'</tbody></table>';
  document.getElementById('static-badge').textContent = filteredRows.length+' rows × '+filteredCols.length+' cols (filtered from '+rows.length+' rows × '+cols.length+' cols) | Thick border per Line';
}

function bindModeToggle(id){
  const btn = document.getElementById(id);
  if(!btn) return;
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('.util-toggle-group button').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    currentMode = id.includes('day') ? 'day' : 'shift';
    renderMatrix();
  });
}

document.getElementById('util-filter-from')?.addEventListener('change', (e)=>{ dateFrom = e.target.value; });
document.getElementById('util-filter-to')?.addEventListener('change', (e)=>{ dateTo = e.target.value; });
document.getElementById('btn-apply-pivot')?.addEventListener('click', ()=>{ renderMatrix(); });
document.getElementById('btn-clear-util-filters')?.addEventListener('click', ()=>{
  selectedVersions = new Set(['Gated','Ungated']);
  selectedLines.clear();
  dateFrom=''; dateTo='';
  const fromEl = document.getElementById('util-filter-from');
  const toEl = document.getElementById('util-filter-to');
  if(fromEl) fromEl.value='';
  if(toEl) toEl.value='';
  setupVersionTypeDropdown();
  setupLineDropdown();
  renderMatrix();
});

setupVersionTypeDropdown();
setupLineDropdown();
bindModeToggle('btn-mode-day');
bindModeToggle('btn-mode-shift');

renderStatus();
renderMatrix();
</script>
</body></html>`;

        const blob = new Blob([staticHtml], {type:'text/html'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'utilization_static_interactive_'+ new Date().toISOString().slice(0,10) + '.html';
        a.click();
        setTimeout(()=> URL.revokeObjectURL(a.href), 1000);
      }catch(e){
        alert('Download static HTML failed: '+e.message);
        console.error(e);
      }finally{
        if(btn){ btn.textContent=origText; btn.disabled=false; }
      }
    });

    if(status.loaded){
      applyPivot();
    }
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    const active = document.querySelector('.nav-item.active');
    if(active && active.dataset.module==='utilization'){ render(); }
  });
  document.addEventListener('module-change', (e)=>{
    if(e.detail.module==='utilization'){ render(); }
  });
})();
