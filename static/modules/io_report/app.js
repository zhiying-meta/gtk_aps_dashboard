/**
 * I/O Report - 9 Tables with Left Group Boxes Manager
 * UX: 左侧一列方框，每个方框一个标签起步，可拖动标签拼到另一个方框合并为一张表（多合一）
 * 支持多组合并共存，行维度优先，同一 Line/PN 的不同 Type 相邻
 */
(() => {
const DIM_LABELS = { ITEM_NO: 'PN', LINE_CODE: 'Line', STYLE: 'Style' };
const REPORTS = ['daily_input','daily_output','daily_checkin','daily_checkout','cum_input','cum_output','cum_checkin','cum_checkout','balance'];
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

function esc(s){ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }
function getRoot(){ return document.getElementById('io-report-section'); }
async function checkStatus(){
  try{ const r = await fetch('/api/io/status'); const j = await r.json(); return !!j.loaded; }catch{ return false; }
}
async function render(){
  ioRoot = getRoot();
  if(!ioRoot) return;
  const loaded = await checkStatus();
  if(loaded) renderReportsPage();
  else renderUploadPage();
}

function buildUploadSectionHTML(isCompact){
  const title = isCompact ? '📁 Upload I/O Data' : '📁 Upload I/O Data (3 files required)';
  return `
    <div class="section" id="${isCompact ? 'io-upload-bar' : 'io-upload-section'}">
      <div class="section-header">
        <span class="section-title">${title}</span>
        <div class="section-actions">
          <a href="/api/io/templates/template" class="btn btn-sm btn-outline">📄 Template</a>
          <a href="/api/io/templates/demo" class="btn btn-sm btn-outline">📦 Demo</a>
          <a href="/api/io/templates/schema" target="_blank" class="btn btn-sm btn-outline">📋 Schema</a>
          ${isCompact ? '<button class="btn btn-sm btn-outline" id="toggleUploadBar">▼ Collapse</button>' : ''}
        </div>
      </div>
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px;margin-bottom:10px;font-size:11px;color:#475569">
        Item Master + Schedule Result + BOH Balance. Place 3 files in <code>data/</code> or upload below.
      </div>
      <div id="${isCompact ? 'uploadBarContent' : 'uploadFullContent'}">
        <div class="upload-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
          <div class="upload-card" id="card_master_${isCompact?'compact':'full'}">
            <div class="upload-label">📁 Item Master <span class="req">*</span></div>
            <input type="file" class="file-input" id="input_master_${isCompact?'compact':'full'}" accept=".xlsx">
            <div class="fname" id="fname_master_${isCompact?'compact':'full'}" style="font-size:11px;color:#3b82f6;margin-top:6px"></div>
          </div>
          <div class="upload-card" id="card_schedule_${isCompact?'compact':'full'}">
            <div class="upload-label">📁 Schedule <span class="req">*</span></div>
            <input type="file" class="file-input" id="input_schedule_${isCompact?'compact':'full'}" accept=".xlsx">
            <div class="fname" id="fname_schedule_${isCompact?'compact':'full'}" style="font-size:11px;color:#3b82f6;margin-top:6px"></div>
          </div>
          <div class="upload-card" id="card_balance_${isCompact?'compact':'full'}">
            <div class="upload-label">📁 BOH Balance <span class="req">*</span></div>
            <input type="file" class="file-input" id="input_balance_${isCompact?'compact':'full'}" accept=".xlsx">
            <div class="fname" id="fname_balance_${isCompact?'compact':'full'}" style="font-size:11px;color:#3b82f6;margin-top:6px"></div>
          </div>
        </div>
        <div style="margin-top:12px;display:flex;gap:10px;align-items:center">
          <button class="btn" id="uploadBtn_${isCompact?'compact':'full'}" disabled>▶ Upload & Analyze</button>
          <button class="btn btn-outline btn-sm" id="btnRetryLoad_${isCompact?'compact':'full'}">↻ Recheck data/</button>
          <span id="uploadProgress_${isCompact?'compact':'full'}" style="font-size:12px"></span>
        </div>
      </div>
    </div>
  `;
}

function attachUploadLogic(isCompact){
  const suffix = isCompact ? 'compact' : 'full';
  const files = { master: null, schedule: null, balance: null };
  function markHasFile(cardId, has){
    const card = document.getElementById(cardId);
    if(card) card.classList.toggle('has-file', !!has);
  }
  function updateBtn(){
    const ok = files.master && files.schedule && files.balance;
    const btn = document.getElementById('uploadBtn_'+suffix);
    if(btn) btn.disabled = !ok;
  }
  ['master','schedule','balance'].forEach(k=>{
    const input = document.getElementById('input_'+k+'_'+suffix);
    if(!input) return;
    input.addEventListener('change', ()=>{
      if(input.files.length>0){
        files[k]=input.files[0];
        document.getElementById('fname_'+k+'_'+suffix).textContent = '✓ ' + input.files[0].name;
        markHasFile('card_'+k+'_'+suffix, true);
      }else{
        files[k]=null;
        markHasFile('card_'+k+'_'+suffix, false);
      }
      updateBtn();
    });
  });
  const uploadBtn = document.getElementById('uploadBtn_'+suffix);
  if(uploadBtn){
    uploadBtn.addEventListener('click', async ()=>{
      const prog = document.getElementById('uploadProgress_'+suffix);
      uploadBtn.disabled = true;
      uploadBtn.textContent = 'Uploading...';
      if(prog) prog.textContent='⏳ Processing...';
      const form = new FormData();
      form.append('master', files.master);
      form.append('schedule', files.schedule);
      form.append('balance', files.balance);
      try{
        const resp = await fetch('/api/io/upload', { method: 'POST', body: form });
        const result = await resp.json();
        if(result.ok){
          if(prog) prog.innerHTML = `<span style="color:#059669">✅ Loaded: ${result.fg||0} FG, ${result.gb||0} GB</span>`;
          setTimeout(()=> renderReportsPage(), 800);
        }else{
          if(prog) prog.innerHTML = `<span style="color:#dc2626">❌ ${JSON.stringify(result)}</span>`;
          uploadBtn.disabled = false;
          uploadBtn.textContent = '▶ Upload & Analyze';
        }
      }catch(e){
        if(prog) prog.innerHTML = `<span style="color:#dc2626">❌ ${e.message}</span>`;
        uploadBtn.disabled = false;
        uploadBtn.textContent = '▶ Upload & Analyze';
      }
    });
  }
  const retryBtn = document.getElementById('btnRetryLoad_'+suffix);
  if(retryBtn){
    retryBtn.addEventListener('click', async ()=>{
      const ok = await checkStatus();
      if(ok) renderReportsPage();
      else alert('No valid data in data/');
    });
  }
  if(isCompact){
    document.getElementById('toggleUploadBar')?.addEventListener('click', ()=>{
      const c = document.getElementById('uploadBarContent');
      if(!c) return;
      const hid = c.style.display==='none';
      c.style.display = hid ? 'block' : 'none';
      document.getElementById('toggleUploadBar').textContent = hid ? '▼ Collapse' : '▶ Expand';
    });
  }
}

function renderUploadPage(){
  ioRoot.innerHTML = buildUploadSectionHTML(false);
  attachUploadLogic(false);
}

// ---------- New Left Group Boxes UX ----------
function renderReportsPage(){
  ioRoot.innerHTML = buildUploadSectionHTML(true) + `
    <div class="section" id="io-main-section">
      <div class="section-header">
        <span class="section-title">📈 I/O Report</span>
        <div class="section-actions">
          <button id="io-dl-all" class="btn btn-sm btn-outline">📥 Download All</button>
          <button id="io-reset-groups" class="btn btn-sm btn-outline">↺ Reset</button>
        </div>
      </div>

      <div class="dim-tabs" id="io-group-tabs">
        <button class="dim-tab active" data-group="FG">FG (SKU)</button>
        <button class="dim-tab" data-group="GB">GB</button>
      </div>

      <div class="toolbar" id="io-toolbar">
        <div class="panels-row">
          <div class="panel" style="flex:1;min-width:220px">
            <div class="panel-label">Row Dimensions (drag to order)</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
              <span class="dim-chip available" draggable="true" data-dim="LINE_CODE">Line</span>
              <span class="dim-chip available" draggable="true" data-dim="ITEM_NO">PN</span>
              <span class="dim-chip available" draggable="true" data-dim="STYLE">Style</span>
              <div id="ioDimWell" class="dim-well"><span class="placeholder">Drop dimensions here</span></div>
            </div>
          </div>
          <div class="panel" style="min-width:160px">
            <div class="panel-label">Column</div>
            <div class="btn-group" id="ioColDimTabs" style="margin-top:6px">
              <button class="btn" data-coldim="shift">Shift</button>
              <button class="btn active" data-coldim="day">Day</button>
              <button class="btn" data-coldim="week">Week</button>
              <button class="btn" data-coldim="month">Month</button>
            </div>
          </div>
          <div class="panel" style="flex:1;min-width:260px">
            <div class="panel-label">Filters</div>
            <div class="filter-row" style="margin-top:6px">
              <div class="filter-group"><label>Line</label><div class="filter-input-wrap" id="fiw_lineCode"><input type="text" class="filter-input" id="fi_lineCode" placeholder="All"><span class="filter-arrow">▾</span><div class="filter-dropdown" id="fd_lineCode"></div></div></div>
              <div class="filter-group"><label>PN</label><div class="filter-input-wrap" id="fiw_itemNo"><input type="text" class="filter-input" id="fi_itemNo" placeholder="All"><span class="filter-arrow">▾</span><div class="filter-dropdown" id="fd_itemNo"></div></div></div>
              <div class="filter-group"><label>Style</label><div class="filter-input-wrap" id="fiw_style"><input type="text" class="filter-input" id="fi_style" placeholder="All"><span class="filter-arrow">▾</span><div class="filter-dropdown" id="fd_style"></div></div></div>
              <div class="filter-group" style="justify-content:flex-end"><button id="ioRefreshBtn" class="btn btn-outline btn-sm" style="margin-top:14px">Refresh</button></div>
            </div>
          </div>
        </div>
      </div>

      <div class="merge-info" style="margin-top:12px;padding:10px 12px;background:#f0f9ff;border:1px solid #bfdbfe;border-radius:8px;font-size:11px;color:#334155">
        <div style="font-weight:600;margin-bottom:4px">💡 合并方案：左侧一列方框，每框1个标签起步 → 拖动标签拼到另一框合并 → 右侧生成一张大表（同Line/PN相邻）</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <span>Groups: <strong id="mergeGroupCount">9</strong></span>
          <span style="color:#64748b">支持多组合并并存，例如 Group1=Daily+Cum Input，Group2=Daily+Cum Output</span>
          <button id="addEmptyGroupBtn" class="btn btn-sm btn-outline">➕ Add Group</button>
        </div>
      </div>

      <div style="display:flex;gap:12px;margin-top:12px;align-items:flex-start">
        <!-- LEFT: Group Boxes Manager -->
        <div style="flex:0 0 220px;max-width:220px;position:sticky;top:70px">
          <div class="io-left-manager" style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px">
            <div style="font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">
              <span>📦 Group Boxes</span>
              <span style="font-size:10px;color:#94a3b8">${REPORTS.length} types</span>
            </div>
            <div id="leftGroupBoxes" style="display:flex;flex-direction:column;gap:8px"></div>
            <div id="pendingBox" style="margin-top:10px;display:none"></div>
            <div id="newMergedDrop" class="group-box empty" style="margin-top:10px;border:2px dashed #8b5cf6;background:#faf5ff;padding:12px;text-align:center;font-size:11px;color:#6d28d9;border-radius:8px;cursor:copy">
              ➕ 拖入多个标签<br>创建新合并组<br><small style="color:#94a3b8">Drop multiple chips here</small>
            </div>
            <div style="margin-top:10px;font-size:10px;color:#94a3b8;line-height:1.4">
              • 拖动标签拼到另一框合并<br>
              • 点击方框跳转右侧<br>
              • 点击 × 拆分<br>
              • 合并表：行维度优先，同Line/PN相邻，Type列区分
            </div>
          </div>
        </div>
        <!-- RIGHT: Tables -->
        <div style="flex:1;min-width:0">
          <div id="ioReportContent"></div>
        </div>
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
  initSearchableSelect('lineCode');
  initSearchableSelect('itemNo');
  initSearchableSelect('style');
  dimOrder = [];
  allData = null;
  renderDimWell();
  initDimDragDrop();
  refreshMeta().then(()=> loadAllReports());
  document.getElementById('ioRefreshBtn')?.addEventListener('click', loadAllReports);
  document.getElementById('io-dl-all')?.addEventListener('click', downloadAll);
  document.getElementById('io-reset-groups')?.addEventListener('click', ()=>{ reportGroups = REPORTS.map(r=>[r]); pendingNewGroup=[]; renderAllReports(); });
  document.getElementById('addEmptyGroupBtn')?.addEventListener('click', ()=>{ reportGroups.push([]); renderAllReports(); });
}

// searchable selects
function initSearchableSelect(key){
  const input = document.getElementById('fi_' + key);
  const dd = document.getElementById('fd_' + key);
  const wrap = document.getElementById('fiw_' + key);
  if(!input||!dd||!wrap) return;
  const show = ()=>{ dd.style.display='block'; filterDropdown(key, input.value); };
  const hide = ()=>{ dd.style.display='none'; };
  input.addEventListener('focus', show);
  input.addEventListener('click', show);
  input.addEventListener('input', ()=>{ dd.style.display='block'; filterDropdown(key, input.value); });
  input.addEventListener('keydown', (e)=>{ if(e.key==='Escape') hide(); });
  dd.addEventListener('mousedown', (e)=>{
    const opt = e.target.closest('.fo');
    if(!opt) return;
    e.preventDefault();
    const val = opt.dataset.value;
    input.value = val || '';
    filterVals[key]=val;
    hide();
    loadAllReports();
  });
  document.addEventListener('click', (e)=>{ if(!wrap.contains(e.target)) hide(); });
}
function filterDropdown(key, text){
  const dd = document.getElementById('fd_' + key);
  if(!dd) return;
  dd.querySelectorAll('.fo').forEach(item=>{
    item.style.display = item.dataset.value==='' ? '' : (item.textContent.toLowerCase().includes(text.toLowerCase()) ? '' : 'none');
  });
}
function populateFilter(key, options){
  const dd = document.getElementById('fd_' + key);
  if(!dd) return;
  const cur = filterVals[key];
  let html = '<div class="fo" data-value="">All</div>';
  (options||[]).forEach(o=>{
    const safe = String(o).replace(/"/g,'&quot;');
    html += `<div class="fo${o===cur?' active':''}" data-value="${safe}">${esc(o)}</div>`;
  });
  dd.innerHTML = html;
}

// dim drag
function initDimDragDrop(){
  document.querySelectorAll('#io-report-section .dim-chip.available').forEach(chip=>{
    chip.addEventListener('dragstart', e=>{
      e.dataTransfer.setData('text/plain', chip.dataset.dim);
      e.dataTransfer.setData('text/x-dim', '1');
      chip.classList.add('dragging');
    });
    chip.addEventListener('dragend', e=> chip.classList.remove('dragging'));
  });
  const well = document.getElementById('ioDimWell');
  if(well){
    well.addEventListener('dragover', e=>{ if(e.dataTransfer.types.includes('text/x-dim')||true){ e.preventDefault(); well.classList.add('drag-over'); }});
    well.addEventListener('dragleave', ()=> well.classList.remove('drag-over'));
    well.addEventListener('drop', e=>{
      e.preventDefault(); well.classList.remove('drag-over');
      if(e.dataTransfer.getData('text/x-report')) return;
      const dim = e.dataTransfer.getData('text/plain');
      if(!dim || !DIM_LABELS[dim]) return;
      if(dragFromDim){
        const fromIdx = dimOrder.indexOf(dragFromDim);
        if(fromIdx>=0) dimOrder.splice(fromIdx,1);
        const target = e.target.closest('.dim-chip.in-well');
        if(target){
          const toDim = target.dataset.dim;
          const toIdx = dimOrder.indexOf(toDim);
          if(toIdx>=0) dimOrder.splice(toIdx,0,dim); else dimOrder.push(dim);
        }else dimOrder.push(dim);
        dragFromDim=null;
        renderDimWell();
      }else if(!dimOrder.includes(dim)){
        dimOrder.push(dim);
        renderDimWell();
      }
    });
  }
}
function removeDim(dim){ dimOrder = dimOrder.filter(d=> d!==dim); renderDimWell(); }
window.ioRemoveDim = removeDim;
function renderDimWell(){
  const w=document.getElementById('ioDimWell'); if(!w) return;
  if(dimOrder.length===0){
    w.innerHTML = '<span class="placeholder">Drop dimensions here</span>';
  }else{
    w.innerHTML = dimOrder.map((dim,i)=>`<span class="dim-chip in-well" draggable="true" data-dim="${dim}" ondragstart="window.ioOnWellChipDragStart(event,'${dim}')">${DIM_LABELS[dim]||dim} <small>${i+1}</small><span class="remove" onclick="window.ioRemoveDim('${dim}')">×</span></span>`).join('');
  }
  setTimeout(()=> loadAllReports(), 0);
}
function onWellChipDragStart(e,dim){ e.dataTransfer.setData('text/plain', dim); e.dataTransfer.setData('text/x-dim','1'); dragFromDim = dim; }
window.ioOnWellChipDragStart = onWellChipDragStart;
function getDimParam(){
  if(dimOrder.length===0) return '';
  if(dimOrder.length===1) return dimOrder[0];
  return 'detail';
}
async function refreshMeta(){
  try{
    const groupParam = currentGroup === 'FG' ? '成品' : 'GB';
    const resp = await fetch(`/api/io/meta?group=${encodeURIComponent(groupParam)}&col_dim=${COL_DIM}`);
    const meta = await resp.json();
    if(meta.error) throw new Error(meta.error);
    const map = { lineCode: 'line_codes', itemNo: 'items', style: 'styles' };
    for(const [fk,mk] of Object.entries(map)){
      const cur = filterVals[fk];
      const opts = meta[mk] || [];
      populateFilter(fk, opts);
      if(cur && !opts.includes(cur)){
        filterVals[fk]=''; const inp = document.getElementById('fi_'+fk); if(inp) inp.value='';
      }
    }
  }catch(e){ console.error(e); }
}
async function loadAllReports(){
  const dim = getDimParam();
  const content = document.getElementById('ioReportContent');
  if(!dim){
    allData=null;
    if(content) content.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">Please drag row dimensions into the box above</div>';
    renderLeftGroupBoxes();
    return;
  }
  if(content) content.innerHTML = '<div style="text-align:center;padding:24px;color:#64748b">⏳ Loading...</div>';
  const groupParam = currentGroup === 'FG' ? '成品' : 'GB';
  const params = new URLSearchParams({group:groupParam, dim, col_dim:COL_DIM, line_code:filterVals.lineCode, item_no:filterVals.itemNo, style:filterVals.style});
  try{
    const resp = await fetch(`/api/io/reports?${params}`);
    const data = await resp.json();
    if(data.error) throw new Error(data.error);
    allData = data;
    renderAllReports();
  }catch(e){
    if(content) content.innerHTML = `<div style="text-align:center;padding:24px;color:#dc2626">❌ ${esc(e.message)}</div>`;
  }
}

// ---------- Left Group Boxes Manager ----------
function renderLeftGroupBoxes(){
  const container = document.getElementById('leftGroupBoxes');
  if(!container) return;
  let html = '';
  // pending new merged group on left top
  if(pendingNewGroup.length>0){
    html += `<div class="group-box merged pending" style="border-color:#8b5cf6;background:#faf5ff">
      <div style="font-size:11px;font-weight:700;color:#6d28d9;margin-bottom:6px">🆕 NEW (${pendingNewGroup.length}) — Confirm to create</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px">
        ${pendingNewGroup.map(t=> `<span class="report-chip chip-${t}" draggable="true" data-type="${t}" data-pending="1" ondragstart="ioHandleReportDragStart(event)" ondragend="ioHandleReportDragEnd(event)"><span class="type-dot dot-${t}"></span>${esc(REPORT_NAMES[t])}<span class="remove" onclick="event.stopPropagation(); ioRemovePendingType('${t}')">×</span></span>`).join('')}
      </div>
      <div style="display:flex;gap:4px"><button class="btn btn-sm" style="flex:1" onclick="ioConfirmPendingGroup()">✓ Confirm</button><button class="btn btn-sm btn-outline" style="flex:1" onclick="ioClearPendingGroup()">✕ Cancel</button></div>
    </div>`;
  }
  reportGroups.forEach((groupTypes, gIdx)=>{
    if(!groupTypes) groupTypes=[];
    const isEmpty = groupTypes.length===0;
    const isMerged = groupTypes.length>1;
    const border = isEmpty ? '#cbd5e1' : (isMerged ? '#8b5cf6' : '#3b82f6');
    const bg = isEmpty ? '#f8fafc' : (isMerged ? '#faf5ff' : '#fff');
    if(isEmpty){
      html += `<div class="group-box empty" id="left_group_${gIdx}" data-group-idx="${gIdx}" ondragover="ioHandleGroupDragOver(event)" ondragleave="ioHandleGroupDragLeave(event)" ondrop="ioHandleGroupDrop(event, ${gIdx})" style="border:2px dashed ${border};background:${bg};border-radius:8px;padding:12px;text-align:center;cursor:copy">
        <div style="font-size:11px;color:#94a3b8">📭 Empty Box ${gIdx+1}<br>Drop chips here</div>
        <button class="btn btn-sm btn-outline" style="margin-top:6px" onclick="reportGroups.splice(${gIdx},1); renderAllReports();">✕ Remove</button>
      </div>`;
    }else{
      const chips = groupTypes.map(t=> `<span class="report-chip chip-${t}" draggable="true" data-type="${t}" data-group="${gIdx}" ondragstart="ioHandleReportDragStart(event)" ondragend="ioHandleReportDragEnd(event)"><span class="type-dot dot-${t}"></span>${esc(REPORT_NAMES[t])}<span class="remove" onclick="event.stopPropagation(); ioSplitType(${gIdx},'${t}')">×</span></span>`).join('');
      html += `<div class="group-box ${isMerged?'merged':''}" id="left_group_${gIdx}" data-group-idx="${gIdx}" ondragover="ioHandleGroupDragOver(event)" ondragleave="ioHandleGroupDragLeave(event)" ondrop="ioHandleGroupDrop(event, ${gIdx})" onclick="ioJumpToGroup(${gIdx})" style="border:1px solid ${border};background:${bg};border-radius:8px;padding:8px;cursor:pointer;transition:all .15s">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <span style="font-size:10px;font-weight:700;color:#475569">BOX ${gIdx+1} ${isMerged?`(${groupTypes.length} merged)`:`(1)`}</span>
          <span style="font-size:10px;color:#94a3b8">${isMerged?'🔗 Merged':''}</span>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:4px">${chips}</div>
        ${isMerged?`<div style="margin-top:6px;font-size:10px;color:#6d28d9">Type列区分，同维度相邻</div>`:''}
      </div>`;
    }
  });
  container.innerHTML = html || '<div style="text-align:center;color:#94a3b8;font-size:11px;padding:20px">No groups — click Reset</div>';
  const countEl = document.getElementById('mergeGroupCount');
  if(countEl) countEl.textContent = String(reportGroups.filter(g=>g.length>0).length + (pendingNewGroup.length>0?1:0));
}

function initMergeDragDrop(){
  const newMerged = document.getElementById('newMergedDrop');
  if(newMerged){
    newMerged.addEventListener('dragover', e=>{ if(draggedReport){ e.preventDefault(); newMerged.classList.add('drag-over'); }});
    newMerged.addEventListener('dragleave', ()=> newMerged.classList.remove('drag-over'));
    newMerged.addEventListener('drop', e=>{
      e.preventDefault(); newMerged.classList.remove('drag-over');
      if(!draggedReport) return;
      const {type, fromGroup} = draggedReport;
      const from = reportGroups[fromGroup];
      if(from){
        const idx = from.indexOf(type);
        if(idx>=0) from.splice(idx,1);
        if(from.length===0) reportGroups.splice(fromGroup,1);
      }
      if(!pendingNewGroup.includes(type)) pendingNewGroup.push(type);
      draggedReport=null;
      renderAllReports();
    });
  }
}

function addEmptyGroup(){ reportGroups.push([]); renderAllReports(); }
window.ioAddEmptyGroup = addEmptyGroup;

function handleReportDragStart(e){
  const type = e.currentTarget.dataset.type;
  const fromGroup = e.currentTarget.dataset.group ? parseInt(e.currentTarget.dataset.group) : -1;
  if(e.currentTarget.dataset.pending){
    draggedReport = {type, fromGroup: -2, fromPending: true};
  }else{
    draggedReport = {type, fromGroup};
  }
  e.dataTransfer.setData('text/plain', type);
  e.dataTransfer.setData('text/x-report', '1');
  e.dataTransfer.effectAllowed='move';
  e.currentTarget.classList.add('dragging');
}
function handleReportDragEnd(e){
  e.currentTarget.classList.remove('dragging');
  document.querySelectorAll('.group-box').forEach(el=> el.classList.remove('drag-over'));
  document.querySelectorAll('.report-section').forEach(el=> el.classList.remove('drag-over'));
  document.getElementById('newMergedDrop')?.classList.remove('drag-over');
}
function handleGroupDragOver(e){
  if(!draggedReport) return;
  e.preventDefault();
  e.currentTarget.classList.add('drag-over');
}
function handleGroupDragLeave(e){ e.currentTarget.classList.remove('drag-over'); }
function handleGroupDrop(e, toGroupIdx){
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  if(!draggedReport) return;
  const {type, fromGroup, fromPending} = draggedReport;
  if(!fromPending && fromGroup===toGroupIdx) { draggedReport=null; return; }
  if(fromPending){
    const idx = pendingNewGroup.indexOf(type);
    if(idx>=0) pendingNewGroup.splice(idx,1);
    const to = reportGroups[toGroupIdx];
    if(to && !to.includes(type)) to.push(type);
  }else{
    const from = reportGroups[fromGroup];
    const to = reportGroups[toGroupIdx];
    if(!from || !to){ draggedReport=null; return; }
    const idx = from.indexOf(type);
    if(idx>=0) from.splice(idx,1);
    if(from.length===0){
      const removedBefore = fromGroup < toGroupIdx ? 1 : 0;
      reportGroups.splice(fromGroup,1);
      const newToIdx = toGroupIdx - removedBefore;
      const target = reportGroups[newToIdx];
      if(target && !target.includes(type)) target.push(type);
    }else{
      if(!to.includes(type)) to.push(type);
    }
  }
  draggedReport=null;
  renderAllReports();
}
window.ioHandleGroupDrop = handleGroupDrop;
window.ioHandleGroupDragOver = handleGroupDragOver;
window.ioHandleGroupDragLeave = handleGroupDragLeave;
window.ioHandleReportDragStart = handleReportDragStart;
window.ioHandleReportDragEnd = handleReportDragEnd;

function splitReportType(groupIdx, type){
  const g = reportGroups[groupIdx];
  if(!g) return;
  const pos = g.indexOf(type);
  if(pos>=0) g.splice(pos,1);
  if(g.length===0) reportGroups.splice(groupIdx,1);
  reportGroups.push([type]);
  renderAllReports();
}
window.ioSplitType = splitReportType;

function removePendingType(type){
  const idx = pendingNewGroup.indexOf(type);
  if(idx>=0) pendingNewGroup.splice(idx,1);
  renderAllReports();
}
window.ioRemovePendingType = removePendingType;
function confirmPendingGroup(){
  if(pendingNewGroup.length>0){
    reportGroups.push([...pendingNewGroup]);
    pendingNewGroup=[];
    renderAllReports();
  }
}
window.ioConfirmPendingGroup = confirmPendingGroup;
function clearPendingGroup(){
  pendingNewGroup.forEach(t=> reportGroups.push([t]));
  pendingNewGroup=[];
  renderAllReports();
}
window.ioClearPendingGroup = clearPendingGroup;

function jumpToGroup(gIdx){
  const el = document.getElementById(`io_group_${gIdx}`);
  el?.scrollIntoView({behavior:'smooth', block:'start'});
  el?.classList.add('jump-highlight');
  setTimeout(()=> el?.classList.remove('jump-highlight'), 1500);
}
window.ioJumpToGroup = jumpToGroup;

// merge helpers
function mergeTypesData(types){
  let columns = [];
  let colSet = new Set();
  types.forEach(t=>{
    const d = allData[t];
    if(!d || !d.columns) return;
    d.columns.forEach(c=>{ if(!colSet.has(c)){ colSet.add(c); columns.push(c); }});
  });
  let rows = [];
  types.forEach(t=>{
    const d = allData[t];
    if(!d || !d.rows) return;
    d.rows.forEach(r=>{ rows.push({ ...r, _REPORT_TYPE: REPORT_NAMES[t], _REPORT_KEY: t }); });
  });
  return { columns, rows };
}

function renderAllReports(){
  const content = document.getElementById('ioReportContent');
  if(!content) return;
  renderLeftGroupBoxes();
  if(!allData){ content.innerHTML = '<div style="text-align:center;padding:24px;color:#94a3b8">No data</div>'; return; }
  if(reportGroups.length===0) reportGroups = REPORTS.map(r=>[r]);

  let html = '';
  reportGroups.forEach((groupTypes, gIdx)=>{
    if(!groupTypes || groupTypes.length===0) return; // empty boxes only in left, no table on right
    const isMerged = groupTypes.length > 1;
    const titles = groupTypes.map(t=> REPORT_NAMES[t]).join(' + ');
    const isDetail = getDimParam()==='detail' && dimOrder.length>=2;
    let tableHTML = '';
    let totalRows = 0, totalCols = 0;

    if(isMerged){
      const merged = mergeTypesData(groupTypes);
      totalRows = merged.rows.length;
      totalCols = merged.columns.length;
      tableHTML = totalRows===0 ? '<div style="text-align:center;padding:20px;color:#94a3b8">No data</div>' : (isDetail ? buildMergedHierarchicalTable(merged, dimOrder) : buildMergedFlatTable(merged, dimOrder[0] || 'ITEM_NO'));
    }else{
      const rtype = groupTypes[0];
      const data = allData[rtype];
      totalRows = data ? data.rows.length : 0;
      totalCols = data ? data.columns.length : 0;
      if(!data || !data.rows || data.rows.length===0){
        tableHTML = '<div style="text-align:center;padding:20px;color:#94a3b8">No data</div>';
      }else{
        const enriched = { columns: data.columns, rows: data.rows.map(r=> ({...r, _REPORT_TYPE: REPORT_NAMES[rtype], _REPORT_KEY: rtype})) };
        tableHTML = isDetail ? buildHierarchicalTable(enriched, dimOrder, rtype) : buildFlatTable(enriched, dimOrder[0]||'ITEM_NO', rtype);
      }
    }

    const badges = groupTypes.map(t=> `<span class="type-badge type-${t}">${esc(REPORT_NAMES[t])}</span>`).join(' ');

    html += `<div class="report-section merge-group ${isMerged?'merged':''}" id="io_group_${gIdx}" data-group-idx="${gIdx}">
      <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid ${isMerged?'#8b5cf6':'#3b82f6'};padding-bottom:6px;margin-bottom:8px">
        <div><h6 style="margin:0;font-size:13px;font-weight:700">${esc(titles)}</h6><div style="font-size:11px;color:#64748b">${totalRows} rows × ${totalCols} cols ${isMerged?'<span style="color:#8b5cf6">(Merged, 同维度相邻)</span>':''} — ${badges}</div></div>
        <div style="display:flex;gap:6px"><button class="btn btn-sm btn-outline" onclick="window.${isMerged?'ioDownloadMerged':'ioDownloadExcel'}(${isMerged?gIdx:`'${groupTypes[0]}'`})">📥 Excel</button></div>
      </div>
      ${tableHTML}
    </div>`;
  });
  content.innerHTML = html || '<div style="text-align:center;padding:40px;color:#94a3b8">No tables — add groups on left</div>';
}

function renderLeftGroupBoxes(){
  const container = document.getElementById('leftGroupBoxes');
  if(!container) return;
  let html = '';
  if(pendingNewGroup.length>0){
    html += `<div class="group-box merged pending" style="border-color:#8b5cf6;background:#faf5ff;border:2px dashed #8b5cf6;border-radius:8px;padding:8px">
      <div style="font-size:11px;font-weight:700;color:#6d28d9;margin-bottom:6px">🆕 NEW (${pendingNewGroup.length})</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px">
        ${pendingNewGroup.map(t=> `<span class="report-chip chip-${t}" draggable="true" data-type="${t}" data-pending="1" ondragstart="ioHandleReportDragStart(event)" ondragend="ioHandleReportDragEnd(event)"><span class="type-dot dot-${t}"></span>${esc(REPORT_NAMES[t])}<span class="remove" onclick="event.stopPropagation(); ioRemovePendingType('${t}')">×</span></span>`).join('')}
      </div>
      <div style="display:flex;gap:4px"><button class="btn btn-sm" style="flex:1" onclick="ioConfirmPendingGroup()">✓ Confirm</button><button class="btn btn-sm btn-outline" style="flex:1" onclick="ioClearPendingGroup()">✕</button></div>
    </div>`;
  }
  reportGroups.forEach((groupTypes, gIdx)=>{
    if(!groupTypes) groupTypes=[];
    const isEmpty = groupTypes.length===0;
    const isMerged = groupTypes.length>1;
    const border = isEmpty ? '#cbd5e1' : (isMerged ? '#8b5cf6' : '#3b82f6');
    const bg = isEmpty ? '#f8fafc' : (isMerged ? '#faf5ff' : '#fff');
    if(isEmpty){
      html += `<div class="group-box empty" id="left_group_${gIdx}" data-group-idx="${gIdx}" ondragover="ioHandleGroupDragOver(event)" ondragleave="ioHandleGroupDragLeave(event)" ondrop="ioHandleGroupDrop(event, ${gIdx})" style="border:2px dashed ${border};background:${bg};border-radius:8px;padding:12px;text-align:center;cursor:copy"><div style="font-size:11px;color:#94a3b8">📭 Empty Box ${gIdx+1}<br>Drop here</div><button class="btn btn-sm btn-outline" style="margin-top:6px" onclick="reportGroups.splice(${gIdx},1); renderAllReports();">✕ Remove</button></div>`;
    }else{
      const chips = groupTypes.map(t=> `<span class="report-chip chip-${t}" draggable="true" data-type="${t}" data-group="${gIdx}" ondragstart="ioHandleReportDragStart(event)" ondragend="ioHandleReportDragEnd(event)"><span class="type-dot dot-${t}"></span>${esc(REPORT_NAMES[t])}<span class="remove" onclick="event.stopPropagation(); ioSplitType(${gIdx},'${t}')">×</span></span>`).join('');
      html += `<div class="group-box ${isMerged?'merged':''}" id="left_group_${gIdx}" data-group-idx="${gIdx}" ondragover="ioHandleGroupDragOver(event)" ondragleave="ioHandleGroupDragLeave(event)" ondrop="ioHandleGroupDrop(event, ${gIdx})" onclick="ioJumpToGroup(${gIdx})" style="border:1px solid ${border};background:${bg};border-radius:8px;padding:8px;cursor:pointer">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><span style="font-size:10px;font-weight:700;color:#475569">BOX ${gIdx+1} ${isMerged?`(${groupTypes.length} merged)`:''}</span><span style="font-size:10px;color:#94a3b8">${isMerged?'🔗':''}</span></div>
        <div style="display:flex;flex-wrap:wrap;gap:4px">${chips}</div>
      </div>`;
    }
  });
  container.innerHTML = html || '<div style="text-align:center;color:#94a3b8;font-size:11px;padding:20px">No groups</div>';
  const countEl = document.getElementById('mergeGroupCount');
  if(countEl) countEl.textContent = String(reportGroups.filter(g=>g.length>0).length + (pendingNewGroup.length>0?1:0));
}

// ---------- Tables (dim-first) ----------
function buildFlatTable(data, dim, reportKey){
  const { columns, rows } = data;
  const dimLabel = DIM_LABELS[dim] || dim;
  const frozenW = 120;
  const dividerLeft = frozenW;
  const lastCol = columns[columns.length-1];
  let total=0, nz=0;
  rows.forEach(r=>{ const v=r[lastCol]||0; total+=v; if(v>0) nz++; });
  let html = `<div class="stat-row"><strong>${rows.length}</strong> rows &nbsp; <strong>${columns.length}</strong> cols &nbsp; Last total: <strong>${total.toLocaleString()}</strong></div>`;
  html += '<div class="table-wrapper"><table><thead><tr>';
  html += `<th class="frozen" style="left:0;min-width:${frozenW}px;z-index:16">${esc(dimLabel)}</th>`;
  html += `<th class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{ const p=c.split('_'); html += `<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`; });
  html += '</tr></thead><tbody>';
  let prevVal=null;
  rows.forEach((r)=>{
    const curVal=r[dim];
    const isNewGroup = prevVal!==null && prevVal!==curVal;
    prevVal=curVal;
    const rKey = r._REPORT_KEY || reportKey || '';
    html += `<tr class="row-${rKey} ${isNewGroup ? 'row-new-group' : ''}"><td class="frozen" style="left:0;min-width:${frozenW}px;z-index:5;font-weight:500;background:inherit">${esc(String(r[dim]??''))}</td><td class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
    columns.forEach(c=>{ const v=r[c]; html += `<td class="num ${v>0?'num-pos':v===0?'num-zero':''}">${v!=null ? Number(v).toLocaleString() : ''}</td>`; });
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  return html;
}

function buildMergedFlatTable(data, dim){
  const { columns, rows } = data;
  const dimLabel = DIM_LABELS[dim] || dim;
  const typeW = 130; const frozenW = 120; const dividerLeft = frozenW + typeW;
  let html = `<div class="stat-row"><strong>${rows.length}</strong> merged &nbsp; Types: <strong>${[...new Set(rows.map(r=>r._REPORT_TYPE))].join(', ')}</strong> — 同一 ${esc(dimLabel)} 相邻</div>`;
  html += '<div class="table-wrapper"><table><thead><tr>';
  html += `<th class="frozen" style="left:0;min-width:${frozenW}px;z-index:16">${esc(dimLabel)}</th>`;
  html += `<th class="frozen" style="left:${frozenW}px;min-width:${typeW}px;z-index:16">Type</th>`;
  html += `<th class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{ const p=c.split('_'); html += `<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`; });
  html += '</tr></thead><tbody>';
  const typeOrder = {}; REPORTS.forEach((t,i)=> typeOrder[t]=i);
  const sorted = [...rows].sort((a,b)=>{
    const av = a[dim]||'', bv = b[dim]||'';
    if(av < bv) return -1; if(av > bv) return 1;
    return (typeOrder[a._REPORT_KEY]??99)-(typeOrder[b._REPORT_KEY]??99);
  });
  let prevVal=null;
  sorted.forEach((r)=>{
    const isNewGroup = prevVal!==null && prevVal!==r[dim];
    prevVal=r[dim];
    html += `<tr class="row-${r._REPORT_KEY} ${isNewGroup?'row-new-group':''}"><td class="frozen" style="left:0;min-width:${frozenW}px;z-index:5;font-weight:500;background:inherit">${esc(String(r[dim]??''))}</td><td class="frozen" style="left:${frozenW}px;min-width:${typeW}px;z-index:5"><span class="type-badge type-${r._REPORT_KEY}">${esc(r._REPORT_TYPE||'')}</span></td><td class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
    columns.forEach(c=>{ const v=r[c]; html += `<td class="num">${v!=null?Number(v).toLocaleString():''}</td>`; });
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  return html;
}

function buildHierarchicalTable(data, dimOrder, reportKey){
  const { columns, rows } = data;
  const nDims = dimOrder.length; const frozenW=120; const divLeft=nDims*frozenW;
  function groupRows(items, depth){
    if(depth>=nDims) return items.map(r=> ({ key:null, items:[], allRows:[r] }));
    const dim = dimOrder[depth];
    const groups = {}; items.forEach(r=>{ const k=r[dim]||'(blank)'; if(!groups[k]) groups[k]=[]; groups[k].push(r); });
    return Object.keys(groups).sort().map(k=> ({ key:k, items: groupRows(groups[k], depth+1), allRows: groups[k] }));
  }
  const tree = groupRows(rows,0);
  function sumRows(arr){ const s={}; columns.forEach(c=>s[c]=0); arr.forEach(r=> columns.forEach(c=> s[c]+=(Number(r[c])||0))); return s; }
  const grandTotal = sumRows(rows);
  let h = `<div class="stat-row"><strong>${rows.length}</strong> detail rows</div><div class="table-wrapper"><table><thead><tr>`;
  dimOrder.forEach((d,i)=>{ const left=i*frozenW; h+=`<th class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:16">${esc(DIM_LABELS[d]||d)} <span class="expand-btn" onclick="window.ioExpandLevel(event,${i})">⊞</span></th>`; });
  h+=`<th class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{ const p=c.split('_'); h+=`<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`; });
  h+='</tr></thead><tbody>';
  let path=[]; const uidBase=Date.now();
  function renderTree(nodes, depth){
    nodes.forEach((node, idx)=>{
      path[depth]=idx; const pid=uidBase+'_'+path.slice(0,depth+1).join('_');
      if(depth===nDims-1){
        const agg=sumRows(node.allRows); const rk=node.allRows[0]?._REPORT_KEY||reportKey||'';
        h+=`<tr class="agg-row row-new-group row-${rk}">`;
        for(let d=0; d<nDims; d++){ const left=d*frozenW; h+=`<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5">${esc(d<depth?'':node.key)}</td>`; }
        h+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ h+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
        h+='</tr>';
      }else{
        const aggregated=node.items.flatMap(n=> n.allRows||[]); const agg=sumRows(aggregated); const rk=aggregated[0]?._REPORT_KEY||''; 
        h+=`<tr class="hierarchy-row agg-row row-new-group row-${rk}" id="${pid}" data-depth="${depth}" onclick="window.ioToggleDetail('${pid}')">`;
        for(let d=0; d<nDims; d++){ const left=d*frozenW; if(d===depth) h+=`<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5"><span class="toggle" id="tog_${pid}">▶</span>${esc(node.key)}</td>`; else if(d===depth+1) h+=`<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5">${node.items.length} items</td>`; else h+=`<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5"></td>`; }
        h+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ h+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
        h+='</tr><tbody id="children_${pid}" style="display:none">'; renderTree(node.items, depth+1); h+='</tbody>';
      }
    });
  }
  renderTree(tree,0);
  h+=`<tr class="total-row"><td class="frozen" style="left:0;min-width:${frozenW}px;z-index:5"><strong>Total</strong></td>${Array(nDims-1).fill(0).map((_,i)=>`<td class="frozen" style="left:${(i+1)*frozenW}px;min-width:${frozenW}px;z-index:5"></td>`).join('')}<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
  columns.forEach(c=>{ h+=`<td class="num"><strong>${Number(grandTotal[c]).toLocaleString()}</strong></td>`; });
  h+='</tr></tbody></table></div>';
  return h;
}

function buildMergedHierarchicalTable(data, dimOrder){
  const { columns, rows } = data;
  const effDims = [...dimOrder, '_REPORT_TYPE'];
  const nDims = effDims.length;
  const frozenW=120, typeW=130;
  const lefts=[]; let curL=0; effDims.forEach((_,i)=>{ lefts.push(curL); curL+= (i===nDims-1? typeW : frozenW); });
  const divLeft=curL;
  function groupRows(items, depth){
    if(depth>=nDims) return items.map(r=> ({ key:null, items:[], allRows:[r] }));
    const dim = effDims[depth];
    const groups={}; items.forEach(r=>{ const k=r[dim]||'(blank)'; if(!groups[k]) groups[k]=[]; groups[k].push(r); });
    const keys=Object.keys(groups);
    if(dim==='_REPORT_TYPE') keys.sort((a,b)=>{ const ia=REPORTS.findIndex(t=> REPORT_NAMES[t]===a); const ib=REPORTS.findIndex(t=> REPORT_NAMES[t]===b); return ia-ib; }); else keys.sort();
    return keys.map(k=> ({ key:k, items: groupRows(groups[k], depth+1), allRows: groups[k], repKey: groups[k][0]?._REPORT_KEY||'' }));
  }
  const tree=groupRows(rows,0);
  function sumRows(arr){ const s={}; columns.forEach(c=>s[c]=0); arr.forEach(r=> columns.forEach(c=> s[c]+=(Number(r[c])||0))); return s; }
  const grandTotal=sumRows(rows);
  let h=`<div class="stat-row"><strong>${rows.length}</strong> merged — 按行维度优先，同 ${dimOrder.map(d=>DIM_LABELS[d]||d).join('/')} 相邻</div><div class="table-wrapper"><table><thead><tr>`;
  effDims.forEach((d,i)=>{ const left=lefts[i]; const w=i===nDims-1? typeW : frozenW; const label=d==='_REPORT_TYPE'?'Type':(DIM_LABELS[d]||d); h+=`<th class="frozen" style="left:${left}px;min-width:${w}px;z-index:16">${esc(label)} <span class="expand-btn" onclick="window.ioExpandLevel(event,${i})">⊞</span></th>`; });
  h+=`<th class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{ const p=c.split('_'); h+=`<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`; });
  h+='</tr></thead><tbody>';
  let path=[]; const uidBase=Date.now();
  function renderTree(nodes, depth){
    nodes.forEach((node, idx)=>{
      path[depth]=idx; const pid=uidBase+'_'+path.slice(0,depth+1).join('_');
      const isTypeDepth=effDims[depth]==='_REPORT_TYPE'; const rk=node.repKey||node.allRows[0]?._REPORT_KEY||'';
      if(depth===nDims-1){
        const agg=sumRows(node.allRows);
        h+=`<tr class="agg-row row-new-group row-${rk}">`;
        for(let d=0; d<nDims; d++){ const left=lefts[d]; const val=d<depth?'':node.key; if(effDims[d]==='_REPORT_TYPE') h+=`<td class="frozen" style="left:${left}px;min-width:${typeW}px;z-index:5"><span class="type-badge type-${rk}">${esc(val)}</span></td>`; else h+=`<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5">${esc(val)}</td>`; }
        h+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ h+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; }); h+='</tr>';
      }else{
        const aggregated=node.items.flatMap(n=> n.allRows||[]); const agg=sumRows(aggregated); const repKey=node.items.length? aggregated[0]?._REPORT_KEY||'' : rk;
        h+=`<tr class="hierarchy-row agg-row row-new-group row-${repKey}" id="${pid}" data-depth="${depth}" onclick="window.ioToggleDetail('${pid}')">`;
        for(let d=0; d<nDims; d++){ const left=lefts[d]; const w=d===nDims-1? typeW : frozenW; if(d===depth) h+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span class="toggle" id="tog_${pid}">▶</span>${esc(node.key)}</td>`; else if(d===depth+1) h+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5">${node.items.length} items</td>`; else h+=`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"></td>`; }
        h+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ h+=`<td class="num">${Number(agg[c]).toLocaleString()}</td>`; }); h+='</tr><tbody id="children_${pid}" style="display:none">'; renderTree(node.items, depth+1); h+='</tbody>';
      }
    });
  }
  renderTree(tree,0);
  h+=`<tr class="total-row">`; for(let d=0; d<nDims; d++){ const left=lefts[d]; const w=d===nDims-1? typeW : frozenW; h+=d===0?`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><strong>Total</strong></td>`:`<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"></td>`; } h+=`<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`; columns.forEach(c=>{ h+=`<td class="num"><strong>${Number(grandTotal[c]).toLocaleString()}</strong></td>`; }); h+='</tr></tbody></table></div>';
  return h;
}

