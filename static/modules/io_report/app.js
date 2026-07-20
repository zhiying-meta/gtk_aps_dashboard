/**
 * I/O Report - Optimized: Left Group Boxes + Dim-first + Lazy Expand + Paging
 */
(() => {
const DIM_LABELS = { ITEM_NO: 'PN', LINE_CODE: 'Line', STYLE: 'Style' };
const REPORTS = ['daily_input','daily_output','cum_input','cum_output','daily_checkin','daily_checkout','cum_checkin','cum_checkout','balance'];
const REPORT_NAMES = {
  daily_input: 'Daily Input',
  daily_output: 'Daily Output',
  daily_checkin: 'Daily Checkin',
  daily_checkout: 'Daily Checkout',
  cum_input: 'Cum Input',
  cum_output: 'Cum Output',
  cum_checkin: 'Cum Checkin',
  cum_checkout: 'Cum Checkout',
  balance: 'BOH'
};

let dimOrder = [];
let currentGroup = 'FG';
let allData = null;
let COL_DIM = 'day';
let dragFromDim = null;
const filterVals = { lineCode: '', itemNo: '', style: '' };
let ioRoot = null;
let reportGroups = REPORTS.map(r => [r]);
let pendingNewGroup = [];
let draggedReport = null;
const PAGE_SIZE = 200;
const treeCache = {}; // tableId -> tree root
let _ioClientCache = null; // client-side cache for offline

function esc(s){ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }
function getRoot(){ return document.getElementById('io-report-section'); }
function getStaticDBIO(){ try { return window.STATIC_DB || null; } catch(e){ return null; } }
function isPlanMergeStatic(){ const db=getStaticDBIO(); return !!(db && db.versions && db.versions.length>0); }
let _lastStatus = null;
async function checkStatus(){
  if (_ioClientCache){
    _lastStatus = {loaded:true, fg: _ioClientCache.fgItems.length, gb: _ioClientCache.gbItems.length, client:true};
    return true;
  }
  try{
    const r = await fetch('/api/io/status');
    const j = await r.json();
    _lastStatus = j;
    try{ localStorage.setItem('io_report_status', JSON.stringify({ ...j, time: new Date().toISOString() })); }catch{}
    return !!j.loaded;
  }catch{ return false; }
}
async function getFullStatus(){
  if (_ioClientCache){
    return {loaded:true, fg: _ioClientCache.fgItems.length, gb: _ioClientCache.gbItems.length, client:true};
  }
  try{
    if(_lastStatus) return _lastStatus;
    const r = await fetch('/api/io/status');
    const j = await r.json();
    _lastStatus = j;
    return j;
  }catch{ return { loaded:false }; }
}
function saveIOLoadStatus(info){
  try{ localStorage.setItem('io_report_last_load', JSON.stringify(info)); }catch{}
}
function loadIOLoadStatus(){
  try{
    const s = localStorage.getItem('io_report_last_load');
    if(s) return JSON.parse(s);
  }catch{}
  return null;
}
function getStatusBadgeHTML(){
  const info = loadIOLoadStatus();
  const st = _lastStatus;
  if(st && st.loaded){
    const fg = st.fg||0, gb = st.gb||0;
    const time = info && info.time ? new Date(info.time).toLocaleString() : '';
    return `<span style="background:#dcfce7;color:#065f46;border:1px solid #86efac;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">✅ Ready: ${fg} FG / ${gb} GB ${time? '· '+esc(time):''}</span>`;
  }else if(info){
    return `<span style="background:#dcfce7;color:#065f46;border:1px solid #86efac;padding:2px 8px;border-radius:12px;font-size:11px">✅ Last: ${esc(info.fg||0)} FG / ${esc(info.gb||0)} GB · ${esc(info.timeStr||'') || 'ready'}</span>`;
  }else{
    return `<span style="background:#f1f5f9;color:#64748b;border:1px solid #e2e8f0;padding:2px 8px;border-radius:12px;font-size:11px">No data loaded</span>`;
  }
}
async function render(){
  ioRoot = getRoot();
  if(!ioRoot) return;
  // Client cache takes priority - true offline
  if (_ioClientCache){
    renderReportsPage();
    return;
  }
  // If in static offline mode, still allow IO upload via client engine
  if (isPlanMergeStatic()) {
    const db = getStaticDBIO();
    if (!db.io) {
      // Show upload page with client engine ability, not just notice
      // We still have offline plan_merge, but IO can be loaded via client engine
      const loaded = await checkStatus();
      if(loaded) { renderReportsPage(); return; }
      // Show upload page with extra banner explaining IO offline via client engine
      ioRoot.innerHTML = `
        <div class="section" style="background:linear-gradient(135deg,#eff6ff 0%,#f0fdf4 100%);border:1px solid #bfdbfe;padding:12px 16px">
          <div style="font-size:13px;font-weight:700;color:#1e40af">📦 Offline Mode - I/O Report 可用 (客户端引擎)</div>
          <div style="font-size:11px;color:#475569;margin-top:2px">当前离线包已包含 Gated/Ungated/CTB 数据，I/O Report 可通过下方上传 3 个文件或 combined 文件，在浏览器内直接计算，无需服务器</div>
        </div>
      ` + (await (async()=>{
        // We need to build upload section HTML manually? Use existing builder
        // For simplicity, call renderUploadPage after injecting banner
        return '';
      })());
      // Now render upload page normally (it will be appended below)
      renderUploadPage();
      // Prepend banner again after upload page rendered to top
      setTimeout(()=>{
        const upSec = document.getElementById('io-upload-section') || document.getElementById('io-upload-bar');
        if (upSec && upSec.parentNode){
          const banner = document.createElement('div');
          banner.className='section';
          banner.style.cssText='background:linear-gradient(135deg,#eff6ff 0%,#f0fdf4 100%);border:1px solid #bfdbfe;padding:12px 16px;margin-bottom:12px';
          banner.innerHTML=`<div style="font-size:13px;font-weight:700;color:#1e40af">📦 Offline Mode - I/O Report 可用 (客户端引擎)</div><div style="font-size:11px;color:#475569;margin-top:2px">已内置浏览器版 I/O 引擎，上传 3 文件或 combined xlsx 即可生成 9 张报表，支持 Shift/Day/Week/Month、Line/ITEM/STYLE 维度、合并、下载 Excel</div>`;
          upSec.parentNode.insertBefore(banner, upSec);
        }
      }, 200);
      return;
    }
  }
  const loaded = await checkStatus();
  if(loaded) renderReportsPage();
  else renderUploadPage();
}

function buildUploadSectionHTML(isCompact){
  const title = isCompact ? '📁 Upload I/O Data' : '📁 Upload I/O Data';
  const statusBadge = getStatusBadgeHTML();
  return `<div class="section" id="${isCompact ? 'io-upload-bar' : 'io-upload-section'}">
      <div class="section-header">
        <div style="display:flex;align-items:center;gap:10px">
          <span class="section-title">${title}</span>
          <span id="ioStatusBadge_${isCompact?'compact':'full'}">${statusBadge}</span>
        </div>
        <div class="section-actions">
          <a href="/api/io/templates/input_template.xlsx" class="btn btn-sm btn-outline">📄 Combined Template</a>
          <a href="/api/io/templates/template" class="btn btn-sm btn-outline">📦 3 Templates (zip)</a>
          <a href="/api/io/templates/demo" class="btn btn-sm btn-outline">📦 Demo</a>
          <a href="/api/io/templates/schema" target="_blank" class="btn btn-sm btn-outline">📋 Schema</a>
          ${isCompact ? '<button class="btn btn-sm btn-outline" id="toggleUploadBar">▼ Collapse</button>' : ''}
        </div>
      </div>
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;margin-bottom:8px;font-size:11px;color:#475569;display:flex;justify-content:space-between;align-items:center">
        <span>💡 Accepts: 3 xlsx files, a .zip, or a single combined xlsx with 3 sheets</span>
        <span id="ioPersistentMsg_${isCompact?'compact':'full'}" style="font-size:11px;color:#059669;font-weight:600"></span>
      </div>
      <div id="${isCompact ? 'uploadBarContent' : 'uploadFullContent'}">
        <div class="upload-card" id="card_combined_${isCompact?'compact':'full'}" style="border:2px dashed #8b5cf6;background:#faf5ff;margin-bottom:10px">
          <div class="upload-label">⚡ Quick Upload <span style="font-size:10px;background:#8b5cf6;color:#fff;padding:1px 6px;border-radius:8px">Recommended</span></div>
          <div class="upload-hint">Select files, zip, or combined xlsx</div>
          <input type="file" class="file-input" id="input_combined_${isCompact?'compact':'full'}" accept=".xlsx,.zip" multiple>
          <div class="fname" id="fname_combined_${isCompact?'compact':'full'}" style="font-size:11px;color:#6d28d9;margin-top:6px;min-height:16px"></div>
        </div>
        <div style="font-size:11px;color:#94a3b8;margin:6px 0;text-align:center">— or upload individually —</div>
        <div class="upload-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
          <div class="upload-card" id="card_master_${isCompact?'compact':'full'}"><div class="upload-label">📁 Item Master <span class="req">*</span></div><input type="file" class="file-input" id="input_master_${isCompact?'compact':'full'}" accept=".xlsx"><div class="fname" id="fname_master_${isCompact?'compact':'full'}" style="font-size:11px;color:#3b82f6;margin-top:6px"></div></div>
          <div class="upload-card" id="card_schedule_${isCompact?'compact':'full'}"><div class="upload-label">📁 Schedule <span class="req">*</span></div><input type="file" class="file-input" id="input_schedule_${isCompact?'compact':'full'}" accept=".xlsx"><div class="fname" id="fname_schedule_${isCompact?'compact':'full'}" style="font-size:11px;color:#3b82f6;margin-top:6px"></div></div>
          <div class="upload-card" id="card_balance_${isCompact?'compact':'full'}"><div class="upload-label">📁 BOH Balance <span class="req">*</span></div><input type="file" class="file-input" id="input_balance_${isCompact?'compact':'full'}" accept=".xlsx"><div class="fname" id="fname_balance_${isCompact?'compact':'full'}" style="font-size:11px;color:#3b82f6;margin-top:6px"></div></div>
        </div>
        <div style="margin-top:12px;display:flex;gap:10px;align-items:center"><button class="btn" id="uploadBtn_${isCompact?'compact':'full'}" disabled>▶ Upload & Analyze</button><button class="btn btn-outline btn-sm" id="btnRetryLoad_${isCompact?'compact':'full'}">↻ Recheck</button><span id="uploadProgress_${isCompact?'compact':'full'}" style="font-size:12px"></span></div>
      </div>
    </div>`;
}
function attachUploadLogic(isCompact){
  const suffix = isCompact ? 'compact' : 'full';
  const files = { master: null, schedule: null, balance: null, combined: [] };
  function markHasFile(cardId, has){ document.getElementById(cardId)?.classList.toggle('has-file', !!has); }
  function classifyByName(name){
    const low = (name||'').toLowerCase();
    if (low.includes('master')) return 'master';
    if (low.includes('sched')) return 'schedule';
    if (low.includes('bal') || low.includes('boh')) return 'balance';
    return null;
  }
  function updateBtn(){
    const hasCombined = files.combined && files.combined.length>0;
    const ok = hasCombined || (files.master && files.schedule && files.balance);
    const btn=document.getElementById('uploadBtn_'+suffix);
    if(btn) btn.disabled=!ok;
    // update combined hint
    const comboEl = document.getElementById('fname_combined_'+suffix);
    if (comboEl && files.combined.length>0) {
      if (files.combined.length===1) {
        const f=files.combined[0];
        const isZip = f.name.toLowerCase().endsWith('.zip');
        const hint = isZip ? '📦 Zip' : '📄 Combined/ Single';
        comboEl.textContent = `✓ ${hint}: ${f.name} (${(f.size/1024).toFixed(1)}KB)`;
      } else {
        comboEl.textContent = `✓ ${files.combined.length} files: ` + files.combined.map(f=>f.name).join(', ');
      }
    }
  }
  function setFileForKey(k, file){
    files[k]=file;
    const fnameEl=document.getElementById('fname_'+k+'_'+suffix);
    if(fnameEl) fnameEl.textContent='✓ '+file.name;
    markHasFile('card_'+k+'_'+suffix,true);
  }
  ['master','schedule','balance'].forEach(k=>{
    const input=document.getElementById('input_'+k+'_'+suffix);
    if(!input) return;
    input.addEventListener('change', ()=>{
      if(input.files.length>0){ files[k]=input.files[0]; document.getElementById('fname_'+k+'_'+suffix).textContent='✓ '+input.files[0].name; markHasFile('card_'+k+'_'+suffix,true); }
      else{ files[k]=null; const el=document.getElementById('fname_'+k+'_'+suffix); if(el) el.textContent=''; markHasFile('card_'+k+'_'+suffix,false); }
      // Clear combined if individual changed
      if (files.combined.length>0) {
        files.combined=[];
        const ce=document.getElementById('fname_combined_'+suffix);
        if(ce) ce.textContent='';
        markHasFile('card_combined_'+suffix,false);
        const inp=document.getElementById('input_combined_'+suffix);
        if(inp) inp.value='';
      }
      updateBtn();
    });
  });
  // One-click handler
  const combinedInput=document.getElementById('input_combined_'+suffix);
  if(combinedInput){
    combinedInput.addEventListener('change', ()=>{
      const selected = Array.from(combinedInput.files||[]);
      if(selected.length===0){ files.combined=[]; markHasFile('card_combined_'+suffix,false); updateBtn(); return; }
      // If single file that is zip or likely combined (1 file)
      if(selected.length===1){
        const f=selected[0];
        const low=f.name.toLowerCase();
        const isZip = low.endsWith('.zip');
        const isCombinedName = low.includes('combined') || low.includes('io_template') || low.includes('template');
        // Treat as combined mode
        files.combined=[f];
        // Clear individual
        ['master','schedule','balance'].forEach(k=>{
          files[k]=null;
          const el=document.getElementById('fname_'+k+'_'+suffix);
          if(el) el.textContent='';
          markHasFile('card_'+k+'_'+suffix,false);
          const inp=document.getElementById('input_'+k+'_'+suffix);
          if(inp) inp.value='';
        });
        markHasFile('card_combined_'+suffix,true);
        updateBtn();
        return;
      }
      // Multiple files selected at once: auto-distribute
      files.combined=[];
      // Reset individual
      ['master','schedule','balance'].forEach(k=>{
        files[k]=null;
        const el=document.getElementById('fname_'+k+'_'+suffix);
        if(el) el.textContent='';
        markHasFile('card_'+k+'_'+suffix,false);
        const inp=document.getElementById('input_'+k+'_'+suffix);
        if(inp) inp.value='';
      });
      // Classify each
      const unclassified=[];
      selected.forEach(f=>{
        const cls=classifyByName(f.name);
        if(cls && !files[cls]){ setFileForKey(cls,f); }
        else if (!cls) { unclassified.push(f); }
        else { // already assigned, push to unclassified to try assign to empty slot
          unclassified.push(f);
        }
      });
      // Fill remaining empty slots with unclassified in order
      for(const k of ['master','schedule','balance']){
        if(!files[k] && unclassified.length>0){ setFileForKey(k, unclassified.shift()); }
      }
      // If still has leftover, treat as combined multi? Keep them as combined as fallback
      if(unclassified.length>0 && !files.master && !files.schedule && !files.balance){
        files.combined=selected;
      } else if (files.master && files.schedule && files.balance) {
        // Successfully distributed to 3 slots, clear combined display, keep 3 slots
        files.combined=[];
        const ce=document.getElementById('fname_combined_'+suffix);
        if(ce) ce.textContent=`✓ Auto-distributed ${selected.length} files → Master/Schedule/Balance`;
        markHasFile('card_combined_'+suffix,true);
      } else {
        // Partial - keep whatever we have, but also store as combined for fallback
        files.combined=selected;
        // Show partial status
        const ce=document.getElementById('fname_combined_'+suffix);
        if(ce) ce.textContent=`✓ ${selected.length} files selected, classified ${['master','schedule','balance'].filter(k=>!!files[k]).length}/3. Click Upload to try auto-detect.`;
      }
      // If we have 3 individual filled, enable
      updateBtn();
      // If we have partial but user selected 3 files, we will actually upload all 3 as combined via backend auto-classify
      if(selected.length>=3){
        files.combined=selected;
        markHasFile('card_combined_'+suffix,true);
        updateBtn();
      }
    });
  }
  document.getElementById('uploadBtn_'+suffix)?.addEventListener('click', async ()=>{
    const prog=document.getElementById('uploadProgress_'+suffix);
    const btn=document.getElementById('uploadBtn_'+suffix);
    btn.disabled=true; btn.textContent='Uploading...'; if(prog) prog.textContent='⏳ Processing...';
    const form=new FormData();
    if(files.combined && files.combined.length>0){
      // One-click mode: append all combined files, backend will auto-classify and handle zip/combined
      files.combined.forEach((f,i)=>{
        form.append('file_'+i, f);
        form.append('combined_'+i, f);
      });
      // Also append first file as generic 'file' for combined xlsx detection
      if(files.combined.length===1){
        form.append('combined', files.combined[0]);
        form.append('file', files.combined[0]);
      }
    } else {
      form.append('master',files.master); form.append('schedule',files.schedule); form.append('balance',files.balance);
    }
    try{
      const resp=await fetch('/api/io/upload',{method:'POST',body:form});
      const result=await resp.json();
      if(result.ok){
        const now = new Date();
        const info = { fg: result.fg||0, gb: result.gb||0, time: now.toISOString(), timeStr: now.toLocaleString() };
        saveIOLoadStatus(info);
        try{ _lastStatus = { loaded:true, ok:true, fg: result.fg, gb: result.gb }; }catch{}
        if(prog) prog.innerHTML=`<span style="color:#059669">✅ Loaded: ${result.fg||0} FG, ${result.gb||0} GB — Ready, entering reports...</span>`;
        // update persistent badges immediately
        const badgeCompact = document.getElementById('ioStatusBadge_compact');
        const badgeFull = document.getElementById('ioStatusBadge_full');
        const msgCompact = document.getElementById('ioPersistentMsg_compact');
        const msgFull = document.getElementById('ioPersistentMsg_full');
        const htmlBadge = getStatusBadgeHTML();
        if(badgeCompact) badgeCompact.innerHTML = htmlBadge;
        if(badgeFull) badgeFull.innerHTML = htmlBadge;
        if(msgCompact) msgCompact.textContent = `✅ Loaded ${info.fg} FG / ${info.gb} GB at ${info.timeStr} — Ready to use`;
        if(msgFull) msgFull.textContent = `✅ Loaded ${info.fg} FG / ${info.gb} GB at ${info.timeStr} — Ready to use`;
        setTimeout(()=>{ renderReportsPage(); }, 900);
      }
      else{ if(prog) prog.innerHTML=`<span style="color:#dc2626">❌ ${result.error||JSON.stringify(result)}</span>`; btn.disabled=false; btn.textContent='▶ Upload & Analyze'; }
    }catch(e){ if(prog) prog.innerHTML=`<span style="color:#dc2626">❌ ${e.message}</span>`; btn.disabled=false; btn.textContent='▶ Upload & Analyze'; }
  });
  document.getElementById('btnRetryLoad_'+suffix)?.addEventListener('click', async ()=>{ const ok=await checkStatus(); if(ok) renderReportsPage(); else alert('No valid data'); });
  if(isCompact) document.getElementById('toggleUploadBar')?.addEventListener('click', ()=>{ const c=document.getElementById('uploadBarContent'); if(!c) return; const hid=c.style.display==='none'; c.style.display=hid?'block':'none'; document.getElementById('toggleUploadBar').textContent=hid?'▼ Collapse':'▶ Expand'; });
}
function renderUploadPage(){ ioRoot.innerHTML=buildUploadSectionHTML(false); attachUploadLogic(false); }

function renderReportsPage(){
  const _badge = getStatusBadgeHTML();
  const _info = loadIOLoadStatus();
  const _persistText = _lastStatus && _lastStatus.loaded ? `✅ Ready: ${_lastStatus.fg||0} FG / ${_lastStatus.gb||0} GB — You can drag dimensions and view reports` : (_info ? `✅ Last loaded: ${_info.fg||0} FG / ${_info.gb||0} GB at ${_info.timeStr||''} — Ready` : '✅ Data loaded — Ready to use');
  ioRoot.innerHTML = buildUploadSectionHTML(true) + `
    <div class="section" id="io-main-section">
      <div class="section-header">
        <div style="display:flex;align-items:center;gap:12px">
          <span class="section-title">📈 I/O Report</span>
          <span id="ioMainStatusBadge">${_badge}</span>
          <span id="ioMainPersistent" style="font-size:11px;color:#059669;font-weight:500">${_persistText}</span>
        </div>
        <div class="section-actions"><button id="io-dl-all" class="btn btn-sm btn-outline">📥 Download All</button><button id="io-reset-groups" class="btn btn-sm btn-outline">↺ Reset</button></div>
      </div>
      <div class="dim-tabs" id="io-group-tabs"><button class="dim-tab active" data-group="FG">FG (SKU)</button><button class="dim-tab" data-group="GB">GB</button></div>
      <div class="toolbar" id="io-toolbar"><div class="panels-row">
        <div class="panel" style="flex:1;min-width:220px"><div class="panel-label">Row Dimensions (drag to order)</div><div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px"><span class="dim-chip available" draggable="true" data-dim="LINE_CODE">Line</span><span class="dim-chip available" draggable="true" data-dim="ITEM_NO">PN</span><span class="dim-chip available" draggable="true" data-dim="STYLE">Style</span><div id="ioDimWell" class="dim-well"><span class="placeholder">Drop dimensions here</span></div></div></div>
        <div class="panel" style="min-width:160px"><div class="panel-label">Column</div><div class="btn-group" id="ioColDimTabs" style="margin-top:6px"><button class="btn" data-coldim="shift">Shift</button><button class="btn active" data-coldim="day">Day</button><button class="btn" data-coldim="week">Week</button><button class="btn" data-coldim="month">Month</button></div></div>
        <div class="panel" style="flex:1;min-width:260px"><div class="panel-label">Filters</div><div class="filter-row" style="margin-top:6px"><div class="filter-group"><label>Line</label><div class="filter-input-wrap" id="fiw_lineCode"><input type="text" class="filter-input" id="fi_lineCode" placeholder="All"><span class="filter-arrow">▾</span><div class="filter-dropdown" id="fd_lineCode"></div></div></div><div class="filter-group"><label>PN</label><div class="filter-input-wrap" id="fiw_itemNo"><input type="text" class="filter-input" id="fi_itemNo" placeholder="All"><span class="filter-arrow">▾</span><div class="filter-dropdown" id="fd_itemNo"></div></div></div><div class="filter-group"><label>Style</label><div class="filter-input-wrap" id="fiw_style"><input type="text" class="filter-input" id="fi_style" placeholder="All"><span class="filter-arrow">▾</span><div class="filter-dropdown" id="fd_style"></div></div></div><div class="filter-group" style="justify-content:flex-end"><button id="ioRefreshBtn" class="btn btn-outline btn-sm" style="margin-top:14px">Refresh</button></div></div></div>
      </div></div>

      <div class="merge-info" style="margin-top:12px;padding:6px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;font-size:11px;color:#475569;display:flex;gap:12px;align-items:center"><span>Groups: <strong id="mergeGroupCount">9</strong></span><span style="color:#94a3b8">|</span><span style="color:#64748b">Drag report labels between boxes to merge; same dim adjacent</span><button id="addEmptyGroupBtn" class="btn btn-sm btn-outline" style="margin-left:auto">➕ Add Group</button></div>

      <div style="display:flex;gap:12px;margin-top:12px;align-items:flex-start">
        <div style="flex:0 0 220px;max-width:220px;position:sticky;top:70px">
          <div class="io-left-manager" style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px">
            <div style="font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;margin-bottom:8px;display:flex;justify-content:space-between"><span>📦 Group Boxes</span><span style="font-size:10px;color:#94a3b8">${REPORTS.length} types</span></div>
            <div id="leftGroupBoxes" style="display:flex;flex-direction:column;gap:8px"></div>
            <div id="newMergedDrop" class="group-box empty" style="margin-top:10px;border:2px dashed #8b5cf6;background:#faf5ff;padding:12px;text-align:center;font-size:11px;color:#6d28d9;border-radius:8px;cursor:copy">➕ Drop to create merged group</div>
          </div>
        </div>
        <div style="flex:1;min-width:0"><div id="ioReportContent"></div></div>
      </div>
    </div>
  `;
  attachUploadLogic(true);
  initReportsPage();
  initMergeDragDrop();
}

function initReportsPage(){
  document.querySelectorAll('#io-group-tabs .dim-tab').forEach(tab=>{
    tab.addEventListener('click', ()=>{
      document.querySelectorAll('#io-group-tabs .dim-tab').forEach(t=> t.classList.remove('active'));
      tab.classList.add('active');
      currentGroup = tab.dataset.group;
      refreshMeta().then(()=> loadAllReports());
    });
  });
  document.querySelectorAll('#ioColDimTabs .btn').forEach(b=>{
    b.addEventListener('click', ()=>{
      document.querySelectorAll('#ioColDimTabs .btn').forEach(x=> x.classList.remove('active'));
      b.classList.add('active');
      COL_DIM = b.dataset.coldim;
      refreshMeta().then(()=> loadAllReports());
    });
  });
  initSearchableSelect('lineCode'); initSearchableSelect('itemNo'); initSearchableSelect('style');
  // preserve dimOrder and other state from localStorage if available, don't wipe on re-render
  try{
    const savedDim = localStorage.getItem('io_dimOrder');
    if(savedDim){
      const parsed = JSON.parse(savedDim);
      if(Array.isArray(parsed) && parsed.length>0 && (!dimOrder || dimOrder.length===0)){
        dimOrder = parsed;
      }
    }
  }catch{}
  // keep existing allData if present; otherwise will be fetched
  if(!dimOrder) dimOrder = [];
  // don't reset allData to null here - keep previous data to preserve display across switches
  // allData = null; // removed to preserve
  renderDimWell(); initDimDragDrop();
  refreshMeta().then(()=> loadAllReports());
  // persistent status: refresh badge from API and show ready message
  (async()=>{
    try{
      const st = await getFullStatus();
      const badge = document.getElementById('ioMainStatusBadge');
      const persist = document.getElementById('ioMainPersistent');
      const upBadge = document.getElementById('ioStatusBadge_compact');
      const upMsg = document.getElementById('ioPersistentMsg_compact');
      if(badge) badge.innerHTML = getStatusBadgeHTML();
      if(upBadge) upBadge.innerHTML = getStatusBadgeHTML();
      if(persist && st && st.loaded){
        persist.textContent = `✅ Ready: ${st.fg||0} FG / ${st.gb||0} GB — Drag dimensions (Line/PN/Style) to start`;
      }
      if(upMsg && st && st.loaded){
        upMsg.textContent = `✅ Data ready: ${st.fg||0} FG / ${st.gb||0} GB — You can now use the reports below. This status persists.`;
      }
    }catch{}
  })();
  document.getElementById('ioRefreshBtn')?.addEventListener('click', loadAllReports);
  document.getElementById('io-dl-all')?.addEventListener('click', downloadAll);
  document.getElementById('io-reset-groups')?.addEventListener('click', ()=>{ reportGroups = REPORTS.map(r=>[r]); pendingNewGroup=[]; Object.keys(treeCache).forEach(k=>delete treeCache[k]); if(window._ioExpanded) window._ioExpanded={}; renderAllReports(); });
  document.getElementById('addEmptyGroupBtn')?.addEventListener('click', ()=>{ reportGroups.push([]); renderAllReports(); });
}

function initSearchableSelect(key){
  const input=document.getElementById('fi_'+key), dd=document.getElementById('fd_'+key), wrap=document.getElementById('fiw_'+key);
  if(!input||!dd||!wrap) return;
  const show=()=>{ dd.style.display='block'; filterDropdown(key, input.value); };
  const hide=()=>{ dd.style.display='none'; };
  input.addEventListener('focus', show); input.addEventListener('click', show);
  input.addEventListener('input', ()=>{ dd.style.display='block'; filterDropdown(key, input.value); });
  input.addEventListener('keydown', (e)=>{ if(e.key==='Escape') hide(); });
  dd.addEventListener('mousedown', (e)=>{
    const opt=e.target.closest('.fo'); if(!opt) return; e.preventDefault();
    const val=opt.dataset.value; input.value=val||''; filterVals[key]=val; hide(); loadAllReports();
  });
  document.addEventListener('click', (e)=>{ if(!wrap.contains(e.target)) hide(); });
}
function filterDropdown(key, text){
  const dd=document.getElementById('fd_'+key); if(!dd) return;
  dd.querySelectorAll('.fo').forEach(item=>{ item.style.display = item.dataset.value==='' ? '' : (item.textContent.toLowerCase().includes(text.toLowerCase()) ? '' : 'none'); });
}
function populateFilter(key, options){
  const dd=document.getElementById('fd_'+key); if(!dd) return;
  const cur=filterVals[key];
  let html='<div class="fo" data-value="">All</div>';
  (options||[]).forEach(o=>{ const safe=String(o).replace(/"/g,'&quot;'); html+=`<div class="fo${o===cur?' active':''}" data-value="${safe}">${esc(o)}</div>`; });
  dd.innerHTML=html;
}
function initDimDragDrop(){
  document.querySelectorAll('#io-report-section .dim-chip.available').forEach(chip=>{
    chip.addEventListener('dragstart', e=>{ e.dataTransfer.setData('text/plain', chip.dataset.dim); e.dataTransfer.setData('text/x-dim','1'); chip.classList.add('dragging'); });
    chip.addEventListener('dragend', e=> chip.classList.remove('dragging'));
  });
  const well=document.getElementById('ioDimWell');
  if(well){
    well.addEventListener('dragover', e=>{ e.preventDefault(); well.classList.add('drag-over'); });
    well.addEventListener('dragleave', ()=> well.classList.remove('drag-over'));
    well.addEventListener('drop', e=>{
      e.preventDefault(); well.classList.remove('drag-over');
      if(e.dataTransfer.getData('text/x-report')) return;
      const dim=e.dataTransfer.getData('text/plain'); if(!dim || !DIM_LABELS[dim]) return;
      if(dragFromDim){ const fromIdx=dimOrder.indexOf(dragFromDim); if(fromIdx>=0) dimOrder.splice(fromIdx,1); const target=e.target.closest('.dim-chip.in-well'); if(target){ const toDim=target.dataset.dim; const toIdx=dimOrder.indexOf(toDim); if(toIdx>=0) dimOrder.splice(toIdx,0,dim); else dimOrder.push(dim); }else dimOrder.push(dim); dragFromDim=null; renderDimWell(); }
      else if(!dimOrder.includes(dim)){ dimOrder.push(dim); renderDimWell(); }
    });
  }
}
function removeDim(dim){ dimOrder=dimOrder.filter(d=>d!==dim); renderDimWell(); }
window.ioRemoveDim=removeDim;
function renderDimWell(){
  const w=document.getElementById('ioDimWell'); if(!w) return;
  if(dimOrder.length===0) w.innerHTML='<span class="placeholder">Drop dimensions here</span>';
  else w.innerHTML=dimOrder.map((dim,i)=>`<span class="dim-chip in-well" draggable="true" data-dim="${dim}" ondragstart="window.ioOnWellChipDragStart(event,'${dim}')">${DIM_LABELS[dim]||dim} <small>${i+1}</small><span class="remove" onclick="window.ioRemoveDim('${dim}')">×</span></span>`).join('');
  setTimeout(()=> loadAllReports(), 0);
}
function onWellChipDragStart(e,dim){ e.dataTransfer.setData('text/plain',dim); e.dataTransfer.setData('text/x-dim','1'); dragFromDim=dim; }
window.ioOnWellChipDragStart=onWellChipDragStart;
function getDimParam(){ if(dimOrder.length===0) return ''; if(dimOrder.length===1) return dimOrder[0]; return 'detail'; }
async function refreshMeta(){
  // Client offline path
  if (_ioClientCache && window.IOReportEngine){
    try{
      const meta = window.IOReportEngine.getMeta(_ioClientCache, currentGroup, COL_DIM);
      const map={lineCode:'line_codes',itemNo:'items',style:'styles'};
      for(const [fk,mk] of Object.entries(map)){
        const cur=filterVals[fk]; const opts=meta[mk]||[]; populateFilter(fk, opts);
        if(cur && !opts.includes(cur)){ filterVals[fk]=''; const inp=document.getElementById('fi_'+fk); if(inp) inp.value=''; }
      }
      return;
    }catch(e){ console.error('client refreshMeta failed', e); }
  }
  try{
    const resp=await fetch(`/api/io/meta?group=${encodeURIComponent(currentGroup)}&col_dim=${COL_DIM}`);
    const meta=await resp.json(); if(meta.error) throw new Error(meta.error);
    const map={lineCode:'line_codes',itemNo:'items',style:'styles'};
    for(const [fk,mk] of Object.entries(map)){
      const cur=filterVals[fk]; const opts=meta[mk]||[]; populateFilter(fk, opts);
      if(cur && !opts.includes(cur)){ filterVals[fk]=''; const inp=document.getElementById('fi_'+fk); if(inp) inp.value=''; }
    }
  }catch(e){ console.error(e); }
}
async function loadAllReports(){
  const dim=getDimParam();
  const content=document.getElementById('ioReportContent');
  if(!dim){ allData=null; if(content) content.innerHTML='<div style="text-align:center;padding:40px;color:#94a3b8">Please drag row dimensions</div>'; renderLeftGroupBoxes(); return; }
  if(content) content.innerHTML='<div style="text-align:center;padding:24px;color:#64748b">⏳ Loading...</div>';
  // Client offline
  if (_ioClientCache && window.IOReportEngine){
    try{
      const result = window.IOReportEngine.buildReportsForGroup(_ioClientCache, dim, COL_DIM, currentGroup, filterVals.lineCode, filterVals.itemNo, filterVals.style);
      const data = result[0];
      allData=data;
      Object.keys(treeCache).forEach(k=>delete treeCache[k]);
      renderAllReports();
      return;
    }catch(e){
      console.error('client loadAllReports failed', e);
      if(content) content.innerHTML=`<div style="text-align:center;padding:24px;color:#dc2626">❌ ${esc(e.message)}</div>`;
      return;
    }
  }
  const params=new URLSearchParams({group:currentGroup, dim, col_dim:COL_DIM, line_code:filterVals.lineCode, item_no:filterVals.itemNo, style:filterVals.style});
  try{
    const resp=await fetch(`/api/io/reports?${params}`);
    const data=await resp.json(); if(data.error) throw new Error(data.error);
    allData=data; Object.keys(treeCache).forEach(k=>delete treeCache[k]); renderAllReports();
  }catch(e){ if(content) content.innerHTML=`<div style="text-align:center;padding:24px;color:#dc2626">❌ ${esc(e.message)}</div>`; }
}

// merge
function initMergeDragDrop(){
  const newMerged=document.getElementById('newMergedDrop');
  if(newMerged){
    newMerged.addEventListener('dragover', e=>{ if(draggedReport){ e.preventDefault(); newMerged.classList.add('drag-over'); }});
    newMerged.addEventListener('dragleave', ()=> newMerged.classList.remove('drag-over'));
    newMerged.addEventListener('drop', e=>{
      e.preventDefault(); newMerged.classList.remove('drag-over');
      if(!draggedReport) return;
      const {type, fromGroup}=draggedReport;
      const from=reportGroups[fromGroup];
      if(from){ const idx=from.indexOf(type); if(idx>=0) from.splice(idx,1); if(from.length===0) reportGroups.splice(fromGroup,1); }
      if(!pendingNewGroup.includes(type)) pendingNewGroup.push(type);
      draggedReport=null; renderAllReports();
    });
  }
}
function addEmptyGroup(){ reportGroups.push([]); renderAllReports(); }
window.ioAddEmptyGroup=addEmptyGroup;
function handleReportDragStart(e){
  const type=e.currentTarget.dataset.type;
  const fromGroup=e.currentTarget.dataset.group ? parseInt(e.currentTarget.dataset.group) : -1;
  if(e.currentTarget.dataset.pending) draggedReport={type,fromGroup:-2,fromPending:true};
  else draggedReport={type,fromGroup};
  e.dataTransfer.setData('text/plain',type); e.dataTransfer.setData('text/x-report','1'); e.dataTransfer.effectAllowed='move'; e.currentTarget.classList.add('dragging');
}
function handleReportDragEnd(e){
  e.currentTarget.classList.remove('dragging');
  document.querySelectorAll('.group-box').forEach(el=> el.classList.remove('drag-over'));
  document.getElementById('newMergedDrop')?.classList.remove('drag-over');
}
function handleGroupDragOver(e){ if(!draggedReport) return; e.preventDefault(); e.currentTarget.classList.add('drag-over'); }
function handleGroupDragLeave(e){ e.currentTarget.classList.remove('drag-over'); }
function handleGroupDrop(e, toGroupIdx){
  e.preventDefault(); e.currentTarget.classList.remove('drag-over');
  if(!draggedReport) return;
  const {type, fromGroup, fromPending}=draggedReport;
  if(!fromPending && fromGroup===toGroupIdx){ draggedReport=null; return; }
  if(fromPending){ const idx=pendingNewGroup.indexOf(type); if(idx>=0) pendingNewGroup.splice(idx,1); const to=reportGroups[toGroupIdx]; if(to && !to.includes(type)) to.push(type); }
  else{
    const from=reportGroups[fromGroup]; const to=reportGroups[toGroupIdx];
    if(!from||!to){ draggedReport=null; return; }
    const idx=from.indexOf(type); if(idx>=0) from.splice(idx,1);
    if(from.length===0){ const removedBefore=fromGroup<toGroupIdx?1:0; reportGroups.splice(fromGroup,1); const newToIdx=toGroupIdx-removedBefore; const target=reportGroups[newToIdx]; if(target&&!target.includes(type)) target.push(type); }
    else{ if(!to.includes(type)) to.push(type); }
  }
  draggedReport=null; renderAllReports();
}
window.ioHandleGroupDrop=handleGroupDrop;
window.ioHandleGroupDragOver=handleGroupDragOver;
window.ioHandleGroupDragLeave=handleGroupDragLeave;
window.ioHandleReportDragStart=handleReportDragStart;
window.ioHandleReportDragEnd=handleReportDragEnd;
function splitReportType(groupIdx, type){
  const g=reportGroups[groupIdx]; if(!g) return;
  const pos=g.indexOf(type); if(pos>=0) g.splice(pos,1);
  if(g.length===0) reportGroups.splice(groupIdx,1);
  reportGroups.push([type]); renderAllReports();
}
window.ioSplitType=splitReportType;
function removePendingType(type){ const idx=pendingNewGroup.indexOf(type); if(idx>=0) pendingNewGroup.splice(idx,1); renderAllReports(); }
window.ioRemovePendingType=removePendingType;
function confirmPendingGroup(){ if(pendingNewGroup.length>0){ reportGroups.push([...pendingNewGroup]); pendingNewGroup=[]; renderAllReports(); } }
window.ioConfirmPendingGroup=confirmPendingGroup;
function clearPendingGroup(){ pendingNewGroup.forEach(t=> reportGroups.push([t])); pendingNewGroup=[]; renderAllReports(); }
window.ioClearPendingGroup=clearPendingGroup;
function jumpToGroup(gIdx){ const el=document.getElementById(`io_group_${gIdx}`); el?.scrollIntoView({behavior:'smooth',block:'start'}); el?.classList.add('jump-highlight'); setTimeout(()=>el?.classList.remove('jump-highlight'),1500); }
window.ioJumpToGroup=jumpToGroup;

function mergeTypesData(types){
  let columns=[]; let colSet=new Set();
  types.forEach(t=>{ const d=allData[t]; if(!d||!d.columns) return; d.columns.forEach(c=>{ if(!colSet.has(c)){ colSet.add(c); columns.push(c); }}); });
  let rows=[]; types.forEach(t=>{ const d=allData[t]; if(!d||!d.rows) return; d.rows.forEach(r=>{ rows.push({...r,_REPORT_TYPE:REPORT_NAMES[t],_REPORT_KEY:t}); }); });
  return {columns,rows};
}

function renderLeftGroupBoxes(){
  const container=document.getElementById('leftGroupBoxes'); if(!container) return;
  let html='';
  if(pendingNewGroup.length>0){
    html+=`<div class="group-box merged pending" style="border-color:#8b5cf6;background:#faf5ff;border:2px dashed #8b5cf6;border-radius:8px;padding:8px"><div style="font-size:11px;font-weight:700;color:#6d28d9;margin-bottom:6px">🆕 NEW (${pendingNewGroup.length})</div><div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px">${pendingNewGroup.map(t=>`<span class="report-chip chip-${t}" draggable="true" data-type="${t}" data-pending="1" ondragstart="ioHandleReportDragStart(event)" ondragend="ioHandleReportDragEnd(event)"><span class="type-dot dot-${t}"></span>${esc(REPORT_NAMES[t])}<span class="remove" onclick="event.stopPropagation(); ioRemovePendingType('${t}')">×</span></span>`).join('')}</div><div style="display:flex;gap:4px"><button class="btn btn-sm" style="flex:1" onclick="ioConfirmPendingGroup()">✓ Confirm</button><button class="btn btn-sm btn-outline" style="flex:1" onclick="ioClearPendingGroup()">✕</button></div></div>`;
  }
  reportGroups.forEach((groupTypes,gIdx)=>{
    if(!groupTypes) groupTypes=[];
    const isEmpty=groupTypes.length===0; const isMerged=groupTypes.length>1;
    const border=isEmpty?'#cbd5e1':(isMerged?'#8b5cf6':'#3b82f6'); const bg=isEmpty?'#f8fafc':(isMerged?'#faf5ff':'#fff');
    if(isEmpty){
      html+=`<div class="group-box empty" id="left_group_${gIdx}" data-group-idx="${gIdx}" ondragover="ioHandleGroupDragOver(event)" ondragleave="ioHandleGroupDragLeave(event)" ondrop="ioHandleGroupDrop(event, ${gIdx})" style="border:2px dashed ${border};background:${bg};border-radius:8px;padding:12px;text-align:center;cursor:copy"><div style="font-size:11px;color:#94a3b8">📭 Empty Box ${gIdx+1}<br>Drop here</div><button class="btn btn-sm btn-outline" style="margin-top:6px" onclick="reportGroups.splice(${gIdx},1); renderAllReports();">✕ Remove</button></div>`;
    }else{
      const chips=groupTypes.map(t=>`<span class="report-chip chip-${t}" draggable="true" data-type="${t}" data-group="${gIdx}" ondragstart="ioHandleReportDragStart(event)" ondragend="ioHandleReportDragEnd(event)"><span class="type-dot dot-${t}"></span>${esc(REPORT_NAMES[t])}<span class="remove" onclick="event.stopPropagation(); ioSplitType(${gIdx},'${t}')">×</span></span>`).join('');
      html+=`<div class="group-box ${isMerged?'merged':''}" id="left_group_${gIdx}" data-group-idx="${gIdx}" ondragover="ioHandleGroupDragOver(event)" ondragleave="ioHandleGroupDragLeave(event)" ondrop="ioHandleGroupDrop(event, ${gIdx})" onclick="ioJumpToGroup(${gIdx})" style="border:1px solid ${border};background:${bg};border-radius:8px;padding:8px;cursor:pointer"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><span style="font-size:10px;font-weight:700;color:#475569">BOX ${gIdx+1} ${isMerged?`(${groupTypes.length} merged)`:''}</span><span style="font-size:10px;color:#94a3b8">${isMerged?'🔗':''}</span></div><div style="display:flex;flex-wrap:wrap;gap:4px">${chips}</div></div>`;
    }
  });
  container.innerHTML=html||'<div style="text-align:center;color:#94a3b8;font-size:11px;padding:20px">No groups</div>';
  const countEl=document.getElementById('mergeGroupCount'); if(countEl) countEl.textContent=String(reportGroups.filter(g=>g.length>0).length + (pendingNewGroup.length>0?1:0));
}

function renderAllReports(){
  const content=document.getElementById('ioReportContent');
  if(!content) return;
  renderLeftGroupBoxes();
  if(!allData){ content.innerHTML='<div style="text-align:center;padding:24px;color:#94a3b8">No data</div>'; return; }
  if(reportGroups.length===0) reportGroups=REPORTS.map(r=>[r]);
  let html='';
  reportGroups.forEach((groupTypes,gIdx)=>{
    if(!groupTypes||groupTypes.length===0) return;
    const isMerged=groupTypes.length>1;
    const titles=groupTypes.map(t=>REPORT_NAMES[t]).join(' + ');
    const isDetail=getDimParam()==='detail' && dimOrder.length>=2;
    let tableHTML=''; let totalRows=0,totalCols=0;
    if(isMerged){
      const merged=mergeTypesData(groupTypes); totalRows=merged.rows.length; totalCols=merged.columns.length;
      tableHTML=totalRows===0?'<div style="text-align:center;padding:20px;color:#94a3b8">No data</div>':(isDetail?buildMergedHierarchicalTable(merged,dimOrder,gIdx):buildMergedFlatTable(merged,dimOrder[0]||'ITEM_NO',gIdx));
    }else{
      const rtype=groupTypes[0]; const data=allData[rtype]; totalRows=data?data.rows.length:0; totalCols=data?data.columns.length:0;
      if(!data||!data.rows||!data.rows.length) tableHTML='<div style="text-align:center;padding:20px;color:#94a3b8">No data</div>';
      else{
        const enriched={columns:data.columns,rows:data.rows.map(r=>({...r,_REPORT_TYPE:REPORT_NAMES[rtype],_REPORT_KEY:rtype}))};
        tableHTML=isDetail?buildHierarchicalTable(enriched,dimOrder,rtype,gIdx):buildFlatTable(enriched,dimOrder[0]||'ITEM_NO',rtype,gIdx);
      }
    }
    const badges=groupTypes.map(t=>`<span class="type-badge type-${t}">${esc(REPORT_NAMES[t])}</span>`).join(' ');
    html+=`<div class="report-section merge-group ${isMerged?'merged':''}" id="io_group_${gIdx}" data-group-idx="${gIdx}"><div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid ${isMerged?'#8b5cf6':'#3b82f6'};padding-bottom:6px;margin-bottom:8px"><div><h6 style="margin:0;font-size:13px;font-weight:700">${esc(titles)}</h6><div style="font-size:11px;color:#64748b">${totalRows} rows × ${totalCols} cols ${isMerged?'<span style="color:#8b5cf6">(Merged, same dim adjacent)</span>':''} — ${badges}</div></div><div style="display:flex;gap:6px"><button class="btn btn-sm btn-outline" onclick="window.${isMerged?'ioDownloadMerged':'ioDownloadExcel'}(${isMerged?gIdx:`'${groupTypes[0]}'`})">📥 Excel</button></div></div>${tableHTML}</div>`;
  });
  content.innerHTML=html||'<div style="text-align:center;padding:40px;color:#94a3b8">No tables</div>';
}

// ---------- Tables with paging + lazy expand ----------
function buildFlatTable(data, dim, reportKey, gIdx){
  const {columns, rows} = data;
  const dimLabel=DIM_LABELS[dim]||dim;
  const frozenW=120, dividerLeft=frozenW;
  const totalRows=rows.length;
  const pageKey=`flat_${gIdx}_${reportKey}_${dim}`;
  const page = window._ioPages?.[pageKey] || 0;
  const start=page*PAGE_SIZE, end=Math.min(start+PAGE_SIZE, totalRows);
  const pageRows=rows.slice(start,end);

  let html=`<div class="stat-row"><strong>${totalRows}</strong> rows &nbsp; <strong>${columns.length}</strong> cols ${totalRows>PAGE_SIZE?`— showing ${start+1}-${end}`:''} ${totalRows>PAGE_SIZE?`<button class="btn btn-sm btn-outline" onclick="ioChangePage('${pageKey}', -1)">◀ Prev</button><button class="btn btn-sm btn-outline" onclick="ioChangePage('${pageKey}', 1)">Next ▶</button><span style="font-size:11px;color:#64748b">Page ${page+1}/${Math.ceil(totalRows/PAGE_SIZE)}</span>`:''}</div>`;
  html+='<div class="table-wrapper"><table><thead><tr>';
  html+=`<th class="frozen" style="left:0;min-width:${frozenW}px;z-index:16">${esc(dimLabel)}</th>`;
  html+=`<th class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{ const p=c.split('_'); html+=`<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`; });
  html+='</tr></thead><tbody>';
  let prevVal=null;
  pageRows.forEach((r)=>{
    const isNew=prevVal!==null&&prevVal!==r[dim]; prevVal=r[dim];
    const rk=r._REPORT_KEY||reportKey||'';
    html+=`<tr class="row-${rk} ${isNew?'row-new-group':''}"><td class="frozen" style="left:0;min-width:${frozenW}px;z-index:5;font-weight:500">${esc(String(r[dim]??''))}</td><td class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
    columns.forEach(c=>{ const v=r[c]; html+=`<td class="num ${v>0?'num-pos':v===0?'num-zero':''}">${v!=null?Number(v).toLocaleString():''}</td>`; });
    html+='</tr>';
  });
  html+='</tbody></table></div>';
  if(totalRows>PAGE_SIZE){
    html+=`<div style="text-align:center;margin-top:8px;display:flex;gap:8px;justify-content:center;align-items:center"><button class="btn btn-sm btn-outline" onclick="ioChangePage('${pageKey}', -1)">◀ Prev</button><span style="font-size:12px">${start+1}-${end} / ${totalRows}</span><button class="btn btn-sm btn-outline" onclick="ioChangePage('${pageKey}', 1)">Next ▶</button></div>`;
  }
  return html;
}

function buildMergedFlatTable(data, dim, gIdx){
  const {columns, rows}=data;
  const dimLabel=DIM_LABELS[dim]||dim;
  const typeW=130,frozenW=120,dividerLeft=frozenW+typeW;
  const totalRows=rows.length;
  const pageKey=`mflat_${gIdx}_${dim}`;
  const page=window._ioPages?.[pageKey]||0;
  const typeOrder={}; REPORTS.forEach((t,i)=> typeOrder[t]=i);
  const sorted=[...rows].sort((a,b)=>{ const av=a[dim]||'', bv=b[dim]||''; if(av<bv) return -1; if(av>bv) return 1; return (typeOrder[a._REPORT_KEY]??99)-(typeOrder[b._REPORT_KEY]??99); });
  const start=page*PAGE_SIZE, end=Math.min(start+PAGE_SIZE, totalRows);
  const pageRows=sorted.slice(start,end);

  let html=`<div class="stat-row"><strong>${totalRows}</strong> merged rows &nbsp; Types: <strong>${[...new Set(rows.map(r=>r._REPORT_TYPE))].join(', ')}</strong> — same ${esc(dimLabel)} adjacent ${totalRows>PAGE_SIZE?`— showing ${start+1}-${end}`:''} ${totalRows>PAGE_SIZE?`<button class="btn btn-sm btn-outline" onclick="ioChangePage('${pageKey}', -1)">◀</button><button class="btn btn-sm btn-outline" onclick="ioChangePage('${pageKey}', 1)">▶</button>`:''}</div>`;
  html+='<div class="table-wrapper"><table><thead><tr>';
  html+=`<th class="frozen" style="left:0;min-width:${frozenW}px;z-index:16">${esc(dimLabel)}</th>`;
  html+=`<th class="frozen" style="left:${frozenW}px;min-width:${typeW}px;z-index:16">Type</th>`;
  html+=`<th class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{ const p=c.split('_'); html+=`<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`; });
  html+='</tr></thead><tbody>';
  let prevVal=null;
  pageRows.forEach((r)=>{
    const isNew=prevVal!==null&&prevVal!==r[dim]; prevVal=r[dim];
    html+=`<tr class="row-${r._REPORT_KEY} ${isNew?'row-new-group':''}"><td class="frozen" style="left:0;min-width:${frozenW}px;z-index:5;font-weight:500">${esc(String(r[dim]??''))}</td><td class="frozen" style="left:${frozenW}px;min-width:${typeW}px;z-index:5"><span class="type-badge type-${r._REPORT_KEY}">${esc(r._REPORT_TYPE||'')}</span></td><td class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
    columns.forEach(c=>{ const v=r[c]; html+=`<td class="num">${v!=null?Number(v).toLocaleString():''}</td>`; });
    html+='</tr>';
  });
  html+='</tbody></table></div>';
  return html;
}

function ensureExpandedMap(){ if(!window._ioExpanded) window._ioExpanded={}; }
function getExpandedSet(tableId){ ensureExpandedMap(); if(!window._ioExpanded[tableId]) window._ioExpanded[tableId]=new Set(); return window._ioExpanded[tableId]; }

function buildHierarchicalTable(data, dimOrder, reportKey, gIdx){
  const {columns, rows}=data;
  const nDims=dimOrder.length;
  const frozenW=120;
  const divLeft=nDims*frozenW;
  const tableId=`hier_${gIdx}_${reportKey}_${dimOrder.join('_')}`;
  if(!treeCache[tableId]){
    function groupRows(items, depth){
      if(depth>=nDims) return items.map(r=> ({key:null, items:[], allRows:[r]}));
      const dim=dimOrder[depth];
      const groups={}; items.forEach(r=>{ const k=r[dim]||'(blank)'; if(!groups[k]) groups[k]=[]; groups[k].push(r); });
      return Object.keys(groups).sort().map(k=> ({key:k, items: groupRows(groups[k], depth+1), allRows: groups[k]}));
    }
    treeCache[tableId]=groupRows(rows,0);
  }
  const tree=treeCache[tableId];
  const expandedSet=getExpandedSet(tableId);
  function sumRows(arr){ const s={}; columns.forEach(c=>s[c]=0); arr.forEach(r=> columns.forEach(c=> s[c]+=(Number(r[c])||0))); return s; }
  function sumAll(node){
    const s={}; columns.forEach(c=>s[c]=0);
    function walk(ns){ ns.forEach(nn=>{ if(nn.items&&nn.items.length){ walk(nn.items); } else { nn.allRows.forEach(r=>{ columns.forEach(c=> s[c]+=(Number(r[c])||0)); }); } }); }
    walk([node]); return s;
  }
  let h=`<div class="stat-row"><strong>${rows.length}</strong> detail rows — click to expand, persistent state</div><div class="table-wrapper"><table><thead><tr>`;
  dimOrder.forEach((d,i)=>{ const left=i*frozenW; h+=`<th class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:16">${esc(DIM_LABELS[d]||d)} <span class="expand-btn" onclick="event.stopPropagation(); window.ioExpandAll('${tableId}')">⊞</span></th>`; });
  h+=`<th class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{ const p=c.split('_'); h+=`<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`; });
  h+=`</tr></thead><tbody>`;

  function renderNodes(nodes, depth, path){
    let out='';
    nodes.forEach((node, idx)=>{
      const curPath=[...path, idx];
      const pathStr=curPath.join(',');
      const pid=`${tableId}_${curPath.join('_')}`;
      const isExpanded=expandedSet.has(pathStr);
      if(depth===nDims-1){
        const agg=sumRows(node.allRows);
        const rk=node.allRows[0]?._REPORT_KEY||reportKey||'';
        out+=`<tr class="agg-row row-new-group row-${rk}">`;
        for(let d=0; d<nDims; d++){
          const left=d*frozenW;
          const val=d<depth ? '' : esc(node.key);
          const indent = d===depth && depth>0 ? `padding-left:${8+depth*12}px` : '';
          out+=`<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5;${indent}">${val}</td>`;
        }
        out+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ out+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
        out+=`</tr>`;
      }else{
        const agg=sumAll(node);
        const hasChildren=node.items && node.items.length>0;
        out+=`<tr class="hierarchy-row agg-row row-new-group row-${reportKey}" id="${pid}" data-table="${tableId}" data-path="${pathStr}" data-depth="${depth}" onclick="window.ioToggleHier('${tableId}','${pathStr}')">`;
        for(let d=0; d<nDims; d++){
          const left=d*frozenW;
          if(d===depth){
            out+=`<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5"><span class="toggle">${isExpanded?'▼':'▶'}</span> ${esc(node.key)}</td>`;
          }else if(d===depth+1){
            out+=`<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5;color:#64748b">${hasChildren? node.items.length+' items':''}</td>`;
          }else{
            out+=`<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5"></td>`;
          }
        }
        out+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5;background:#475569"></td>`;
        columns.forEach(c=>{ out+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
        out+=`</tr>`;
        if(isExpanded && hasChildren){
          out+=renderNodes(node.items, depth+1, curPath);
        }
      }
    });
    return out;
  }
  h+=renderNodes(tree,0,[]);
  h+=`</tbody></table></div><div style="text-align:center;margin-top:6px"><button class="btn btn-sm btn-outline" onclick="window.ioExpandAll('${tableId}')">⊞ Expand All</button><button class="btn btn-sm btn-outline" onclick="window.ioCollapseAll('${tableId}')">⊟ Collapse All</button></div>`;
  if(!window._ioTableMeta) window._ioTableMeta={};
  window._ioTableMeta[tableId]={columns, dimOrder, frozenW, divLeft, reportKey};
  return h;
}

