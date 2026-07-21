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
  let currentMode = 'day';
  let currentVersion = 'all';
  let pivotCache = null;
  let selectedVersionTypes = new Set(['Gated','Ungated']);
  let selectedLines = new Set();

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
          <b>Formula:</b> <code>Capacity = UPH × Efficiency × WorkingHours</code> | <code>Load = Σ INPUT</code> | <code>Util% = Load / Capacity</code> capped at 100%
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
            <div class="util-upload-hint">For compare</div>
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

    if(rows.length===0){
      wrapper.innerHTML = `<div style="text-align:center;padding:30px;color:#94a3b8">No matching data. Adjust filters.</div>`;
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
          const isOver = cellDetail ? cellDetail.util_raw>100 : false;
          const load = cellDetail ? cellDetail.load : '';
          const cap = cellDetail ? cellDetail.capacity : '';
          let cls = '';
          if(isOver) cls='util-cell-over';
          else if(cellVal>=80) cls='util-cell-high';
          else if(cellVal>=50) cls='util-cell-mid';
          else if(cellVal>0) cls='util-cell-low';
          else cls='util-cell-zero';
          let display = cellVal>0 ? `${Math.round(cellVal)}%` : '0%';
          if(isOver) display = `100%<span style="font-size:8px">(${Math.round(raw)}%)</span>`;
          tbody += `<td class="data-cell ${cls}" title="Line:${esc(r.line_code)} Ver:${esc(vType)} Date:${esc(col)} Load:${load} Cap:${cap} Raw:${raw}%">${display}</td>`;
        }
      });
      tbody += '</tr>';
    });

    wrapper.innerHTML = `<table><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;

    const badge = document.getElementById('util-matrix-badge');
    if(badge){
      badge.textContent = `${pivot.total_lines} rows × ${pivot.total_cols} cols | Thick border per Line`;
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
    let html = '';
    html += buildUploadHTML(status);
    html += buildMatrixSection();
    root.innerHTML = html;

    await loadMeta();
    const lines = (meta && meta.lines) ? meta.lines : [];

    setupVersionTypeDropdown();
    setupLineDropdown(lines);

    // Upload handlers
    const bindUpload = (gated)=>{
      const calId = gated ? 'file-gated-cal' : 'file-ungated-cal';
      const schedId = gated ? 'file-gated-sched' : 'file-ungated-sched';
      const btnId = gated ? 'btn-upload-gated' : 'btn-upload-ungated';
      const msgId = gated ? 'msg-gated' : 'msg-ungated';
      const ver = gated ? 'gated' : 'ungated';
      document.getElementById(btnId)?.addEventListener('click', async ()=>{
        const cal = document.getElementById(calId).files[0];
        const sched = document.getElementById(schedId).files[0];
        if(!cal || !sched){ alert('Select both calendar and schedule'); return; }
        const fd = new FormData();
        fd.append('version', ver);
        fd.append('calendar', cal);
        fd.append('schedule', sched);
        const msg = document.getElementById(msgId);
        if(msg) msg.textContent='Uploading...';
        try{
          const r = await fetch(API_UPLOAD, {method:'POST', body:fd});
          const j = await r.json();
          if(!r.ok) throw new Error(j.error||'upload failed');
          if(msg) msg.textContent=`✅ ${j.lines} lines`;
          setTimeout(()=> location.reload(), 800);
        }catch(e){ if(msg) msg.textContent='❌ '+e.message; }
      });
    };
    bindUpload(true);
    bindUpload(false);

    document.getElementById('btn-load-demo')?.addEventListener('click', async ()=>{
      const msg = document.getElementById('msg-demo');
      if(msg) msg.textContent='Loading demo...';
      try{
        const r = await fetch(API_DEMO, {method:'POST'});
        const j = await r.json();
        if(!r.ok) throw new Error(j.error||'failed');
        if(msg) msg.textContent=`✅ Demo loaded: ${j.lines} lines`;
        setTimeout(async ()=>{ await loadMeta(); setupLineDropdown(meta.lines); applyPivot(); }, 800);
      }catch(e){ if(msg) msg.textContent='❌ '+e.message; }
    });

    // Column dimension toggle (Day / Shift) like I/O Report
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
