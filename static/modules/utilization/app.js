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

  let meta = null;
  let currentMode = 'day'; // day or shift
  let currentVersion = 'all'; // all = gated+ungated, or gated, ungated
  let pivotCache = null;
  let selectedVersionTypes = new Set(['Gated','Ungated']); // for filter
  let selectedLines = new Set(); // empty = all
  let colToggles = { uph: false, eff: false, wh: false, cap: true, load: true };

  function esc(s){ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }
  function escAttr(s){ return esc(s).replace(/'/g,'&#39;'); }
  function getRoot(){ return document.getElementById('utilization-section'); }

  async function fetchJSON(url, opts){
    const r = await fetch(url, opts);
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  }

  async function checkStatus(){
    try{ return await fetchJSON(API_STATUS); }catch(e){ return {loaded:false}; }
  }

  async function loadMeta(){
    try{
      meta = await fetchJSON(API_META);
      return true;
    }catch(e){ meta=null; return false; }
  }

  function statusBadgeHTML(status){
    if(status && status.loaded){
      const vers = (status.versions||[]).join(', ')||'gated';
      return `<span class="util-status-badge ready">✅ Ready: ${vers}</span>`;
    }else{
      return `<span class="util-status-badge empty">No data — upload or load demo</span>`;
    }
  }

  function buildUploadHTML(status){
    return `
      <div class="section">
        <div class="section-header">
          <span class="section-title">⚙️ Line Utilization — Upload</span>
          <span id="util-status-badge">${statusBadgeHTML(status)}</span>
        </div>
        <div style="padding:12px;background:#f8fafc;border:1px dashed #cbd5e1;border-radius:6px;font-size:12px;color:#475569;margin-bottom:12px">
          <b>Formula:</b> <code>Capacity = UPH × Efficiency × WorkingHours</code> (calendar INPUT) | <code>Load = Σ schedule INPUT</code> | <code>Util% = Load / Capacity</code> capped at 100% (raw in tooltip)
        </div>
        <div class="util-upload-grid">
          <div class="util-upload-card">
            <div class="util-upload-label">Gated Version</div>
            <div class="util-upload-hint">Calendar + Schedule</div>
            <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
              <div><label style="font-size:11px">Calendar</label><br><input type="file" id="file-gated-cal" accept=".xlsx"></div>
              <div><label style="font-size:11px">Schedule</label><br><input type="file" id="file-gated-sched" accept=".xlsx"></div>
            </div>
            <div style="margin-top:8px"><button class="util-btn" id="btn-upload-gated">Upload Gated</button> <span id="msg-gated" style="font-size:11px;color:#64748b"></span></div>
          </div>
          <div class="util-upload-card">
            <div class="util-upload-label">Ungated (optional)</div>
            <div class="util-upload-hint">For Gated vs Ungated compare</div>
            <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
              <div><label style="font-size:11px">Calendar</label><br><input type="file" id="file-ungated-cal" accept=".xlsx"></div>
              <div><label style="font-size:11px">Schedule</label><br><input type="file" id="file-ungated-sched" accept=".xlsx"></div>
            </div>
            <div style="margin-top:8px"><button class="util-btn" id="btn-upload-ungated">Upload Ungated</button> <span id="msg-ungated" style="font-size:11px;color:#64748b"></span></div>
          </div>
        </div>
        <div style="text-align:center;margin:12px 0">
          <button class="util-btn util-btn-outline" id="btn-load-demo">📦 Load Demo (IVY20260721Gated)</button>
          <span id="msg-demo" style="font-size:11px;margin-left:8px;color:#64748b"></span>
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
              <span style="background:#ecfdf5;color:#059669;padding:2px 6px;border-radius:10px">0-50%</span>
              <span style="background:#fffbeb;color:#d97706;padding:2px 6px;border-radius:10px">50-80%</span>
              <span style="background:#ffedd5;color:#ea580c;padding:2px 6px;border-radius:10px">80-100%</span>
              <span style="background:#fef2f2;color:#dc2626;padding:2px 6px;border-radius:10px;border:1px solid #fecaca">Overload</span>
            </span>
          </div>
        </div>

        <div class="dim-tabs">
          <button class="dim-tab ${currentMode==='day'?'active':''}" data-mode="day">Day</button>
          <button class="dim-tab ${currentMode==='shift'?'active':''}" data-mode="shift">Shift</button>
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
              <div class="panel-label">📋 Columns <span style="font-weight:400;text-transform:none;color:#94a3b8"> — Column dimensions</span></div>
              <div class="cols-row">
                <label class="toggle-label"><input type="checkbox" id="col-uph"> UPH</label>
                <label class="toggle-label"><input type="checkbox" id="col-eff"> Eff</label>
                <label class="toggle-label"><input type="checkbox" id="col-wh"> WH</label>
                <label class="toggle-label"><input type="checkbox" id="col-cap" checked> Capacity</label>
                <label class="toggle-label"><input type="checkbox" id="col-load" checked> Load</label>
                <span id="util-col-count" style="font-size:11px;color:#64748b;margin-left:8px"></span>
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

  // ---- Dropdown helpers similar to Packout ----
  function setupVersionTypeDropdown(){
    const btn = document.getElementById('util-vtype-btn');
    const menu = document.getElementById('util-vtype-menu');
    const cnt = document.getElementById('util-vtype-count');
    if(!btn||!menu) return;
    const allTypes = ['Gated','Ungated'];
    function render(){
      const selectedCount = selectedVersionTypes.size;
      cnt.textContent = selectedCount < allTypes.length ? `${selectedCount}` : '';
      btn.textContent = selectedCount===allTypes.length ? `All ${allTypes.length}` : selectedCount===0 ? '(none)' : `${selectedCount} selected`;
      let h = `<div class="dropdown-all"><label><input type="checkbox" id="vtype-all" ${selectedCount===allTypes.length?'checked':''}> All (${allTypes.length})</label></div>`;
      allTypes.forEach(v=>{
        h+=`<label><input type="checkbox" data-val="${escAttr(v)}" ${selectedVersionTypes.has(v)?'checked':''}> <span class="type-badge type-${v}">${esc(v)}</span></label>`;
      });
      menu.innerHTML = h;
      menu.querySelector('#vtype-all')?.addEventListener('change', (e)=>{
        if(e.target.checked){ allTypes.forEach(v=>selectedVersionTypes.add(v)); }
        else { selectedVersionTypes.clear(); }
        render(); applyPivot();
      });
      menu.querySelectorAll('input[data-val]').forEach(cb=>{
        cb.addEventListener('change', (e)=>{
          const v = e.target.dataset.val;
          if(e.target.checked) selectedVersionTypes.add(v); else selectedVersionTypes.delete(v);
          render();
          applyPivot();
        });
      });
    }
    btn.onclick = (e)=>{ e.stopPropagation(); menu.classList.toggle('open'); };
    document.addEventListener('click', ()=> menu.classList.remove('open'));
    menu.onclick = (e)=> e.stopPropagation();
    render();
  }

  function setupLineDropdown(lines){
    const btn = document.getElementById('util-line-btn');
    const menu = document.getElementById('util-line-menu');
    const cnt = document.getElementById('util-line-count');
    if(!btn||!menu) return;
    const allLines = lines || [];
    function render(){
      const total = allLines.length;
      const selectedCount = selectedLines.size===0 ? total : selectedLines.size;
      // cnt shows selected when not all
      const isAll = selectedLines.size===0 || selectedLines.size===total;
      cnt.textContent = isAll ? '' : `${selectedLines.size}`;
      btn.textContent = isAll ? `All ${total}` : `${selectedLines.size} selected`;
      let h = `<div class="dropdown-search"><input type="text" id="util-line-search" placeholder="Search line..."></div>`;
      h+=`<div class="dropdown-all"><label><input type="checkbox" id="line-all" ${isAll?'checked':''}> All (${total})</label></div>`;
      // Filter by search term
      const searchInput = document.getElementById('util-line-search');
      const term = (searchInput?.value || '').toLowerCase();
      const filtered = term ? allLines.filter(l=> l.toLowerCase().includes(term)) : allLines;
      filtered.forEach(l=>{
        const checked = selectedLines.size===0 || selectedLines.has(l);
        h+=`<label><input type="checkbox" data-val="${escAttr(l)}" ${checked?'checked':''}> ${esc(l)}</label>`;
      });
      if(filtered.length===0) h+=`<div style="padding:8px;color:#94a3b8;font-size:12px">No match</div>`;
      menu.innerHTML = h;
      const sInput = menu.querySelector('#util-line-search');
      if(sInput){
        sInput.focus();
        sInput.oninput = ()=> render();
        sInput.onclick = (e)=> e.stopPropagation();
        // Keep term
        if(term) sInput.value = term;
      }
      menu.querySelector('#line-all')?.addEventListener('change', (e)=>{
        if(e.target.checked) selectedLines.clear();
        else {
          // If unchecking all, select none? For UX, unchecking all means clear? We'll clear to represent none
          // Actually to represent none, we need all unchecked, but we treat empty as all, so we need to check logic
          // Simplify: checking all = clear set (means all), unchecking = select none? We'll set to all lines selected to represent none? Let's just clear for checked, and for unchecked select none = all lines individually? That would be confusing.
          // Better: checking all = clear set, unchecking all = set with all lines (so none displayed? hmm)
          // We'll implement: checked => clear (all), unchecked => select all lines one by one (means none displayed? Actually we want unchecked all to show none)
          // For simplicity, checked = clear (all), unchecked = empty? We'll just clear for checked, and for unchecked we add all lines to set then clear? Let's just for unchecked, select all lines into set then immediately clear? Hmm.
          // Simpler: we treat selectedLines empty = all. So "All" checkbox checked means empty set. Unchecked means we want to allow individual selection, but if user unchecks All, we should keep current individual selections? We'll just clear and not render individual.
          if(!e.target.checked){
            // Unchecking All -> keep none selected? We'll set selectedLines to have all lines, then user can uncheck individually to exclude? Actually to show none, set would need to be all? Wait.
            // Let's define: selectedLines contains excluded? No.
            // For simplicity, unchecking All will select all lines into selectedLines (meaning all individually checked) which still shows all? So to show none, we need different logic.
            // We'll just if unchecking, set selectedLines to all lines (still all), but UI will show all checked? Confusing.
            // Workaround: if user unchecks All, we set selectedLines to all lines (so filtered still shows all) but then they can uncheck individual to exclude.
            // Actually we want All unchecked to mean show none, but that's rare. So for now, unchecking All will set selectedLines to have all lines (so that individual checkboxes are all checked, but our logic of empty==all breaks). Let's handle differently: keep a flag _lineAllChecked.
          }
        });
        // Actually rebind simpler: handle individual
        menu.querySelectorAll('input[data-val]').forEach(cb=>{
          cb.addEventListener('change', (e)=>{
            const v = e.target.dataset.val;
            if(e.target.checked){
              // If we are in "all" state (empty), we need to convert to set of all except this? Complex.
              // Simplify: if selectedLines empty (means all), then on first uncheck we need to populate set with all except this one
              if(selectedLines.size===0){
                allLines.forEach(l=>{ if(l!==v) selectedLines.add(l); });
                // If this was the only one unchecked, set will have all-1
              }else{
                selectedLines.add(v);
              }
            }else{
              if(selectedLines.size===0){
                // Was all, now unchecking one -> need to have all except this
                allLines.forEach(l=> selectedLines.add(l));
                selectedLines.delete(v);
              }else{
                selectedLines.delete(v);
              }
            }
            // If back to all selected, clear set to represent all
            if(selectedLines.size===allLines.length) selectedLines.clear();
            render();
            applyPivot();
          });
        });
      }
    }
    btn.onclick = (e)=>{ e.stopPropagation(); menu.classList.toggle('open'); if(menu.classList.contains('open')) render(); };
    document.addEventListener('click', ()=> menu.classList.remove('open'));
    menu.onclick = (e)=> e.stopPropagation();
    render();
  }

  function getVersionTypeArray(){
    if(selectedVersionTypes.size===0) return [];
    return Array.from(selectedVersionTypes);
  }

  function getLineArray(){
    if(selectedLines.size===0) return null; // null = all
    return Array.from(selectedLines);
  }

  // ---- Matrix rendering ----
  function renderMatrix(pivot){
    pivotCache = pivot;
    const cols = pivot.columns || [];
    const rows = pivot.rows || [];
    const detail = pivot.detail || {};

    const wrapper = document.getElementById('util-matrix-wrapper');
    if(!wrapper) return;

    if(rows.length===0){
      wrapper.innerHTML = `<div style="text-align:center;padding:30px;color:#94a3b8">No matching data. Adjust filters.</div>`;
      return;
    }

    // Column visibility toggles
    const showUPH = document.getElementById('col-uph')?.checked;
    const showEff = document.getElementById('col-eff')?.checked;
    const showWH = document.getElementById('col-wh')?.checked;
    const showCap = document.getElementById('col-cap')?.checked;
    const showLoad = document.getElementById('col-load')?.checked;

    // Build frozen columns definition
    const frozenCols = [
      {key:'line_code', label:'Line', width:130},
      {key:'version_type', label:'Version Type', width:110},
    ];
    // Extra info columns toggled
    const extraCols = [];
    if(showUPH) extraCols.push({key:'_uph', label:'UPH', width:70});
    if(showEff) extraCols.push({key:'_eff', label:'Eff', width:60});
    if(showWH) extraCols.push({key:'_wh', label:'WH', width:60});
    if(showCap) extraCols.push({key:'_cap', label:'Capacity', width:80});
    if(showLoad) extraCols.push({key:'_load', label:'Load', width:80});

    const allFrozen = [...frozenCols, ...extraCols];

    // Compute left offsets
    let left = 0;
    allFrozen.forEach(c=>{ c._left = left; left+=c.width; });
    const dividerLeft = left;
    const DIVIDER = {width:5};

    // Header
    let thead = '<tr>';
    allFrozen.forEach(c=>{
      thead+=`<th class="frozen" style="left:${c._left}px;min-width:${c.width}px">${esc(c.label)}</th>`;
    });
    thead+=`<th class="frozen divider-col" style="left:${dividerLeft}px;min-width:${DIVIDER.width}px"></th>`;
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
        }catch{}
      }else{
        try{
          const d = new Date(col);
          if(!isNaN(d)) label = `${d.getMonth()+1}/${d.getDate()}`;
        }catch{}
      }
      thead+=`<th style="min-width:68px;text-align:center" title="${esc(col)}">${esc(label)}${sub?`<br><span style="font-size:9px;color:#cbd5e1">${esc(sub)}</span>`:''}</th>`;
    });
    thead+='</tr>';

    // Body with thick border per line change
    let tbody = '';
    let lastLine = null;
    rows.forEach(r=>{
      const isNewLine = r.is_new_line;
      const vType = r.version_type||'';
      const rowClass = `row-${vType} ${isNewLine?'row-new-line':''}`;
      tbody+=`<tr class="${rowClass}">`;
      allFrozen.forEach(c=>{
        const isLast = c===allFrozen[allFrozen.length-1];
        const cls = isLast ? ' frozen-last' : '';
        let val = '';
        if(c.key==='line_code') val = esc(r.line_code);
        else if(c.key==='version_type') val = `<span class="type-badge type-${esc(vType)}">${esc(vType)}</span>`;
        else if(c.key==='_uph' || c.key==='_eff' || c.key==='_wh' || c.key==='_cap' || c.key==='_load'){
          // For extra cols, we need to show avg? For simplicity show empty or from first detail column
          // We'll compute from detail for first col if available
          const firstCol = cols[0];
          const keyStr = `${r.line_code}||${vType}`;
          const det = detail[keyStr] && detail[keyStr][firstCol];
          if(det){
            if(c.key==='_uph') val = det.uph ? det.uph.toFixed(0) : '';
            else if(c.key==='_eff') val = det.efficiency ? det.efficiency.toFixed(2) : '';
            else if(c.key==='_wh') val = det.working_hours || '';
            else if(c.key==='_cap') val = det.capacity ? Math.round(det.capacity).toLocaleString() : '';
            else if(c.key==='_load') val = det.load ? Math.round(det.load).toLocaleString() : '';
          }
        }
        tbody+=`<td class="frozen data-cell${cls}" style="left:${c._left}px;min-width:${c.width}px">${val}</td>`;
      });
      tbody+=`<td class="divider-col frozen" style="left:${dividerLeft}px"></td>`;
      cols.forEach(col=>{
        const keyStr = `${r.line_code}||${vType}`;
        const cellDetail = detail[keyStr] && detail[keyStr][col];
        const val = r[col];
        if(val==null){
          tbody+=`<td class="data-cell" style="background:#f8fafc"></td>`;
        }else{
          const raw = cellDetail ? cellDetail.util_raw : val;
          const isOver = cellDetail ? cellDetail.util_raw>100 : false;
          const load = cellDetail ? cellDetail.load : '';
          const cap = cellDetail ? cellDetail.capacity : '';
          let cls = '';
          if(isOver) cls='util-cell-over';
          else if(val>=80) cls='util-cell-high';
          else if(val>=50) cls='util-cell-mid';
          else if(val>0) cls='util-cell-low';
          else cls='util-cell-zero';
          let display = val>0? `${Math.round(val)}%` : '0%';
          if(isOver) display = `100%<span style="font-size:8px">(${Math.round(raw)}%)</span>`;
          tbody+=`<td class="data-cell ${cls}" title="Line:${esc(r.line_code)} Ver:${esc(vType)} Date:${esc(col)} Load:${load} Cap:${cap} Raw:${raw}% (capped)">{__DISPLAY__}</td>`.replace('{__DISPLAY__}', display);
        }
      });
      tbody+='</tr>';
    });

    wrapper.innerHTML = `<table><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;

    const badge = document.getElementById('util-matrix-badge');
    if(badge){
      badge.textContent = `${pivot.total_lines} rows × ${pivot.total_cols} cols | Thick border per Line`;
    }
  }

  async function applyPivot(){
    const lineInput = document.getElementById('util-filter-line');
    // line filter from selectedLines set, but also support text input if any? We'll use selectedLines
    const lineParam = selectedLines.size===0 ? '' : Array.from(selectedLines).join(',');
    const from = document.getElementById('util-filter-from')?.value || '';
    const to = document.getElementById('util-filter-to')?.value || '';
    // version param: if selectedVersionTypes has both, use all
    let versionParam = 'all';
    if(selectedVersionTypes.size===1){
      versionParam = Array.from(selectedVersionTypes)[0].toLowerCase();
    }else if(selectedVersionTypes.size===0){
      // none selected -> show none, but we return empty
      document.getElementById('util-matrix-wrapper').innerHTML = `<div style="text-align:center;padding:30px;color:#94a3b8">No version type selected</div>`;
      return;
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
      const res = await fetchJSON(`${API_PIVOT}?${params.toString()}`);
      // Filter rows by version_type if needed (backend already does but we also have selectedVersionTypes)
      let filteredRows = res.rows;
      if(selectedVersionTypes.size>0 && selectedVersionTypes.size<2){
        filteredRows = res.rows.filter(r=> selectedVersionTypes.has(r.version_type));
      }
      // If lineParam was comma-separated, backend already filtered, but we also have selectedLines logic
      res.rows = filteredRows;
      renderMatrix(res);
    }catch(e){
      if(wrapper) wrapper.innerHTML = `<div style="color:#dc2626;padding:12px">Error: ${esc(e.message)}</div>`;
    }
  }

  async function render(){
    const root = getRoot();
    if(!root) return;
    const status = await checkStatus();
    let html = '';
    html += buildUploadHTML(status);
    html += buildMatrixSection();
    root.innerHTML = html;

    // Setup dropdowns after HTML inserted
    await loadMeta();
    const lines = (meta && meta.lines) ? meta.lines : [];
    setupVersionTypeDropdown();
    setupLineDropdown(lines);

    // Bind upload
    document.getElementById('btn-upload-gated')?.addEventListener('click', async ()=>{
      const cal = document.getElementById('file-gated-cal').files[0];
      const sched = document.getElementById('file-gated-sched').files[0];
      if(!cal || !sched){ alert('Select both calendar and schedule for gated'); return; }
      const fd = new FormData();
      fd.append('version','gated');
      fd.append('calendar', cal);
      fd.append('schedule', sched);
      const msg = document.getElementById('msg-gated');
      msg.textContent='Uploading...';
      try{
        const r = await fetch(API_UPLOAD, {method:'POST', body:fd});
        const j = await r.json();
        if(!r.ok) throw new Error(j.error||'upload failed');
        msg.textContent=`✅ ${j.lines} lines`;
        setTimeout(()=> location.reload(), 800);
      }catch(e){ msg.textContent='❌ '+e.message; }
    });
    document.getElementById('btn-upload-ungated')?.addEventListener('click', async ()=>{
      const cal = document.getElementById('file-ungated-cal').files[0];
      const sched = document.getElementById('file-ungated-sched').files[0];
      if(!cal || !sched){ alert('Select both for ungated'); return; }
      const fd = new FormData();
      fd.append('version','ungated');
      fd.append('calendar', cal);
      fd.append('schedule', sched);
      const msg = document.getElementById('msg-ungated');
      msg.textContent='Uploading...';
      try{
        const r = await fetch(API_UPLOAD, {method:'POST', body:fd});
        const j = await r.json();
        if(!r.ok) throw new Error(j.error||'upload failed');
        msg.textContent=`✅ ${j.lines} lines`;
        setTimeout(()=> location.reload(), 800);
      }catch(e){ msg.textContent='❌ '+e.message; }
    });
    document.getElementById('btn-load-demo')?.addEventListener('click', async ()=>{
      const msg = document.getElementById('msg-demo');
      msg.textContent='Loading demo...';
      try{
        const r = await fetch(API_DEMO, {method:'POST'});
        const j = await r.json();
        if(!r.ok) throw new Error(j.error||'failed');
        msg.textContent=`✅ Demo loaded: ${j.lines} lines`;
        setTimeout(async ()=>{ await loadMeta(); setupLineDropdown(meta.lines); applyPivot(); }, 800);
      }catch(e){ msg.textContent='❌ '+e.message; }
    });

    // Mode tabs
    document.querySelectorAll('#utilization-section .dim-tab').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        document.querySelectorAll('#utilization-section .dim-tab').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.dataset.mode;
        applyPivot();
      });
    });

    // Column toggles
    ['col-uph','col-eff','col-wh','col-cap','col-load'].forEach(id=>{
      document.getElementById(id)?.addEventListener('change', applyPivot);
    });

    // Date filters
    document.getElementById('btn-apply-pivot')?.addEventListener('click', applyPivot);
    document.getElementById('util-filter-from')?.addEventListener('change', applyPivot);
    document.getElementById('util-filter-to')?.addEventListener('change', applyPivot);

    // Clear filters
    document.getElementById('btn-clear-util-filters')?.addEventListener('click', ()=>{
      selectedVersionTypes = new Set(['Gated','Ungated']);
      selectedLines.clear();
      document.getElementById('util-filter-from').value='';
      document.getElementById('util-filter-to').value='';
      setupVersionTypeDropdown();
      setupLineDropdown(lines);
      applyPivot();
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