function buildMergedHierarchicalTable(data, dimOrder, gIdx){
  const {columns, rows}=data;
  const effDims=[...dimOrder, '_REPORT_TYPE'];
  const nDims=effDims.length;
  const frozenW=120, typeW=130;
  const lefts=[]; let curL=0; effDims.forEach((_,i)=>{ lefts.push(curL); curL+=(i===nDims-1? typeW : frozenW); });
  const divLeft=curL;
  const tableId=`m_hier_${gIdx}_${dimOrder.join('_')}`;
  if(!treeCache[tableId]){
    function groupRows(items, depth){
      if(depth>=nDims) return items.map(r=> ({key:null, items:[], allRows:[r]}));
      const dim=effDims[depth];
      const groups={}; items.forEach(r=>{ const k=r[dim]||'(blank)'; if(!groups[k]) groups[k]=[]; groups[k].push(r); });
      const keys=Object.keys(groups);
      if(dim==='_REPORT_TYPE') keys.sort((a,b)=>{ const ia=REPORTS.findIndex(t=> REPORT_NAMES[t]===a); const ib=REPORTS.findIndex(t=> REPORT_NAMES[t]===b); return ia-ib; }); else keys.sort();
      return keys.map(k=> ({key:k, items: groupRows(groups[k], depth+1), allRows: groups[k], repKey: groups[k][0]?._REPORT_KEY||''}));
    }
    treeCache[tableId]=groupRows(rows,0);
  }
  const tree=treeCache[tableId];
  const expandedSet=getExpandedSet(tableId);
  function sumRows(arr){ const s={}; columns.forEach(c=>s[c]=0); arr.forEach(r=> columns.forEach(c=> s[c]+=(Number(r[c])||0))); return s; }
  function sumAll(node){
    const s={}; columns.forEach(c=>s[c]=0);
    function walk(ns){ ns.forEach(nn=>{ if(nn.items&&nn.items.length){ walk(nn.items); } else { nn.allRows.forEach(r=>{ columns.forEach(c=> s[c]+=(Number(r[c])||0)); }); } }); }
    walk([node]); return s;
  }
  let h=`<div class="stat-row"><strong>${rows.length}</strong> merged rows — dim first, same ${dimOrder.map(d=>DIM_LABELS[d]||d).join('/')} adjacent, aligned expand</div><div class="table-wrapper"><table><thead><tr>`;
  effDims.forEach((d,i)=>{ const left=lefts[i]; const w=i===nDims-1? typeW : frozenW; const label=d==='_REPORT_TYPE'?'Type':(DIM_LABELS[d]||d); h+=`<th class="frozen" style="left:${left}px;min-width:${w}px;z-index:16">${esc(label)}</th>`; });
  h+=`<th class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{ const p=c.split('_'); h+=`<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`; });
  h+=`</tr></thead><tbody>`;
  function collectTypesInNode(n){
    const set=new Set();
    function walk(ns){
      ns.forEach(nn=>{
        if(nn.items && nn.items.length>0){
          walk(nn.items);
        }else{
          (nn.allRows||[]).forEach(r=>{
            const k=r._REPORT_KEY || nn.repKey;
            if(k) set.add(k);
          });
          if(nn.repKey) set.add(nn.repKey);
        }
      });
    }
    walk([n]);
    // sort by REPORTS order for consistency
    return Array.from(set).sort((a,b)=> REPORTS.indexOf(a)-REPORTS.indexOf(b));
  }
  function sumForType(node, targetType){
    const s={}; columns.forEach(c=>s[c]=0);
    function walk(ns){
      ns.forEach(nn=>{
        if(nn.items && nn.items.length>0){
          walk(nn.items);
        }else{
          nn.allRows.forEach(r=>{
            const rk=r._REPORT_KEY || nn.repKey;
            if(rk===targetType){
              columns.forEach(c=> s[c]+=(Number(r[c])||0));
            }
          });
        }
      });
    }
    walk([node]);
    return s;
  }
  function filterNodeByType(node, targetType){
    // return a pruned copy of node containing only rows of targetType
    if(!node.items || node.items.length===0){
      // leaf or intermediate with allRows
      const filteredRows = (node.allRows||[]).filter(r=>{
        const rk=r._REPORT_KEY || node.repKey;
        return rk===targetType;
      });
      if(filteredRows.length===0) return null;
      return {...node, allRows: filteredRows, items: []};
    }
    const filteredItems=[];
    for(const child of node.items){
      const f=filterNodeByType(child, targetType);
      if(f) filteredItems.push(f);
    }
    if(filteredItems.length===0) return null;
    // collect allRows as flattened filtered
    const allFiltered=[];
    function collect(n){
      if(n.items && n.items.length>0){ n.items.forEach(collect); }
      else { allFiltered.push(...(n.allRows||[])); }
    }
    filteredItems.forEach(collect);
    return {...node, items: filteredItems, allRows: allFiltered};
  }
  function renderNodes(nodes, depth, path){
    let out='';
    nodes.forEach((node, idx)=>{
      const curPath=[...path, idx];
      const pathStr=curPath.join(',');
      const pid=`${tableId}_${curPath.join('_')}`;
      const isExpanded=expandedSet.has(pathStr);
      const rk=node.repKey||node.allRows[0]?._REPORT_KEY||'';
      if(depth===nDims-1){
        const agg=sumRows(node.allRows);
        out+=`<tr class="agg-row row-new-group row-${rk}">`;
        for(let d=0; d<nDims; d++){
          const left=lefts[d];
          const w=d===nDims-1? typeW : frozenW;
          const val=d<depth ? '' : esc(node.key);
          if(effDims[d]==='_REPORT_TYPE') out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span class="type-badge type-${rk}">${val}</span></td>`;
          else out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5">${val}</td>`;
        }
        out+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ out+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
        out+=`</tr>`;
      }else{
        const hasChildren=node.items && node.items.length>0;
        const typesInNode = collectTypesInNode(node);
        // If this node aggregates multiple types and we are before TYPE level, split into per-type rows (like plan_merge)
        const shouldSplitPerType = typesInNode.length>1 && depth < nDims-1 && effDims[nDims-1]==='_REPORT_TYPE';
        if(shouldSplitPerType){
          // render one row per type, each with its own color - Type only in Type column per user request
          typesInNode.forEach(t=>{
            const agg=sumForType(node, t);
            const hasData=Object.values(agg).some(v=>v!==0);
            if(!hasData) return;
            const typePid=`${pid}_${t}`;
            out+=`<tr class="hierarchy-row agg-row row-new-group row-${t}" id="${typePid}" data-table="${tableId}" data-path="${pathStr}" data-depth="${depth}" data-type="${t}" onclick="window.ioToggleHier('${tableId}','${pathStr}')">`;
            for(let d=0; d<nDims; d++){
              const left=lefts[d];
              const w=d===nDims-1? typeW : frozenW;
              if(d===depth){
                out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span class="toggle">${isExpanded?'▼':'▶'}</span> ${esc(node.key)}</td>`;
              }else if(d===depth+1){
                const filtered=filterNodeByType(node, t);
                // FIX: show immediate child groups count, not total leaf rows
                // For LINE+STYLE: should be 1 (STYLE groups), not 10 (PN leaf rows)
                const cnt=filtered ? filtered.items.length : 0;
                out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5;color:#64748b">${cnt} items</td>`;
              }else if(effDims[d]==='_REPORT_TYPE'){
                out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span class="type-badge type-${t}">${esc(REPORT_NAMES[t]||t)}</span></td>`;
              }else{
                out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"></td>`;
              }
            }
            out+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5;background:#475569"></td>`;
            columns.forEach(c=>{ out+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
            out+=`</tr>`;
          });
          // when expanded, render PN level with same SKU's daily+ cum together for comparison
          if(isExpanded && hasChildren){
            // For each PN under this LINE, show its types together (e.g., SKU1 daily + SKU1 cum adjacent)
            node.items.forEach((pnNode, pnIdx)=>{
              const pnTypes=collectTypesInNode(pnNode).sort((a,b)=> REPORTS.indexOf(a)-REPORTS.indexOf(b));
              pnTypes.forEach(t=>{
                const agg=sumForType(pnNode, t);
                const hasData=Object.values(agg).some(v=>v!==0);
                if(!hasData) return;
                out+=`<tr class="agg-row row-new-group row-${t}">`;
                for(let d=0; d<nDims; d++){
                  const left=lefts[d];
                  const w=d===nDims-1? typeW : frozenW;
                  if(d===0){
                    out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5;color:#94a3b8">${esc(node.key)}</td>`;
                  }else if(d===1){
                    out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span style="padding-left:12px">${esc(pnNode.key)}</span></td>`;
                  }else if(effDims[d]==='_REPORT_TYPE'){
                    out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span class="type-badge type-${t}">${esc(REPORT_NAMES[t]||t)}</span></td>`;
                  }else{
                    out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"></td>`;
                  }
                }
                out+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5;background:#475569"></td>`;
                columns.forEach(c=>{ out+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
                out+=`</tr>`;
              });
            });
          }
        }else{
          const agg=sumAll(node);
          const hasChildren=node.items && node.items.length>0;
          // Type only in Type column per user request
          out+=`<tr class="hierarchy-row agg-row row-new-group ${typesInNode.length===1? 'row-'+typesInNode[0]:''}" id="${pid}" data-table="${tableId}" data-path="${pathStr}" data-depth="${depth}" onclick="window.ioToggleHier('${tableId}','${pathStr}')">`;
          for(let d=0; d<nDims; d++){
            const left=lefts[d];
            const w=d===nDims-1? typeW : frozenW;
            if(d===depth){
              out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span class="toggle">${isExpanded?'▼':'▶'}</span> ${esc(node.key)}</td>`;
            }else if(d===depth+1){
              out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5;color:#64748b">${hasChildren? node.items.length+' items':''}</td>`;
            }else if(effDims[d]==='_REPORT_TYPE'){
              // show all types badges in Type column when collapsed
              const badges = typesInNode.map(t=>`<span class="type-badge type-${t}" style="margin-right:2px;font-size:10px">${esc(REPORT_NAMES[t]||t)}</span>`).join('');
              out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span style="display:flex;flex-wrap:wrap;gap:2px">${badges}</span></td>`;
            }else{
              out+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"></td>`;
            }
          }
          out+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5;background:#475569"></td>`;
          columns.forEach(c=>{ out+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
          out+=`</tr>`;
          if(isExpanded && hasChildren){
            out+=renderNodes(node.items, depth+1, curPath);
          }
        }
      }
    });
    return out;
  }
  h+=renderNodes(tree,0,[]);
  h+=`</tbody></table></div><div style="text-align:center;margin-top:6px"><button class="btn btn-sm btn-outline" onclick="window.ioExpandAll('${tableId}')">⊞ Expand All</button><button class="btn btn-sm btn-outline" onclick="window.ioCollapseAll('${tableId}')">⊟ Collapse All</button></div>`;
  if(!window._ioTableMeta) window._ioTableMeta={};
  window._ioTableMeta[tableId]={columns, dimOrder, effDims, lefts, divLeft, frozenW, typeW, isMerged:true};
  return h;
}

// fixed toggle - flat rendering with persistent expanded state, no nested tables
window.ioToggleHier = function(tableId, pathStr){
  try{
    const set = getExpandedSet(tableId);
    if(set.has(pathStr)) set.delete(pathStr);
    else set.add(pathStr);
    // re-render all reports to reflect new expanded state (preserves alignment)
    renderAllReports();
    // keep scroll position near toggled table
    const el=document.getElementById(`io_group_${tableId.split('_')[1]||0}`);
    // optional: scrollIntoView not needed to avoid jump
  }catch(e){ console.error('ioToggleHier error', e); }
};
window.ioToggleLazy = window.ioToggleHier; // backward compat
window.ioExpandAll = function(tableId){
  try{
    const tree=treeCache[tableId];
    if(!tree) return;
    const set=getExpandedSet(tableId);
    function collectPaths(nodes, prefix){
      nodes.forEach((n, idx)=>{
        const p = prefix ? `${prefix},${idx}` : `${idx}`;
        if(n.items && n.items.length>0){
          set.add(p);
          collectPaths(n.items, p);
        }
      });
    }
    collectPaths(tree, '');
    renderAllReports();
  }catch(e){ console.error('ioExpandAll error', e); }
};
window.ioCollapseAll = function(tableId){
  try{
    const set=getExpandedSet(tableId);
    set.clear();
    renderAllReports();
  }catch(e){ console.error('ioCollapseAll error', e); }
};

window._ioPages = window._ioPages || {};
window.ioChangePage = function(pageKey, delta){
  const cur=window._ioPages[pageKey]||0;
  const next=Math.max(0, cur+delta);
  window._ioPages[pageKey]=next;
  // re-render only that table? For simplicity, full re-render
  renderAllReports();
  // scroll to table
  const parts=pageKey.split('_');
  const gIdx=parts[1]; // approximate
  const el=document.getElementById(`io_group_${gIdx}`);
  el?.scrollIntoView({behavior:'smooth', block:'nearest'});
};

function downloadExcel(type){
  const data=allData?.[type]; if(!data||!data.rows.length) return;
  const dim=getDimParam(); const headers=dim==='detail'?dimOrder:[dimOrder[0]||'ITEM_NO'];
  const wsData=[ [...headers.map(h=>DIM_LABELS[h]||h), ...data.columns] ];
  data.rows.forEach(row=>{ const r=[]; if(dim==='detail'){ headers.forEach(h=> r.push(row[h]||'')); } else { r.push(row[dimOrder[0]]??''); } data.columns.forEach(c=> r.push(row[c]??0)); wsData.push(r); });
  if(window.XLSX){ const wb=XLSX.utils.book_new(); const ws=XLSX.utils.aoa_to_sheet(wsData); XLSX.utils.book_append_sheet(wb, ws, type.slice(0,31)); XLSX.writeFile(wb, `${REPORT_NAMES[type]||type}.xlsx`); }
}
window.ioDownloadExcel=downloadExcel;
function downloadMerged(gIdx){
  const groupTypes=reportGroups[gIdx]; if(!groupTypes||!groupTypes.length) return;
  const merged=mergeTypesData(groupTypes); if(!merged.rows.length) return;
  const dim=getDimParam(); const isDetail=dim==='detail'&&dimOrder.length>=2;
  const headers=isDetail?[...dimOrder.map(d=>DIM_LABELS[d]||d),'Type']:[DIM_LABELS[dim]||dim,'Type'];
  const wsData=[[...headers,...merged.columns]];
  const typeOrder={}; REPORTS.forEach((t,i)=> typeOrder[t]=i);
  const sorted=[...merged.rows].sort((a,b)=>{ if(isDetail){ for(const d of dimOrder){ const av=a[d]||'', bv=b[d]||''; if(av<bv) return -1; if(av>bv) return 1; } } else { const av=a[dim]||'', bv=b[dim]||''; if(av<bv) return -1; if(av>bv) return 1; } return (typeOrder[a._REPORT_KEY]??99)-(typeOrder[b._REPORT_KEY]??99); });
  sorted.forEach(row=>{ const r=[]; if(isDetail){ dimOrder.forEach(d=> r.push(row[d]||'')); } else { r.push(row[dim]??''); } r.push(row._REPORT_TYPE||''); merged.columns.forEach(c=> r.push(row[c]??0)); wsData.push(r); });
  if(window.XLSX){ const wb=XLSX.utils.book_new(); const ws=XLSX.utils.aoa_to_sheet(wsData); XLSX.utils.book_append_sheet(wb, ws, groupTypes.map(t=>REPORT_NAMES[t]).join('_').slice(0,31)); XLSX.writeFile(wb, `${groupTypes.map(t=>REPORT_NAMES[t]).join('_')}.xlsx`); }
}
window.ioDownloadMerged=downloadMerged;
function downloadAll(){
  if(!allData) return;
  if(!window.XLSX){ alert('XLSX not loaded'); return; }
  const wb=XLSX.utils.book_new(); const typeOrder={}; REPORTS.forEach((t,i)=> typeOrder[t]=i);
  reportGroups.forEach((groupTypes,gIdx)=>{
    const merged=mergeTypesData(groupTypes); if(!merged.rows.length) return;
    const dim=getDimParam(); const isDetail=dim==='detail'&&dimOrder.length>=2;
    const headers=isDetail?[...dimOrder.map(d=>DIM_LABELS[d]||d),'Type']:[DIM_LABELS[dim]||dim,'Type'];
    const wsData=[[...headers,...merged.columns]];
    const sorted=[...merged.rows].sort((a,b)=>{ if(isDetail){ for(const d of dimOrder){ const av=a[d]||'', bv=b[d]||''; if(av<bv) return -1; if(av>bv) return 1; } } else { const av=a[dim]||'', bv=b[dim]||''; if(av<bv) return -1; if(av>bv) return 1; } return (typeOrder[a._REPORT_KEY]??99)-(typeOrder[b._REPORT_KEY]??99); });
    sorted.forEach(row=>{ const r=[]; if(isDetail){ dimOrder.forEach(d=> r.push(row[d]||'')); } else { r.push(row[dim]??''); } r.push(row._REPORT_TYPE||''); merged.columns.forEach(c=> r.push(row[c]??0)); wsData.push(r); });
    const ws=XLSX.utils.aoa_to_sheet(wsData); XLSX.utils.book_append_sheet(wb, ws, groupTypes.map(t=>REPORT_NAMES[t]).join('+').slice(0,31)||`Group${gIdx+1}`);
  });
  XLSX.writeFile(wb, `IO_Report_${currentGroup}_${COL_DIM}.xlsx`);
}
window.ioDownloadAll=downloadAll;

function saveIOStateToStorage(){
  try{
    localStorage.setItem('io_dimOrder', JSON.stringify(dimOrder||[]));
    localStorage.setItem('io_filterVals', JSON.stringify(filterVals||{}));
    localStorage.setItem('io_currentGroup', currentGroup||'FG');
    localStorage.setItem('io_colDim', COL_DIM||'day');
    localStorage.setItem('io_reportGroups', JSON.stringify(reportGroups||[]));
    localStorage.setItem('io_pendingNewGroup', JSON.stringify(pendingNewGroup||[]));
    if(allData){
      localStorage.setItem('io_hasData', '1');
    }
  }catch{}
}
function loadIOStateFromStorage(){
  try{
    const d = localStorage.getItem('io_dimOrder');
    if(d) dimOrder = JSON.parse(d);
    const f = localStorage.getItem('io_filterVals');
    if(f) Object.assign(filterVals, JSON.parse(f));
    const g = localStorage.getItem('io_currentGroup');
    if(g) currentGroup = g;
    const c = localStorage.getItem('io_colDim');
    if(c) COL_DIM = c;
    const rg = localStorage.getItem('io_reportGroups');
    if(rg){
      const parsed = JSON.parse(rg);
      if(Array.isArray(parsed) && parsed.length>0) reportGroups = parsed;
    }
    const pg = localStorage.getItem('io_pendingNewGroup');
    if(pg) pendingNewGroup = JSON.parse(pg);
  }catch{}
}

document.addEventListener('DOMContentLoaded', ()=>{
  loadIOStateFromStorage();
  const active=document.querySelector('.nav-item.active');
  if(active&&active.dataset.module==='io-report'){ render(); }
});
document.addEventListener('module-change', (e)=>{
  if(e.detail.module==='io-report'){
    // if we already have rendered content and data, keep it - don't reset
    const existingContent = document.getElementById('ioReportContent');
    if(existingContent && existingContent.innerHTML && allData && Object.keys(allData).length>0){
      // just ensure status badge updated and return
      getFullStatus().then(()=>{
        const badge=document.getElementById('ioMainStatusBadge');
        if(badge) badge.innerHTML=getStatusBadgeHTML();
      });
      // re-attach drag-drop that may have been lost? keep simple
      return;
    }
    loadIOStateFromStorage();
    render();
  } else {
    // when switching away from io-report, save state
    saveIOStateToStorage();
  }
});
// also save state on relevant changes
try{
  const _origRenderDimWell = renderDimWell;
  renderDimWell = function(){ _origRenderDimWell(); saveIOStateToStorage(); };
}catch{}
try{
  const _origLoadAllReports = loadAllReports;
  loadAllReports = async function(){ const r = await _origLoadAllReports(); saveIOStateToStorage(); return r; };
}catch{}
try{
  const _origRenderAllReports = renderAllReports;
  renderAllReports = function(){ const r=_origRenderAllReports(); saveIOStateToStorage(); return r; };
}catch{}
})();
