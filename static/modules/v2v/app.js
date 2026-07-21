// V2V Module Frontend - Refactored 2026-07-21 v3 per user feedback
// - Detail Comparison title short, no long explanations
// - Download/Export moved to page top right (HTML)
// - Only Diff checkbox removed (always only diff)
// - Table columns Diff/Tag/Diff% centered
// - Tabs/cards no numeric badge, only light yellow color for diff

const V2V_TABLE_DEFS = {
  bom: {name: 'BOM Snapshot', cat: 'input', icon: '📦'},
  fcst: {name: 'FCST', cat: 'input', icon: '📊'},
  supply: {name: 'Supply', cat: 'input', icon: '🚚'},
  switch: {name: 'Switch Matrix', cat: 'input', icon: '🔀'},
  item: {name: 'Item Master', cat: 'input', icon: '🏷️'},
  line: {name: 'Line Master', cat: 'input', icon: '🧵'},
  calendar: {name: 'Line Calendar', cat: 'input', icon: '📅'},
  plan_config: {name: 'Plan Config', cat: 'input', icon: '⚙️'},
  plan_input: {name: 'Plan Input', cat: 'output', icon: '📥', fixedSku: true},
  plan_output: {name: 'Plan Output', cat: 'output', icon: '📋', fixedSku: true},
  balance: {name: 'BOH', cat: 'output', icon: '📦', fixedSku: true},
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
  filters: {changeType: 'ALL', onlyDiff: true} // always only diff
};

function v2vInit() {
  console.log('V2V Init v3 - simplified UI, centered Diff/Tag');
  setupV2VGranularity();
  setupV2VServerVersions();
  setupV2VFilters();
  fetch('/v2v/templates/schema').then(r=>r.json()).then(data=>{
    console.log('V2V schema loaded', Object.keys(data).length);
  }).catch(()=>{});
}

function setupV2VGranularity() {
  document.querySelectorAll('.v2v-granularity-toggle button').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      document.querySelectorAll('.v2v-granularity-toggle button').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      v2vState.granularity = btn.dataset.granularity;
      v2vState.currentPage = 1;
      if (v2vState.jobId) loadV2VDetail(v2vState.activeTable);
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
  const dlBtn = document.getElementById('v2v-btn-download');
  if (dlBtn) dlBtn.addEventListener('click', downloadV2VCurrentView);
  const exportBtn = document.getElementById('v2v-btn-export-html');
  if (exportBtn) exportBtn.addEventListener('click', exportV2VHtmlReport);
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
      change_type: v2vState.filters.changeType || 'ALL'
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
  if(statusEl) statusEl.innerHTML='<div class="v2v-status info">⏳ Comparing server folders...</div>';
  if(btn){ btn.disabled=true; btn.textContent='⏳ Comparing...'; }
  try{
    const resp=await fetch('/v2v/api/compare',{method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({a_path:aPath,b_path:bPath,granularity:v2vState.granularity})});
    const data=await resp.json(); if(data.error) throw new Error(data.error); handleCompareResult(data);
  }catch(e){ if(statusEl) statusEl.innerHTML=`<div class="v2v-status error">❌ ${e.message}</div>`; }
  finally{ if(btn){ btn.disabled=false; btn.textContent='▶ Compare'; } }
}

