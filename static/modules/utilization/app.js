/**
 * Utilization Report - Matrix view like I/O Report
 * Line fixed, dates horizontal, cell = utilization %
 * Capacity = UPH * Eff * WH, Load = schedule INPUT sum
 * Capped at 100% for display, raw kept for tooltip (overload >100% means over capacity)
 */

(() => {
  const API_STATUS = '/api/utilization/status';
  const API_META = '/api/utilization/meta';
  const API_PIVOT = '/api/utilization/pivot';
  const API_UPLOAD = '/api/utilization/upload';
  const API_DEMO = '/api/utilization/demo/load';

  let meta = null;
  let currentMode = 'day'; // day or shift - day is default for matrix (less columns)
  let currentVersion = 'gated';
  let pivotCache = null; // last pivot response

  function esc(s){ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }

  function getRoot(){ return document.getElementById('utilization-section'); }

  async function fetchJSON(url, opts){
    const r = await fetch(url, opts);
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  }

  async function checkStatus(){
    try{
      const s = await fetchJSON(API_STATUS);
      return s;
    }catch(e){
      return {loaded:false, error: e.message};
    }
  }

  async function loadMeta(){
    try{
      meta = await fetchJSON(API_META);
      return true;
    }catch(e){
      meta = null;
      return false;
    }
  }

  function statusBadgeHTML(status){
    if(status && status.loaded){
      const vers = (status.versions||[]).join(', ')||'gated';
      const details = status.details||{};
      let totalShift = 0;
      Object.values(details).forEach(d=>{ totalShift+=d.records_shift||0; });
      // If details empty (fast status), show versions only
      if(totalShift===0) return `<span class="util-status-badge ready">✅ Ready: ${vers} — click to load matrix</span>`;
      return `<span class="util-status-badge ready">✅ Ready: ${vers} | ${totalShift} shift recs</span>`;
    }else{
      return `<span class="util-status-badge empty">No data — upload calendar + schedule or load demo</span>`;
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
          <b>Formula:</b> Per line/date/shift: <code>Capacity = UPH × Efficiency × WorkingHours</code> (from calendar snapshot INPUT, PLAN_TYPE=UPH/效率/工时)<br>
          <code>Load = Σ schedule INPUT qty</code> — <code>Util% = Load / Capacity</code> capped at 100% (raw kept in tooltip, >100% = overload)<br>
          Matrix view like I/O Report: Line fixed, dates horizontal draggable, cell = Util%
        </div>
        <div class="util-upload-grid">
          <div class="util-upload-card" id="card-gated">
            <div class="util-upload-label">Gated Version</div>
            <div class="util-upload-hint">Calendar + Schedule (gated)</div>
            <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
              <div><label style="font-size:11px">Calendar</label><br><input type="file" id="file-gated-cal" accept=".xlsx"></div>
              <div><label style="font-size:11px">Schedule</label><br><input type="file" id="file-gated-sched" accept=".xlsx"></div>
            </div>
            <div style="margin-top:8px"><button class="util-btn" id="btn-upload-gated">Upload Gated</button> <span id="msg-gated" style="font-size:11px;color:#64748b"></span></div>
          </div>
          <div class="util-upload-card" id="card-ungated">
            <div class="util-upload-label">Ungated (optional)</div>
            <div class="util-upload-hint">For compare mode</div>
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

  function buildMatrixToolbar(){
    return `
      <div class="section">
        <div class="section-header">
          <span class="section-title">⚙️ Line Utilization — Matrix (Line fixed, Date horizontal)</span>
          <span id="util-matrix-badge" style="font-size:11px;color:#64748b"></span>
        </div>
        <div class="util-toolbar">
          <div class="util-filter-group">
            <label>Mode</label>
            <div class="util-toggle-group">
              <button id="btn-mode-day" class="${currentMode==='day'?'active':''}">Day</button>
              <button id="btn-mode-shift" class="${currentMode==='shift'?'active':''}">Shift</button>
            </div>
          </div>
          <div class="util-filter-group">
            <label>Version</label>
            <div class="util-toggle-group">
              <button id="btn-ver-gated" class="${currentVersion==='gated'?'active':''}">Gated</button>
              <button id="btn-ver-ungated" class="${currentVersion==='ungated'?'active':''}">Ungated</button>
            </div>
          </div>
          <div class="util-filter-group">
            <label>Line Filter</label>
            <input type="text" id="util-filter-line" placeholder="e.g. AL1-PKG">
          </div>
          <div class="util-filter-group">
            <label>Date From</label>
            <input type="date" id="util-filter-from">
          </div>
          <div class="util-filter-group">
            <label>Date To</label>
            <input type="date" id="util-filter-to">
          </div>
          <div class="util-filter-group">
            <label>&nbsp;</label>
            <button class="util-btn" id="btn-apply-pivot">Apply / Reload</button>
          </div>
          <div class="util-filter-group">
            <label>Legend</label>
            <div style="display:flex;gap:6px;align-items:center;font-size:11px">
              <span style="background:#ecfdf5;color:#059669;padding:2px 6px;border-radius:10px">0-50%</span>
              <span style="background:#fffbeb;color:#d97706;padding:2px 6px;border-radius:10px">50-80%</span>
              <span style="background:#ffedd5;color:#ea580c;padding:2px 6px;border-radius:10px">80-100%</span>
              <span style="background:#fef2f2;color:#dc2626;padding:2px 6px;border-radius:10px;border:1px solid #fecaca">>100% Overload capped at 100%</span>
            </div>
          </div>
        </div>
        <div id="util-matrix-wrapper" class="util-table-wrapper" style="max-height:calc(100vh - 300px)">
          <div style="text-align:center;padding:30px;color:#94a3b8">Loading matrix...</div>
        </div>
      </div>
    `;
  }

  function pctColorClass(pct, isOverload){
    if(isOverload || pct>100) return 'util-cell-over';
    if(pct>=80) return 'util-cell-high';
    if(pct>=50) return 'util-cell-mid';
    if(pct>0) return 'util-cell-low';
    return 'util-cell-zero';
  }

  function renderMatrix(pivot){
    pivotCache = pivot;
    const cols = pivot.columns || [];
    const rows = pivot.rows || [];
    const detail = pivot.detail || {};

    if(rows.length===0){
      document.getElementById('util-matrix-wrapper').innerHTML = `<div style="text-align:center;padding:30px;color:#94a3b8">No data for current filter</div>`;
      return;
    }

    // Build header
    let thead = `<tr><th class="frozen" style="left:0;min-width:130px;z-index:11">Line</th>`;
    // For shift mode, columns are like 2026-06-18|白班, we display as two rows? Simplify: show date and shift
    cols.forEach(col=>{
      // col for shift mode is date|shift, for day mode just date
      let label = col;
      let sub = '';
      if(col.includes('|')){
        const parts = col.split('|');
        label = parts[0];
        sub = parts[1];
      }
      // Shorten date: show MM-DD
      let short = label;
      try{
        const d = new Date(label);
        if(!isNaN(d)) short = `${d.getMonth()+1}/${d.getDate()}`;
      }catch{}
      thead += `<th style="min-width:68px;text-align:center" title="${esc(col)}">${esc(short)}${sub?`<br><span style="font-size:9px;color:#cbd5e1">${esc(sub)}</span>`:''}</th>`;
    });
    thead += `</tr>`;

    // For second header row showing full date? Keep simple one row
    let tbody = '';
    rows.forEach(r=>{
      const line = r.line_code;
      tbody += `<tr>`;
      tbody += `<td class="frozen" style="left:0;background:#fff;z-index:5;font-weight:600;min-width:130px">${esc(line)}</td>`;
      cols.forEach(col=>{
        const val = r[col]; // capped %
        const det = (detail[line] && detail[line][col]) ? detail[line][col] : null;
        if(val==null){
          tbody += `<td style="background:#f8fafc"></td>`;
        }else{
          const raw = det ? det.util_raw : val;
          const isOver = det ? det.util_raw > 100 : val>100;
          const load = det ? det.load : '';
          const cap = det ? det.capacity : '';
          const cls = pctColorClass(val, isOver);
          // Show capped value, but if overload show 100%+ with raw in tooltip
          let display = `${Math.round(val)}%`;
          if(isOver) display = `100%<span style="font-size:8px">(${Math.round(raw)}%)</span>`;
          else if(val===0) display = `0%`;
          tbody += `<td class="${cls}" title="Line:${esc(line)} Date:${esc(col)} Load:${load} Cap:${cap} Raw:${raw}% (capped at 100%)" style="text-align:center;font-size:11px;font-weight:600;cursor:help">${display}</td>`;
        }
      });
      tbody += `</tr>`;
    });

    const tableHTML = `<table><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;
    document.getElementById('util-matrix-wrapper').innerHTML = tableHTML;

    // Update badge
    const badge = document.getElementById('util-matrix-badge');
    if(badge){
      const overCount = rows.reduce((acc,row)=>{
        let c=0;
        cols.forEach(col=>{
          const d = detail[row.line_code] && detail[row.line_code][col];
          if(d && d.util_raw>100) c++;
        });
        return acc+c;
      },0);
      badge.textContent = `${pivot.total_lines} lines × ${pivot.total_cols} dates, ${overCount} overload cells (capped at 100%, raw in tooltip)`;
    }
  }

  async function loadPivot(){
    const line = document.getElementById('util-filter-line')?.value || '';
    const from = document.getElementById('util-filter-from')?.value || '';
    const to = document.getElementById('util-filter-to')?.value || '';
    const params = new URLSearchParams({mode: currentMode, version: currentVersion, line_code: line, date_from: from, date_to: to});
    const wrapper = document.getElementById('util-matrix-wrapper');
    if(wrapper) wrapper.innerHTML = `<div style="text-align:center;padding:30px;color:#94a3b8">Loading pivot matrix (${currentMode}/${currentVersion})...</div>`;
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
    // Build page: upload + matrix
    let html = '';
    html += buildUploadHTML(status);
    html += buildMatrixToolbar();
    root.innerHTML = html;

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
        setTimeout(async ()=>{ await loadMeta(); await loadPivot(); document.getElementById('util-status-badge').innerHTML = statusBadgeHTML({loaded:true, versions:['gated'], details:{gated:{records_shift:j.records_shift}}}); }, 800);
      }catch(e){ msg.textContent='❌ '+e.message; }
    });

    // Bind toolbar
    document.getElementById('btn-mode-day')?.addEventListener('click', ()=>{
      currentMode='day';
      document.getElementById('btn-mode-day').classList.add('active');
      document.getElementById('btn-mode-shift').classList.remove('active');
      loadPivot();
    });
    document.getElementById('btn-mode-shift')?.addEventListener('click', ()=>{
      currentMode='shift';
      document.getElementById('btn-mode-shift').classList.add('active');
      document.getElementById('btn-mode-day').classList.remove('active');
      loadPivot();
    });
    document.getElementById('btn-ver-gated')?.addEventListener('click', ()=>{
      currentVersion='gated';
      document.querySelectorAll('[id^=btn-ver-]').forEach(b=>b.classList.remove('active'));
      document.getElementById('btn-ver-gated').classList.add('active');
      loadPivot();
    });
    document.getElementById('btn-ver-ungated')?.addEventListener('click', ()=>{
      currentVersion='ungated';
      document.querySelectorAll('[id^=btn-ver-]').forEach(b=>b.classList.remove('active'));
      document.getElementById('btn-ver-ungated').classList.add('active');
      loadPivot();
    });
    document.getElementById('btn-apply-pivot')?.addEventListener('click', loadPivot);

    // Initial meta + pivot
    await loadMeta();
    if(status.loaded){
      await loadPivot();
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