window.ioToggleDetail = function(pid){
  const t = document.getElementById('tog_'+pid);
  if(!t) return;
  const open = t.textContent==='▼';
  const children = document.getElementById('children_'+pid);
  if(!children) return;
  children.style.display = open ? 'none' : '';
  if(open){
    children.querySelectorAll('[id^="children_"]').forEach(el=>{ el.style.display='none'; });
    children.querySelectorAll('[id^="tog_"]').forEach(el=>{ el.textContent='▶'; });
  }
  t.textContent = open ? '▶' : '▼';
};
window.ioExpandLevel = function(event, level){
  event.stopPropagation();
  const table = event.target.closest('table');
  if(!table) return;
  const rows = table.querySelectorAll(`tr.agg-row[data-depth="${level}"]`);
  if(!rows.length) return;
  const firstTog = rows[0].querySelector('[id^="tog_"]');
  const allExpanded = firstTog && firstTog.textContent==='▼';
  rows.forEach(row=>{
    const pid=row.id; const t=document.getElementById('tog_'+pid); const children=document.getElementById('children_'+pid);
    if(!t||!children) return;
    if(allExpanded){ children.style.display='none'; t.textContent='▶'; }else{ children.style.display=''; t.textContent='▼'; }
  });
};

function downloadExcel(type){
  const data = allData?.[type];
  if(!data || !data.rows.length) return;
  const dim = getDimParam();
  const headers = dim==='detail' ? dimOrder : [dimOrder[0] || 'ITEM_NO'];
  const wsData = [ [...headers.map(h=> DIM_LABELS[h]||h), ...data.columns] ];
  data.rows.forEach(row=>{
    const r=[]; if(dim==='detail'){ headers.forEach(h=> r.push(row[h]||'')); } else { r.push(row[dimOrder[0]]??''); }
    data.columns.forEach(c=> r.push(row[c]??0)); wsData.push(r);
  });
  if(window.XLSX){
    const wb = XLSX.utils.book_new(); const ws = XLSX.utils.aoa_to_sheet(wsData);
    XLSX.utils.book_append_sheet(wb, ws, type.slice(0,31)); XLSX.writeFile(wb, `${REPORT_NAMES[type]||type}.xlsx`);
  }
}
window.ioDownloadExcel = downloadExcel;