function handleCompareResult(data){
  console.log('Compare result', data);
  v2vState.jobId=data.job_id; v2vState.summary=data.summary||{}; v2vState.diffs=data.diffs||{};
  const statusEl=document.getElementById('v2v-status');
  if(statusEl){ statusEl.innerHTML=`<div class="v2v-status success">✅ Compare completed! Job: ${data.job_id} | Tables: ${Object.keys(data.summary).length}</div>`; }
  const summarySection=document.getElementById('v2v-summary-section'); if(summarySection) summarySection.style.display='block';
  renderSummaryCards(data);
  const detailSection=document.getElementById('v2v-detail-section'); if(detailSection) detailSection.style.display='block';
  renderDetailTabs(data);
  const firstTable=Object.keys(data.summary)[0]||'bom'; v2vState.activeTable=firstTable; loadV2VDetail(firstTable);
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
    // Per user: must be either yellow (has diff) or green (no diff), no gray.
    // For fast_summary (large tables), we only have row counts, but we still must choose yellow/green.
    // Rule: if added/deleted/modified>0 or total_a != total_b => yellow, else green.
    // Special for plan_input (virtual 0/0) -> use fcst diff as proxy
    let hasDiff = (s.total_a !== s.total_b) || ((s.added||0)+(s.deleted||0)+(s.modified||0) > 0);
    if(key==='plan_input'){
      const fcst = summary['fcst'];
      if(fcst && ((fcst.added||0)+(fcst.deleted||0)+(fcst.modified||0)>0 || fcst.total_a!==fcst.total_b)){
        hasDiff = true;
      }
    }
    // For fast tables with equal totals, previously we left gray, now per user must be green (assume no diff if totals equal)
    // This makes supply/calendar green when counts equal, which is desired to avoid false yellow
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
          ` : `<div style="font-size:11px;margin-top:6px;padding:4px 6px;border-radius:4px;${hasDiff ? 'background:#fffbeb;color:#92400e' : 'background:#f0fdf4;color:#166534'}">${hasDiff ? '⚠️ Has diff - click tab for SKU level detail' : '✅ No diff (row counts equal) - green'}</div>`}
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
      // Special for plan_input which is virtual 0/0 but actually has diff via fcst
      if(key==='plan_input'){
        const fcst = summary['fcst'];
        if(fcst && ((fcst.added||0)+(fcst.deleted||0)+(fcst.modified||0)>0 || fcst.total_a!==fcst.total_b)) hasDiff=true;
      }
      // Must be either yellow or green, no gray per user request
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
  const detailSection=document.getElementById('v2v-detail-section');
  if(detailSection){ setTimeout(()=>detailSection.scrollIntoView({behavior:'smooth', block:'start'}),100); }
  loadV2VDetail(tableName);
}

async function loadV2VDetail(tableName){
  const wrapper=document.getElementById('v2v-detail-content'); if(!wrapper) return;
  const displayName=tableName==='balance'?'BOH':(V2V_TABLE_DEFS[tableName]?.name||tableName);
  const isSkuLevel=V2V_TABLE_DEFS[tableName]?.fixedSku;
  wrapper.innerHTML=`<div class="v2v-loading"><div class="v2v-spinner"></div>Loading ${displayName} (${v2vState.granularity})...</div>`;
  try{
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
  }catch(e){ wrapper.innerHTML=`<div class="v2v-status error">❌ Failed to load: ${e.message}</div>`; }
}

function renderV2VTableDetail(data, tableName){
  const wrapper=document.getElementById('v2v-detail-content'); if(!wrapper) return;
  const records=data.records||[]; const pagination=data.pagination||{}; const def=V2V_TABLE_DEFS[tableName]||{name:tableName};
  const displayName=tableName==='balance'?'BOH':def.name; const isSkuLevel=def.fixedSku;
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
  }else if(isSkuLevel){
    const skuCol=tableName==='balance'?'ITEM_CODE':'SKU';
    html+=`<th>${granLabel === 'Month' ? 'Month' : granLabel === 'Week' ? 'Week' : granLabel}</th>`;
    html+=`<th>${skuCol}</th>`;
    html+=`<th class="col-center">Previous</th>`;
    html+=`<th class="col-center">Latest</th>`;
    html+=`<th class="col-center">Diff</th>`;
    html+=`<th class="col-center">Tag</th>`;
    html+=`<th class="col-center">Diff%</th>`;
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
    }else if(isSkuLevel){
      const skuVal=rec.SKU||rec.ITEM_CODE||rec.PN_CODE||'Unknown';
      const timeVal=rec.TIME||rec.TIME_LABEL||rec._WEEK||rec._DATE||rec._MONTH||'';
      const prevVal=rec.PREV??rec.PREVIOUS??0; const latestVal=rec.LATEST??rec.LATEST_VALUE??0;
      const diffVal=rec.DIFF??rec.diff??0;
      let diffPct=rec.diff_pct;
      if(diffPct===undefined||diffPct===null){ diffPct = prevVal!==0 ? (diffVal/prevVal*100) : (diffVal!==0?100:0); }
      const diffColor=diffVal>0?'#16a34a':diffVal<0?'#dc2626':'#64748b';
      const diffPctStr = (diffPct!==undefined && diffPct!==null && diffPct!==0) ? Number(diffPct).toFixed(1)+'%' : (diffVal!==0 ? (diffPct===0?'0.0%':Number(diffPct).toFixed(1)+'%') : '0.0%');
      html+=`<tr class="diff-${ctLower}">
        <td>${esc(String(timeVal).slice(0,10))}</td>
        <td style="font-weight:600">${esc(String(skuVal))}</td>
        <td class="col-center" style="text-align:center">${Number(prevVal).toLocaleString()}</td>
        <td class="col-center" style="text-align:center">${Number(latestVal).toLocaleString()}</td>
        <td class="col-center" style="text-align:center;font-weight:700;color:${diffColor}">${(diffVal>0?'+':'')+Number(diffVal).toLocaleString()}</td>
        <td class="col-center" style="text-align:center"><span class="v2v-change-badge ${ctLower}">${badge}</span></td>
        <td class="col-center" style="text-align:center;color:${diffColor}">${diffPctStr}</td>
      </tr>`;
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
  loadV2VDetail(v2vState.activeTable);
}
function esc(s){ if(s==null) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
window.selectV2VTable=selectV2VTable; window.drillTo=drillTo; window.v2vState=v2vState; window.loadV2VDetail=loadV2VDetail; window.v2vInit=v2vInit;
window.downloadV2VCurrentView=downloadV2VCurrentView; window.exportV2VHtmlReport=exportV2VHtmlReport;
if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', v2vInit); }else{ v2vInit(); }
