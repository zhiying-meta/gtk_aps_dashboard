/**
 * Utilization Report - Line Utilization = Load / Capacity
 * Capacity = UPH * efficiency * working_hours (from calendar snapshot INPUT)
 * Load = sum(schedule INPUT)
 */

(() => {
  const API_STATUS = '/api/utilization/status';
  const API_META = '/api/utilization/meta';
  const API_REPORTS = '/api/utilization/reports';
  const API_UPLOAD = '/api/utilization/upload';
  const API_DEMO = '/api/utilization/demo/load';

  let meta = null;
  let currentMode = 'shift'; // shift or day
  let currentVersion = 'gated'; // gated, ungated, compare
  let allLines = [];
  let currentRecords = [];

  function esc(s){ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }

  function getRoot(){ return document.getElementById('utilization-section'); }

  async function fetchJSON(url){
    const r = await fetch(url);
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
      allLines = meta.lines || [];
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
      let totalShift = 0, totalDay=0;
      Object.values(details).forEach(d=>{ totalShift+=d.records_shift||0; totalDay+=d.records_day||0; });
      return `<span class="util-status-badge ready">✅ Ready: ${vers} | ${totalShift} shift recs / ${totalDay} day recs</span>`;
    }else{
      return `<span class="util-status-badge empty">No data loaded — upload calendar + schedule or load demo</span>`;
    }
  }

  function buildUploadHTML(){
    return `
      <div class="section">
        <div class="section-header">
          <span class="section-title">⚙️ Line Utilization — Upload</span>
          <span id="util-status-badge"></span>
        </div>
        <div style="padding:12px;background:#f8fafc;border:1px dashed #cbd5e1;border-radius:6px;font-size:12px;color:#475569;margin-bottom:12px">
          <b>Logic:</b> Per line/date/shift: <code>Capacity = UPH × Efficiency × WorkingHours</code> (from calendar snapshot INPUT, PLAN_TYPE=UPH/效率/工时)<br>
          <code>Load = Σ schedule INPUT qty</code> (from schedule result). <code>Utilization = Load / Capacity</code><br>
          Supports gated / ungated dual upload — if only one version present, fallback to single view. Gantt similar to I/O Report, switchable shift/day.
        </div>
        <div class="util-upload-grid">
          <div class="util-upload-card" id="card-gated">
            <div class="util-upload-label">Gated Version</div>
            <div class="util-upload-hint">Upload calendar + schedule for gated</div>
            <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
              <div><label style="font-size:11px">Calendar (工作日历快照.xlsx)</label><br><input type="file" id="file-gated-cal" accept=".xlsx"></div>
              <div><label style="font-size:11px">Schedule (排产结果表.xlsx)</label><br><input type="file" id="file-gated-sched" accept=".xlsx"></div>
            </div>
            <div style="margin-top:8px"><button class="util-btn" id="btn-upload-gated">Upload Gated</button> <span id="msg-gated" style="font-size:11px;color:#64748b"></span></div>
          </div>
          <div class="util-upload-card" id="card-ungated">
            <div class="util-upload-label">Ungated Version (optional)</div>
            <div class="util-upload-hint">Optional second version for compare</div>
            <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
              <div><label style="font-size:11px">Calendar</label><br><input type="file" id="file-ungated-cal" accept=".xlsx"></div>
              <div><label style="font-size:11px">Schedule</label><br><input type="file" id="file-ungated-sched" accept=".xlsx"></div>
            </div>
            <div style="margin-top:8px"><button class="util-btn" id="btn-upload-ungated">Upload Ungated</button> <span id="msg-ungated" style="font-size:11px;color:#64748b"></span></div>
          </div>
        </div>
        <div style="text-align:center;margin:12px 0">
          <button class="util-btn util-btn-outline" id="btn-load-demo">📦 Load Demo Data (IVY20260721Gated)</button>
          <span id="msg-demo" style="font-size:11px;margin-left:8px;color:#64748b"></span>
        </div>
      </div>
    `;
  }

  function buildToolbarHTML(){
    const linesOptions = (allLines||[]).slice(0,200).map(l=>`<option value="${esc(l)}">${esc(l)}</option>`).join('');
    return `
      <div class="util-toolbar">
        <div class="util-filter-group">
          <label>Mode</label>
          <div class="util-toggle-group">
            <button id="btn-mode-shift" class="${currentMode==='shift'?'active':''}">Shift</button>
            <button id="btn-mode-day" class="${currentMode==='day'?'active':''}">Day</button>
          </div>
        </div>
        <div class="util-filter-group">
          <label>Version</label>
          <div class="util-toggle-group">
            <button id="btn-ver-gated" class="${currentVersion==='gated'?'active':''}">Gated</button>
            <button id="btn-ver-ungated" class="${currentVersion==='ungated'?'active':''}">Ungated</button>
            <button id="btn-ver-compare" class="${currentVersion==='compare'?'active':''}">Compare</button>
          </div>
        </div>
        <div class="util-filter-group">
          <label>Line</label>
          <select id="util-filter-line"><option value="">All</option>${linesOptions}</select>
        </div>
        <div class="util-filter-group">
          <label>Shift</label>
          <select id="util-filter-shift"><option value="">All</option><option value="白班">白班 (Day)</option><option value="夜班">夜班 (Night)</option></select>
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
          <button class="util-btn" id="btn-apply-filter">Apply</button>
        </div>
        <div class="util-filter-group">
          <label>&nbsp;</label>
          <span id="util-report-count" style="font-size:12px;color:#64748b"></span>
        </div>
      </div>
    `;
  }

  function pctClass(pct){
    const v = parseFloat(pct);
    if(isNaN(v)) return 'util-pct-low';
    if(v>100) return 'util-pct-over';
    if(v>=80) return 'util-pct-high';
    if(v>=50) return 'util-pct-mid';
    return 'util-pct-low';
  }

  function barClass(pct){
    const v = parseFloat(pct);
    if(v>100) return 'over';
    if(v>=80) return 'high';
    if(v>=50) return 'mid';
    return 'low';
  }

  function renderTable(records){
    if(!records || records.length===0){
      return `<div style="text-align:center;padding:30px;color:#94a3b8">No matching records</div>`;
    }
    // Summary cards
    const avgs = records.reduce((acc,r)=> acc + (r.utilization_pct||r.gated_utilization_pct||0),0) / records.length;
    const over100 = records.filter(r=> (r.utilization_pct||r.gated_utilization_pct||0) > 100).length;
    const cards = `
      <div class="util-card-grid">
        <div class="util-card"><div class="util-card-title">Avg Utilization</div><div class="util-card-metric">${avgs.toFixed(1)}%</div><div class="util-card-sub">${records.length} records, mode=${currentMode}</div></div>
        <div class="util-card"><div class="util-card-title">Over 100%</div><div class="util-card-metric" style="color:${over100>0?'#dc2626':'#059669'}">${over100}</div><div class="util-card-sub">Lines exceeding capacity</div></div>
        <div class="util-card"><div class="util-card-title">Total Load</div><div class="util-card-metric">${records.reduce((s,r)=>s+(r.load||r.gated_load||0),0).toLocaleString()}</div><div class="util-card-sub">Sum qty (INPUT)</div></div>
      </div>
    `;

    if(currentVersion==='compare'){
      let html = cards + `<div class="util-table-wrapper"><table><thead><tr><th>Line</th><th>Date</th><th>Shift</th><th>Gated Load</th><th>Gated Cap</th><th>Gated Util%</th><th>Ungated Load</th><th>Ungated Cap</th><th>Ungated Util%</th><th>Δ Util%</th><th>Δ Load</th></tr></thead><tbody>`;
      for(const r of records.slice(0,500)){
        html+=`<tr>
          <td>${esc(r.line_code)}</td>
          <td>${esc(r.plan_date)}</td>
          <td>${esc(r.shift_name)}</td>
          <td class="util-cell-num">${(r.gated_load||0).toLocaleString()}</td>
          <td class="util-cell-num">${(r.gated_capacity||0).toLocaleString()}</td>
          <td><span class="${pctClass(r.gated_utilization_pct)}">${r.gated_utilization_pct!=null?r.gated_utilization_pct+'%':''}</span></td>
          <td class="util-cell-num">${r.ungated_load!=null? r.ungated_load.toLocaleString():''}</td>
          <td class="util-cell-num">${r.ungated_capacity!=null? r.ungated_capacity.toLocaleString():''}</td>
          <td><span class="${r.ungated_utilization_pct!=null? pctClass(r.ungated_utilization_pct):''}">${r.ungated_utilization_pct!=null? r.ungated_utilization_pct+'%':''}</span></td>
          <td class="util-cell-num" style="color:${(r.delta_utilization||0)>0?'#dc2626':'#059669'}">${r.delta_utilization!=null? r.delta_utilization+'%':''}</td>
          <td class="util-cell-num">${r.delta_load!=null? r.delta_load.toLocaleString():''}</td>
        </tr>`;
      }
      html+='</tbody></table></div>';
      return html;
    }else{
      let html = cards + `<div class="util-table-wrapper"><table><thead><tr><th>Line</th><th>Date</th><th>Shift</th><th>UPH</th><th>Eff</th><th>WH</th><th>Capacity</th><th>Load</th><th>Util%</th><th>Gantt</th></tr></thead><tbody>`;
      for(const r of records.slice(0,500)){
        const pct = r.utilization_pct||0;
        const w = Math.min(100, pct);
        html+=`<tr>
          <td>${esc(r.line_code)}</td>
          <td>${esc(r.plan_date)}</td>
          <td>${esc(r.shift_name)}</td>
          <td class="util-cell-num">${r.uph||''}</td>
          <td class="util-cell-num">${r.efficiency||''}</td>
          <td class="util-cell-num">${r.working_hours||''}</td>
          <td class="util-cell-num">${(r.capacity||0).toLocaleString()}</td>
          <td class="util-cell-num">${(r.load||0).toLocaleString()}</td>
          <td><span class="${pctClass(pct)}">${pct}%</span></td>
          <td style="min-width:120px"><div style="width:100px;height:12px;background:#f1f5f9;border-radius:6px;overflow:hidden"><div class="util-gantt-bar ${barClass(pct)}" style="width:${w}%;height:100%"></div></div></td>
        </tr>`;
      }
      html+='</tbody></table></div>';
      return html;
    }
  }

  function renderGantt(records){
    // Group by line, sorted by date
    const byLine = {};
    records.forEach(r=>{
      if(!byLine[r.line_code]) byLine[r.line_code]=[];
      byLine[r.line_code].push(r);
    });
    const lines = Object.keys(byLine).sort().slice(0,20); // limit 20 lines for gantt
    let html = `<div style="margin-top:16px"><div style="font-weight:600;font-size:13px;margin-bottom:8px">Gantt — Utilization by ${currentMode} (top 20 lines)</div>`;
    for(const line of lines){
      const recs = byLine[line].sort((a,b)=> a.plan_date.localeCompare(b.plan_date) || (a.shift_name||'').localeCompare(b.shift_name||'')).slice(0,30);
      html+=`<div style="margin-bottom:10px;border:1px solid #e2e8f0;border-radius:6px;padding:6px"><div style="font-weight:600;font-size:12px;color:#0f172a;margin-bottom:4px">${esc(line)} (${recs.length} points)</div>`;
      for(const r of recs){
        const pct = r.utilization_pct || r.gated_utilization_pct || 0;
        html+=`<div class="util-gantt-row"><div class="util-gantt-date">${esc(r.plan_date)} ${esc(r.shift_name||'')}</div><div class="util-gantt-track"><div class="util-gantt-bar ${barClass(pct)}" style="width:${Math.min(100,pct)}%">${pct}%</div></div><div style="width:50px;font-size:11px;color:#64748b">${(r.load||r.gated_load||0).toLocaleString()}</div></div>`;
      }
      html+='</div>';
    }
    html+='</div>';
    return html;
  }

  async function loadAndRender(){
    const line = document.getElementById('util-filter-line')?.value || '';
    const shift = document.getElementById('util-filter-shift')?.value || '';
    const from = document.getElementById('util-filter-from')?.value || '';
    const to = document.getElementById('util-filter-to')?.value || '';

    const params = new URLSearchParams({mode: currentMode, version: currentVersion, line_code: line, shift_name: shift, date_from: from, date_to: to});
    try{
      const res = await fetchJSON(`${API_REPORTS}?${params.toString()}`);
      currentRecords = res.records || [];
      document.getElementById('util-report-count').textContent = `${res.total||currentRecords.length} total, showing ${currentRecords.length}`;
      const tableHTML = renderTable(currentRecords);
      const ganttHTML = renderGantt(currentRecords);
      document.getElementById('util-report-area').innerHTML = tableHTML + ganttHTML;
    }catch(e){
      document.getElementById('util-report-area').innerHTML = `<div style="color:#dc2626;padding:12px">Error: ${esc(e.message)}</div>`;
    }
  }

  async function render(){
    const root = getRoot();
    if(!root) return;
    const status = await checkStatus();
    const metaLoaded = await loadMeta();

    let html = '';
    html += buildUploadHTML();
    html += `<div id="util-main-panel" style="${status.loaded?'':'display:none'}">`;
    html += buildToolbarHTML();
    html += `<div id="util-report-area" style="min-height:200px;text-align:center;padding:30px;color:#94a3b8">Loading...</div>`;
    html += `</div>`;

    root.innerHTML = html;

    // Update badge
    setTimeout(()=>{
      const badge = document.getElementById('util-status-badge');
      if(badge) badge.innerHTML = statusBadgeHTML(status);
    },0);

    // Bind events
    document.getElementById('btn-mode-shift')?.addEventListener('click', ()=>{
      currentMode='shift';
      document.getElementById('btn-mode-shift').classList.add('active');
      document.getElementById('btn-mode-day').classList.remove('active');
      loadAndRender();
    });
    document.getElementById('btn-mode-day')?.addEventListener('click', ()=>{
      currentMode='day';
      document.getElementById('btn-mode-day').classList.add('active');
      document.getElementById('btn-mode-shift').classList.remove('active');
      loadAndRender();
    });
    document.getElementById('btn-ver-gated')?.addEventListener('click', ()=>{
      currentVersion='gated';
      document.querySelectorAll('[id^=btn-ver-]').forEach(b=>b.classList.remove('active'));
      document.getElementById('btn-ver-gated').classList.add('active');
      loadAndRender();
    });
    document.getElementById('btn-ver-ungated')?.addEventListener('click', ()=>{
      currentVersion='ungated';
      document.querySelectorAll('[id^=btn-ver-]').forEach(b=>b.classList.remove('active'));
      document.getElementById('btn-ver-ungated').classList.add('active');
      loadAndRender();
    });
    document.getElementById('btn-ver-compare')?.addEventListener('click', ()=>{
      currentVersion='compare';
      document.querySelectorAll('[id^=btn-ver-]').forEach(b=>b.classList.remove('active'));
      document.getElementById('btn-ver-compare').classList.add('active');
      loadAndRender();
    });
    document.getElementById('btn-apply-filter')?.addEventListener('click', loadAndRender);

    // Upload handlers
    document.getElementById('btn-upload-gated')?.addEventListener('click', async ()=>{
      const cal = document.getElementById('file-gated-cal').files[0];
      const sched = document.getElementById('file-gated-sched').files[0];
      if(!cal || !sched){ alert('Select both calendar and schedule files for gated'); return; }
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
        msg.textContent=`✅ ${j.lines} lines, ${j.records_shift} shift recs`;
        setTimeout(()=> location.reload(), 800);
      }catch(e){ msg.textContent='❌ '+e.message; }
    });
    document.getElementById('btn-upload-ungated')?.addEventListener('click', async ()=>{
      const cal = document.getElementById('file-ungated-cal').files[0];
      const sched = document.getElementById('file-ungated-sched').files[0];
      if(!cal || !sched){ alert('Select both calendar and schedule for ungated'); return; }
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
        setTimeout(()=> location.reload(), 800);
      }catch(e){ msg.textContent='❌ '+e.message; }
    });

    if(status.loaded){
      await loadAndRender();
    }else{
      document.getElementById('util-main-panel').style.display='none';
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