function downloadMerged(gIdx){
  const groupTypes = reportGroups[gIdx];
  if(!groupTypes || !groupTypes.length) return;
  const merged = mergeTypesData(groupTypes);
  if(!merged.rows.length) return;
  const dim = getDimParam();
  const isDetail = dim==='detail' && dimOrder.length>=2;
  const headers = isDetail ? [...dimOrder.map(d=> DIM_LABELS[d]||d), 'Type'] : [DIM_LABELS[dim]||dim, 'Type'];
  const wsData = [ [...headers, ...merged.columns] ];
  const typeOrder={}; REPORTS.forEach((t,i)=> typeOrder[t]=i);
  const sorted=[...merged.rows].sort((a,b)=>{
    if(isDetail){ for(const d of dimOrder){ const av=a[d]||'', bv=b[d]||''; if(av<bv) return -1; if(av>bv) return 1; } }
    else { const av=a[dim]||'', bv=b[dim]||''; if(av<bv) return -1; if(av>bv) return 1; }
    return (typeOrder[a._REPORT_KEY]??99)-(typeOrder[b._REPORT_KEY]??99);
  });
  sorted.forEach(row=>{
    const r=[]; if(isDetail){ dimOrder.forEach(d=> r.push(row[d]||'')); } else { r.push(row[dim]??''); }
    r.push(row._REPORT_TYPE||''); merged.columns.forEach(c=> r.push(row[c]??0)); wsData.push(r);
  });
  if(window.XLSX){
    const wb = XLSX.utils.book_new(); const ws = XLSX.utils.aoa_to_sheet(wsData);
    XLSX.utils.book_append_sheet(wb, ws, groupTypes.map(t=> REPORT_NAMES[t]).join('_').slice(0,31)); XLSX.writeFile(wb, `${groupTypes.map(t=> REPORT_NAMES[t]).join('_')}.xlsx`);
  }
}
window.ioDownloadMerged = downloadMerged;

function downloadAll(){
  if(!allData) return;
  if(!window.XLSX){ alert('XLSX not loaded'); return; }
  const wb = XLSX.utils.book_new();
  const typeOrder={}; REPORTS.forEach((t,i)=> typeOrder[t]=i);
  reportGroups.forEach((groupTypes,gIdx)=>{
    const merged = mergeTypesData(groupTypes);
    if(!merged.rows.length) return;
    const dim = getDimParam();
    const isDetail = dim==='detail' && dimOrder.length>=2;
    const headers = isDetail ? [...dimOrder.map(d=> DIM_LABELS[d]||d), 'Type'] : [DIM_LABELS[dim]||dim, 'Type'];
    const wsData = [ [...headers, ...merged.columns] ];
    const sorted=[...merged.rows].sort((a,b)=>{
      if(isDetail){ for(const d of dimOrder){ const av=a[d]||'', bv=b[d]||''; if(av<bv) return -1; if(av>bv) return 1; } }
      else { const av=a[dim]||'', bv=b[dim]||''; if(av<bv) return -1; if(av>bv) return 1; }
      return (typeOrder[a._REPORT_KEY]??99)-(typeOrder[b._REPORT_KEY]??99);
    });
    sorted.forEach(row=>{
      const r=[]; if(isDetail){ dimOrder.forEach(d=> r.push(row[d]||'')); } else { r.push(row[dim]??''); }
      r.push(row._REPORT_TYPE||''); merged.columns.forEach(c=> r.push(row[c]??0)); wsData.push(r);
    });
    const ws = XLSX.utils.aoa_to_sheet(wsData);
    XLSX.utils.book_append_sheet(wb, ws, groupTypes.map(t=> REPORT_NAMES[t]).join('+').slice(0,31) || `Group${gIdx+1}`);
  });
  XLSX.writeFile(wb, `IO_Report_${currentGroup}_${COL_DIM}.xlsx`);
}
window.ioDownloadAll = downloadAll;

document.addEventListener('DOMContentLoaded', ()=>{
  const active = document.querySelector('.nav-item.active');
  if(active && active.dataset.module==='io-report'){ render(); }
});
document.addEventListener('module-change', (e)=>{ if(e.detail.module==='io-report'){ render(); } });
})();
