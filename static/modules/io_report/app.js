/**
 * I/O Report - 9 Tables with Mergeable Groups via Drag & Drop
 * Features:
 * - Row dim drag to order, col dim Day default
 * - Report Types draggable to merge into one table, with Type column + row colors
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

// --- merge groups state ---
let reportGroups = REPORTS.map(r => [r]); // 9 separate initially
let draggedReport = null; // {type, fromGroup}

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

// ---------- Upload ----------
function buildUploadSectionHTML(isCompact){
  const title = isCompact ? '📁 Upload I/O Data (Re-upload to update)' : '📁 Upload I/O Data (3 files required)';
  const gridStyle = isCompact ? 'display:grid;grid-template-columns:repeat(3,1fr) 1.2fr;gap:10px;align-items:end' : 'display:grid;grid-template-columns:repeat(3,1fr);gap:12px';
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
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px;margin-bottom:10px;font-size:11px;color:#475569;line-height:1.5">
        <strong>Required:</strong> Item Master (<code>ITEM_NO, PRODUCT_CATEGORY=FG/GB, PRODUCT_STYLE</code>) |
        Schedule Result (<code>LINE_CODE, SHIFT_NAME, PLAN_ITEM=INPUT/OUTPUT/CHECKIN/CHECKOUT, SKU, PLAN_DATE, PLAN_VALUE</code>) |
        BOH Balance (<code>PLAN_DATE, SHIFT_NAME, ITEM_CODE, BALANCE_QTY</code>)<br>
        Place 3 files in <code>data/</code> and click Recheck, or upload below.
      </div>
      <div id="${isCompact ? 'uploadBarContent' : 'uploadFullContent'}">
        <div class="upload-grid" style="${gridStyle}">
          <div class="upload-card" id="card_master_${isCompact?'compact':'full'}">
            <div class="upload-label">📁 Item Master <span class="req">*</span></div>
            <div class="upload-hint">料号主表.xlsx<br>ITEM_NO, CATEGORY, STYLE</div>
            <input type="file" class="file-input" id="input_master_${isCompact?'compact':'full'}" accept=".xlsx">
            <div class="fname" id="fname_master_${isCompact?'compact':'full'}" style="font-size:11px;color:#3b82f6;margin-top:6px"></div>
          </div>
          <div class="upload-card" id="card_schedule_${isCompact?'compact':'full'}">
            <div class="upload-label">📁 Schedule <span class="req">*</span></div>
            <div class="upload-hint">排产结果表.xlsx<br>LINE, SHIFT, PLAN_ITEM, SKU, DATE, VALUE</div>
            <input type="file" class="file-input" id="input_schedule_${isCompact?'compact':'full'}" accept=".xlsx">
            <div class="fname" id="fname_schedule_${isCompact?'compact':'full'}" style="font-size:11px;color:#3b82f6;margin-top:6px"></div>
          </div>
          <div class="upload-card" id="card_balance_${isCompact?'compact':'full'}">
            <div class="upload-label">📁 BOH Balance <span class="req">*</span></div>
            <div class="upload-hint">结存表.xlsx<br>DATE, SHIFT, ITEM_CODE, BALANCE_QTY</div>
            <input type="file" class="file-input" id="input_balance_${isCompact?'compact':'full'}" accept=".xlsx">
            <div class="fname" id="fname_balance_${isCompact?'compact':'full'}" style="font-size:11px;color:#3b82f6;margin-top:6px"></div>
          </div>
          ${isCompact ? '' : `
          <div class="upload-card" id="card_folder_full" style="border-style:dashed">
            <div class="upload-label">📂 Folder (3 files)</div>
            <div class="upload-hint">Select folder containing 3 xlsx, auto-matched</div>
            <input type="file" id="input_folder_full" webkitdirectory style="display:none">
            <button class="btn btn-sm btn-outline" id="btnFolder_full" style="margin-top:6px">Choose Folder</button>
            <div class="fname" id="fname_folder_full" style="font-size:11px;color:#3b82f6;margin-top:6px"></div>
          </div>
          `}
        </div>
        <div style="margin-top:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <button class="btn" id="uploadBtn_${isCompact?'compact':'full'}" disabled style="padding:6px 20px">▶ Upload & Analyze</button>
          <button class="btn btn-outline btn-sm" id="btnRetryLoad_${isCompact?'compact':'full'}">↻ Recheck data/ folder</button>
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
        const fn = document.getElementById('fname_'+k+'_'+suffix);
        if(fn) fn.textContent = '✓ ' + input.files[0].name;
        markHasFile('card_'+k+'_'+suffix, true);
      }else{
        files[k]=null;
        markHasFile('card_'+k+'_'+suffix, false);
      }
      updateBtn();
    });
  });
  if(!isCompact){
    const folderInput = document.getElementById('input_folder_full');
    const folderBtn = document.getElementById('btnFolder_full');
    if(folderBtn) folderBtn.addEventListener('click', ()=> folderInput.click());
    if(folderInput){
      folderInput.addEventListener('change', ()=>{
        if(!folderInput.files.length) return;
        for(const f of folderInput.files){
          const lower = f.name.toLowerCase();
          if(lower.includes('master') || f.name.includes('料号')){
            files.master=f; document.getElementById('fname_master_full').textContent='✓ '+f.name; markHasFile('card_master_full',true);
          }else if(lower.includes('schedule') || lower.includes('result') || f.name.includes('排产')){
            files.schedule=f; document.getElementById('fname_schedule_full').textContent='✓ '+f.name; markHasFile('card_schedule_full',true);
          }else if(lower.includes('balance') || lower.includes('boh') || f.name.includes('结存')){
            files.balance=f; document.getElementById('fname_balance_full').textContent='✓ '+f.name; markHasFile('card_balance_full',true);
          }
        }
        const xlsx = Array.from(folderInput.files).filter(x=> x.name.endsWith('.xlsx'));
        if(xlsx.length>=3){
          if(!files.master){ files.master=xlsx[0]; document.getElementById('fname_master_full').textContent='✓ '+xlsx[0].name; markHasFile('card_master_full',true); }
          if(!files.schedule){ files.schedule=xlsx[1]; document.getElementById('fname_schedule_full').textContent='✓ '+xlsx[1].name; markHasFile('card_schedule_full',true); }
          if(!files.balance){ files.balance=xlsx[2]; document.getElementById('fname_balance_full').textContent='✓ '+xlsx[2].name; markHasFile('card_balance_full',true); }
        }
        const ff = document.getElementById('fname_folder_full');
        if(ff){ const cnt=Object.values(files).filter(Boolean).length; ff.textContent = cnt===3 ? '✅ Matched 3 files' : `⚠️ Matched ${cnt}/3`; }
        updateBtn();
      });
    }
  }
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
        if(result.ok || result.fg!==undefined){
          if(prog) prog.innerHTML = `<span style="color:#059669">✅ Loaded: ${result.fg||0} FG, ${result.gb||0} GB - Refreshing...</span>`;
          setTimeout(()=> renderReportsPage(), 1000);
        }else{
          if(prog) prog.innerHTML = `<span style="color:#dc2626">❌ Failed: ${JSON.stringify(result)}</span>`;
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
      const prog = document.getElementById('uploadProgress_'+suffix);
      if(ok){
        if(prog) prog.textContent='✅ Data found, loading reports...';
        renderReportsPage();
      }else{
        alert('No valid data in data/. Place 3 files: 料号主表.xlsx, 排产结果表.xlsx, 结存表.xlsx');
      }
    });
  }
  if(isCompact){
    const toggle = document.getElementById('toggleUploadBar');
    if(toggle){
      toggle.addEventListener('click', ()=>{
        const content = document.getElementById('uploadBarContent');
        if(!content) return;
        const isHidden = content.style.display==='none';
        content.style.display = isHidden ? 'block' : 'none';
        toggle.textContent = isHidden ? '▼ Collapse' : '▶ Expand';
      });
    }
  }
}

function renderUploadPage(){
  ioRoot.innerHTML = buildUploadSectionHTML(false);
  attachUploadLogic(false);
}

// ---------- Reports Page ----------
function renderReportsPage(){
  ioRoot.innerHTML = buildUploadSectionHTML(true) + `
    <div class="section" id="io-main-section">
      <div class="section-header">
        <span class="section-title">📈 I/O Report</span>
        <div class="section-actions">
          <span id="io-report-status" style="font-size:12px;color:#059669"></span>
          <button id="io-dl-all" class="btn btn-sm btn-outline">📥 Download All (Excel)</button>
          <button id="io-reset-groups" class="btn btn-sm btn-outline">↺ Reset Groups</button>
        </div>
      </div>

      <div class="dim-tabs" id="io-group-tabs">
        <button class="dim-tab active" data-group="FG">FG (SKU)</button>
        <button class="dim-tab" data-group="GB">GB</button>
      </div>

      <div class="toolbar" id="io-toolbar">
        <div class="panels-row">
          <div class="panel" style="flex:1;min-width:260px">
            <div class="panel-label">Row Dimensions (drag to order)</div>
            <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:6px">
              <span class="dim-chip available" draggable="true" data-dim="LINE_CODE">Line</span>
              <span class="dim-chip available" draggable="true" data-dim="ITEM_NO">PN</span>
              <span class="dim-chip available" draggable="true" data-dim="STYLE">Style</span>
              <div id="ioDimWell" class="dim-well">
                <span class="placeholder">Drop dimensions here</span>
              </div>
            </div>
            <div style="font-size:10px;color:#94a3b8;margin-top:4px">Drag to order. 1 dim = flat, 2+ = expandable groups.</div>
          </div>

          <div class="panel" style="min-width:200px">
            <div class="panel-label">Column Dimensions</div>
            <div class="btn-group" id="ioColDimTabs" style="margin-top:6px">
              <button class="btn" data-coldim="shift">Shift</button>
              <button class="btn active" data-coldim="day">Day</button>
              <button class="btn" data-coldim="week">Week</button>
              <button class="btn" data-coldim="month">Month</button>
            </div>
          </div>

          <div class="panel" style="flex:1;min-width:300px">
            <div class="panel-label">Filters</div>
            <div class="filter-row" style="margin-top:6px">
              <div class="filter-group">
                <label>Line</label>
                <div class="filter-input-wrap" id="fiw_lineCode">
                  <input type="text" class="filter-input" id="fi_lineCode" placeholder="All" autocomplete="off">
                  <span class="filter-arrow">▾</span>
                  <div class="filter-dropdown" id="fd_lineCode"></div>
                </div>
              </div>
              <div class="filter-group">
                <label>PN</label>
                <div class="filter-input-wrap" id="fiw_itemNo">
                  <input type="text" class="filter-input" id="fi_itemNo" placeholder="All" autocomplete="off">
                  <span class="filter-arrow">▾</span>
                  <div class="filter-dropdown" id="fd_itemNo"></div>
                </div>
              </div>
              <div class="filter-group">
                <label>Style</label>
                <div class="filter-input-wrap" id="fiw_style">
                  <input type="text" class="filter-input" id="fi_style" placeholder="All" autocomplete="off">
                  <span class="filter-arrow">▾</span>
                  <div class="filter-dropdown" id="fd_style"></div>
                </div>
              </div>
              <div class="filter-group" style="justify-content:flex-end">
                <button id="ioRefreshBtn" class="btn btn-outline btn-sm" style="margin-top:14px">Refresh</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="merge-info" style="margin-top:12px;padding:8px 12px;background:#f0f9ff;border:1px dashed #93c5fd;border-radius:6px;font-size:11px;color:#334155;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <span>💡 <strong>Merge:</strong> drag芯片到另一卡片合并为一张表（多合一），合并表新增 <code>Type</code> 列并按类型着色。支持同时存在多个合并组，例如 Group1=Daily+Cum Input，Group2=Daily+Cum Output。</span>
        <span style="color:#64748b">Groups: <span id="mergeGroupCount">9</span></span>
        <button id="addEmptyGroupBtn" class="btn btn-sm btn-outline" style="padding:2px 8px;font-size:11px">➕ Add Empty Group</button>
      </div>

      <div class="container-fluid" style="padding:0;margin-top:12px">
        <div class="row" style="display:flex;gap:12px">
          <div class="col-1" style="flex:0 0 160px;max-width:160px">
            <div class="io-sidebar" style="position:sticky;top:70px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:8px">
              <div style="font-size:11px;font-weight:600;color:#475569;margin-bottom:8px;text-transform:uppercase">Report Types (9)</div>
              ${REPORTS.map((r,i)=> `<a class="anchor report-anchor" href="#" data-type="${r}" style="display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:4px;font-size:12px;color:#334155;text-decoration:none;margin-bottom:2px;cursor:pointer"><span class="type-dot dot-${r}" style="width:8px;height:8px;border-radius:50%;display:inline-block"></span>${i+1}. ${esc(REPORT_NAMES[r])}</a>`).join('')}
              <div style="margin-top:12px;border-top:1px solid #e2e8f0;padding-top:8px;font-size:10px;color:#94a3b8">Click to jump. Drag chips to merge.<br>支持多组合并：可同时存在 Group1=Daily+Cum Input, Group2=Output+BOH 等。</div>
              <div id="unassignedDrop" class="unassigned-drop" style="margin-top:12px;border:2px dashed #cbd5e1;border-radius:6px;padding:8px;text-align:center;font-size:11px;color:#94a3b8">Drop here to split into separate group</div>
              <div id="newMergedDrop" class="unassigned-drop" style="margin-top:8px;border:2px dashed #8b5cf6;border-radius:6px;padding:8px;text-align:center;font-size:11px;color:#6d28d9;background:#faf5ff">➕ Drop here to create NEW merged group<br><small style="font-size:10px;color:#94a3b8">拖入多个类型自动合并</small></div>
            </div>
          </div>
          <div class="col-11" style="flex:1;min-width:0">
            <div id="ioReportContent">
              <div style="text-align:center;padding:40px;color:#94a3b8">Please drag row dimensions into the box above</div>
            </div>
          </div>
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

  const rb = document.getElementById('ioRefreshBtn');
  if(rb) rb.addEventListener('click', loadAllReports);
  const dlAll = document.getElementById('io-dl-all');
  if(dlAll) dlAll.addEventListener('click', downloadAll);
  const resetBtn = document.getElementById('io-reset-groups');
  if(resetBtn) resetBtn.addEventListener('click', ()=>{ reportGroups = REPORTS.map(r=>[r]); pendingNewGroup = []; renderAllReports(); });
  const addEmptyBtn = document.getElementById('addEmptyGroupBtn');
  if(addEmptyBtn) addEmptyBtn.addEventListener('click', ()=>{ addEmptyGroup(); });

  // sidebar anchor jump - now jumps to group containing type
  document.querySelectorAll('.report-anchor').forEach(a=>{
    a.addEventListener('click', (e)=>{
      e.preventDefault();
      const rtype = a.dataset.type;
      const gIdx = reportGroups.findIndex(g=> g.includes(rtype));
      const el = document.getElementById(gIdx>=0 ? `io_group_${gIdx}` : `io_sec_${rtype}`);
      el?.scrollIntoView({behavior:'smooth', block:'start'});
      document.querySelectorAll('.report-anchor').forEach(x=> x.style.background='');
      a.style.background='#eff6ff';
      a.style.color='#3b82f6';
    });
  });
}

// ---------- Searchable selects ----------
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
    if(item.dataset.value===''){ item.style.display=''; }
    else{ item.style.display = item.textContent.toLowerCase().includes(text.toLowerCase()) ? '' : 'none'; }
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

// ---------- Dim drag drop ----------
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
    well.addEventListener('dragover', e=>{ if(e.dataTransfer.types.includes('text/x-dim')|| e.dataTransfer.getData('text/plain') in DIM_LABELS || true){ e.preventDefault(); well.classList.add('drag-over'); }});
    well.addEventListener('dragleave', ()=> well.classList.remove('drag-over'));
    well.addEventListener('drop', e=>{
      e.preventDefault(); well.classList.remove('drag-over');
      if(e.dataTransfer.getData('text/x-report')) return; // ignore report chips
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
  }catch(e){ console.error('refreshMeta fail', e); }
}
async function loadAllReports(){
  const dim = getDimParam();
  const content = document.getElementById('ioReportContent');
  if(!dim){
    allData=null;
    if(content) content.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">Please drag row dimensions into the box above</div>';
    return;
  }
  if(content) content.innerHTML = '<div style="text-align:center;padding:24px;color:#64748b">⏳ Loading reports...</div>';
  const groupParam = currentGroup === 'FG' ? '成品' : 'GB';
  const params = new URLSearchParams({group:groupParam, dim, col_dim:COL_DIM, line_code:filterVals.lineCode, item_no:filterVals.itemNo, style:filterVals.style});
  try{
    const resp = await fetch(`/api/io/reports?${params}`);
    const data = await resp.json();
    if(data.error) throw new Error(data.error);
    allData = data;
    renderAllReports();
  }catch(e){
    if(content) content.innerHTML = `<div style="text-align:center;padding:24px;color:#dc2626">❌ Load failed: ${esc(e.message)}</div>`;
  }
}

// ---------- Merge logic - supports multiple merged groups ----------
let pendingNewGroup = []; // for creating new merged group via drop zone

function initMergeDragDrop(){
  const unassigned = document.getElementById('unassignedDrop');
  if(unassigned){
    unassigned.addEventListener('dragover', e=>{ if(draggedReport){ e.preventDefault(); unassigned.classList.add('drag-over'); }});
    unassigned.addEventListener('dragleave', ()=> unassigned.classList.remove('drag-over'));
    unassigned.addEventListener('drop', e=>{
      e.preventDefault(); unassigned.classList.remove('drag-over');
      if(!draggedReport) return;
      const {type, fromGroup} = draggedReport;
      const from = reportGroups[fromGroup];
      if(from){
        const idx = from.indexOf(type);
        if(idx>=0) from.splice(idx,1);
        if(from.length===0) reportGroups.splice(fromGroup,1);
      }
      reportGroups.push([type]);
      draggedReport=null;
      renderAllReports();
    });
  }
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
      // accumulate into pendingNewGroup
      if(!pendingNewGroup.includes(type)) pendingNewGroup.push(type);
      draggedReport=null;
      renderAllReports();
    });
  }
}

function addEmptyGroup(){
  reportGroups.push([]);
  renderAllReports();
}
window.ioAddEmptyGroup = addEmptyGroup;

function handleReportDragStart(e){
  const type = e.currentTarget.dataset.type;
  const fromGroup = e.currentTarget.dataset.group ? parseInt(e.currentTarget.dataset.group) : -1;
  // if from pending group
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
  document.querySelectorAll('.merge-group').forEach(el=> el.classList.remove('drag-over'));
  document.querySelectorAll('.unassigned-drop').forEach(el=> el.classList.remove('drag-over'));
}
function handleGroupDragOver(e){
  if(!draggedReport) return;
  e.preventDefault();
  e.currentTarget.classList.add('drag-over');
}
function handleGroupDragLeave(e){
  e.currentTarget.classList.remove('drag-over');
}
function handleGroupDrop(e, toGroupIdx){
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  if(!draggedReport) return;
  const {type, fromGroup, fromPending} = draggedReport;
  if(!fromPending && fromGroup===toGroupIdx) { draggedReport=null; return; }

  if(fromPending){
    // from pending new group to existing group
    const idx = pendingNewGroup.indexOf(type);
    if(idx>=0) pendingNewGroup.splice(idx,1);
    const to = reportGroups[toGroupIdx];
    if(to && !to.includes(type)) to.push(type);
  }else{
    const from = reportGroups[fromGroup];
    const to = reportGroups[toGroupIdx];
    if(!from || !to) { draggedReport=null; return; }
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
  if(g.length===0){
    reportGroups.splice(groupIdx,1);
  }
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
    pendingNewGroup = [];
    renderAllReports();
  }
}
window.ioConfirmPendingGroup = confirmPendingGroup;

function clearPendingGroup(){
  // return types to separate groups
  pendingNewGroup.forEach(t=> reportGroups.push([t]));
  pendingNewGroup = [];
  renderAllReports();
}
window.ioClearPendingGroup = clearPendingGroup;

// Merge helpers
function mergeTypesData(types){
  let columns = [];
  let colSet = new Set();
  // union columns preserving order of first occurrence
  types.forEach(t=>{
    const d = allData[t];
    if(!d || !d.columns) return;
    d.columns.forEach(c=>{ if(!colSet.has(c)){ colSet.add(c); columns.push(c); }});
  });
  let rows = [];
  types.forEach(t=>{
    const d = allData[t];
    if(!d || !d.rows) return;
    d.rows.forEach(r=>{
      rows.push({ ...r, _REPORT_TYPE: REPORT_NAMES[t], _REPORT_KEY: t });
    });
  });
  return { columns, rows };
}

function renderAllReports(){
  const content = document.getElementById('ioReportContent');
  const countEl = document.getElementById('mergeGroupCount');
  if(!content) return;
  if(!allData){ content.innerHTML = '<div style="text-align:center;padding:24px;color:#94a3b8">No data</div>'; return; }
  // keep empty groups for UX, but ensure at least one group
  if(reportGroups.length===0) reportGroups = REPORTS.map(r=>[r]);
  // count display: include pending as half?
  if(countEl) countEl.textContent = String(reportGroups.filter(g=>g.length>0).length + (pendingNewGroup.length>0?1:0));

  let html = '';

  // render pending new merged group on top if exists
  if(pendingNewGroup.length>0){
    html += `<div class="report-section merge-group merged pending" id="io_group_pending" style="border-color:#8b5cf6;background:#faf5ff" ondragover="ioHandleGroupDragOver(event)" ondragleave="ioHandleGroupDragLeave(event)" ondrop="event.preventDefault(); if(!draggedReport) return; const {type,fromGroup,fromPending}=draggedReport; if(fromPending){ const idx=pendingNewGroup.indexOf(type); if(idx>=0) pendingNewGroup.splice(idx,1); }else{ const from=reportGroups[fromGroup]; if(from){ const i=from.indexOf(type); if(i>=0) from.splice(i,1); if(from.length===0) reportGroups.splice(fromGroup,1); } } if(!pendingNewGroup.includes(type)) pendingNewGroup.push(type); draggedReport=null; renderAllReports();">
      <div class="group-header" style="display:flex;justify-content:space-between;align-items:center;gap:8px;border-bottom:2px dashed #8b5cf6;padding-bottom:6px;margin-bottom:8px">
        <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">
          <span style="font-size:11px;font-weight:700;color:#6d28d9">🆕 NEW GROUP (${pendingNewGroup.length} types):</span>
          ${pendingNewGroup.map(t=> `<span class="report-chip chip-${t}" draggable="true" data-type="${t}" data-pending="1" ondragstart="ioHandleReportDragStart(event)" ondragend="ioHandleReportDragEnd(event)"><span class="type-dot dot-${t}"></span>${esc(REPORT_NAMES[t])} <span class="remove" onclick="event.stopPropagation(); ioRemovePendingType('${t}')">×</span></span>`).join('')}
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-sm" onclick="ioConfirmPendingGroup()">✓ Confirm</button>
          <button class="btn btn-sm btn-outline" onclick="ioClearPendingGroup()">✕ Cancel</button>
        </div>
      </div>
      <div style="font-size:11px;color:#64748b">Will be <strong>${pendingNewGroup.map(t=>REPORT_NAMES[t]).join(' + ')}</strong> ${pendingNewGroup.length>1?'(merged with Type column)':''}</div>
    </div>`;
  }
  reportGroups.forEach((groupTypes, gIdx)=>{
    if(!groupTypes || groupTypes.length===0){
      html += `<div class="report-section merge-group empty" id="io_group_${gIdx}" data-group-idx="${gIdx}" ondragover="ioHandleGroupDragOver(event)" ondragleave="ioHandleGroupDragLeave(event)" ondrop="ioHandleGroupDrop(event, ${gIdx})" style="border:2px dashed #cbd5e1;background:#f8fafc">
        <div style="text-align:center;padding:20px;color:#94a3b8">📭 Empty Group ${gIdx+1} — Drop report type chips here to create ${'<strong>multiple merged groups</strong>同时共存'}<br><small>可拖入多个类型形成合并表，例如 Daily+Cum Input 为一组，Daily+Cum Output 为另一组</small></div>
        <div style="text-align:center;margin-top:8px"><button class="btn btn-sm btn-outline" onclick="reportGroups.splice(${gIdx},1); renderAllReports();">✕ Remove Empty Group</button></div>
      </div>`;
      return;
    }
    const isMerged = groupTypes.length > 1;
    const titles = groupTypes.map(t=> REPORT_NAMES[t]).join(' + ');
    const isDetail = getDimParam()==='detail' && dimOrder.length>=2;
    let tableHTML = '';
    let totalRows = 0;
    let totalCols = 0;

    if(isMerged){
      const merged = mergeTypesData(groupTypes);
      totalRows = merged.rows.length;
      totalCols = merged.columns.length;
      if(totalRows===0){
        tableHTML = '<div style="text-align:center;padding:20px;color:#94a3b8">No data for current filters</div>';
      }else{
        if(isDetail){
          tableHTML = buildMergedHierarchicalTable(merged, dimOrder);
        }else{
          tableHTML = buildMergedFlatTable(merged, dimOrder[0] || 'ITEM_NO');
        }
      }
    }else{
      const rtype = groupTypes[0];
      const data = allData[rtype];
      totalRows = data ? data.rows.length : 0;
      totalCols = data ? data.columns.length : 0;
      if(!data || !data.rows || data.rows.length===0){
        tableHTML = '<div style="text-align:center;padding:20px;color:#94a3b8">No data for current filters</div>';
      }else{
        const enriched = { columns: data.columns, rows: data.rows.map(r=> ({...r, _REPORT_TYPE: REPORT_NAMES[rtype], _REPORT_KEY: rtype})) };
        if(isDetail){
          tableHTML = isMerged ? buildMergedHierarchicalTable(enriched, dimOrder) : buildHierarchicalTable(enriched, dimOrder, rtype);
        }else{
          tableHTML = isMerged ? buildMergedFlatTable(enriched, dimOrder[0]||'ITEM_NO') : buildFlatTable(enriched, dimOrder[0]||'ITEM_NO', rtype);
        }
      }
    }

    const chips = groupTypes.map(t=> `<span class="report-chip chip-${t}" draggable="true" data-type="${t}" data-group="${gIdx}" ondragstart="ioHandleReportDragStart(event)" ondragend="ioHandleReportDragEnd(event)"><span class="type-dot dot-${t}"></span>${esc(REPORT_NAMES[t])} <span class="remove" onclick="event.stopPropagation(); ioSplitType(${gIdx},'${t}')">×</span></span>`).join('');

    html += `<div class="report-section merge-group ${isMerged?'merged':''}" id="io_group_${gIdx}" data-group-idx="${gIdx}" ondragover="ioHandleGroupDragOver(event)" ondragleave="ioHandleGroupDragLeave(event)" ondrop="ioHandleGroupDrop(event, ${gIdx})">
      <div class="group-header" style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;border-bottom:2px solid ${isMerged?'#8b5cf6':'#3b82f6'};padding-bottom:6px;margin-bottom:8px">
        <div style="flex:1;min-width:0">
          <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:4px">${chips}</div>
          <div style="font-size:11px;color:#64748b">${esc(titles)} — ${totalRows} rows × ${totalCols} cols ${isMerged?'<span style="color:#8b5cf6;font-weight:600"> (Merged, Type column added)</span>':''}</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-shrink:0">
          ${isMerged
            ? `<button class="btn btn-sm btn-outline" onclick="window.ioDownloadMerged(${gIdx})">📥 Excel</button>`
            : `<button class="btn btn-sm btn-outline" onclick="window.ioDownloadExcel('${groupTypes[0]}')">📥 Excel</button>`
          }
        </div>
      </div>
      ${tableHTML}
    </div>`;
  });

  content.innerHTML = html;
}

// ---------- Tables ----------
function buildFlatTable(data, dim, reportKey){
  const { columns, rows } = data;
  const dimLabel = DIM_LABELS[dim] || dim;
  const frozenW = 120;
  const typeW = 110;
  const isEnriched = rows.length>0 && rows[0]._REPORT_KEY;
  // For single table, we show Type as first column only if we want colors? But requirement is Type column for merged only.
  // For single, we still add type class for coloring but not show Type column (or show as badge?). We'll hide Type column for single to keep familiar, but row colors by type.
  const showTypeCol = false;

  const dividerLeft = showTypeCol ? typeW+frozenW : frozenW;
  const lastCol = columns[columns.length-1];
  let total=0, nz=0;
  rows.forEach(r=>{ const v=r[lastCol]||0; total+=v; if(v>0) nz++; });

  let html = `<div class="stat-row"><strong>${rows.length}</strong> rows &nbsp; <strong>${columns.length}</strong> cols &nbsp; Last col total: <strong>${total.toLocaleString()}</strong> &nbsp; Non-zero: <strong>${nz}</strong></div>`;
  html += '<div class="table-wrapper"><table><thead><tr>';
  if(showTypeCol){
    html += `<th class="frozen" style="left:0;min-width:${typeW}px;z-index:16">Type</th>`;
    html += `<th class="frozen" style="left:${typeW}px;min-width:${frozenW}px;z-index:16">${esc(dimLabel)}</th>`;
  }else{
    html += `<th class="frozen" style="left:0;min-width:${frozenW}px;z-index:16">${esc(dimLabel)}</th>`;
  }
  html += `<th class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{
    const p=c.split('_');
    html += `<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`;
  });
  html += '</tr></thead><tbody>';
  let prevVal=null;
  rows.forEach((r)=>{
    const curVal=r[dim];
    const isNewGroup = prevVal!==null && prevVal!==curVal;
    prevVal=curVal;
    const rKey = r._REPORT_KEY || reportKey || '';
    const rowCls = `row-${rKey} ${isNewGroup ? 'row-new-group' : ''}`;
    html += `<tr class="${rowCls}">`;
    if(showTypeCol){
      html += `<td class="frozen" style="left:0;min-width:${typeW}px;z-index:5"><span class="type-badge type-${rKey}">${esc(r._REPORT_TYPE||'')}</span></td>`;
      html += `<td class="frozen" style="left:${typeW}px;min-width:${frozenW}px;z-index:5;font-weight:500;background:inherit">${esc(String(r[dim]??''))}</td>`;
    }else{
      html += `<td class="frozen" style="left:0;min-width:${frozenW}px;z-index:5;font-weight:500;background:inherit">${esc(String(r[dim]??''))}</td>`;
    }
    html += `<td class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
    columns.forEach(c=>{
      const v=r[c];
      const cls = v>0 ? 'num num-pos' : v===0 ? 'num num-zero' : 'num';
      html += `<td class="${cls}">${v!=null ? Number(v).toLocaleString() : ''}</td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  return html;
}

function buildMergedFlatTable(data, dim){
  const { columns, rows } = data;
  const dimLabel = DIM_LABELS[dim] || dim;
  const typeW = 130;
  const frozenW = 120;
  const dividerLeft = typeW+frozenW;

  let html = `<div class="stat-row"><strong>${rows.length}</strong> rows (merged) &nbsp; <strong>${columns.length}</strong> cols &nbsp; Types: <strong>${[...new Set(rows.map(r=>r._REPORT_TYPE))].join(', ')}</strong></div>`;
  html += '<div class="table-wrapper"><table><thead><tr>';
  html += `<th class="frozen" style="left:0;min-width:${typeW}px;z-index:16">Type</th>`;
  html += `<th class="frozen" style="left:${typeW}px;min-width:${frozenW}px;z-index:16">${esc(dimLabel)}</th>`;
  html += `<th class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{
    const p=c.split('_');
    html += `<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`;
  });
  html += '</tr></thead><tbody>';
  // sort by Type then dim
  const sorted = [...rows].sort((a,b)=>{
    if(a._REPORT_KEY < b._REPORT_KEY) return -1;
    if(a._REPORT_KEY > b._REPORT_KEY) return 1;
    const av = a[dim]||'', bv = b[dim]||'';
    return av < bv ? -1 : av > bv ? 1 : 0;
  });
  let prevType=null, prevVal=null;
  sorted.forEach((r)=>{
    const curType=r._REPORT_KEY;
    const curVal=r[dim];
    const isNewType = prevType!==null && prevType!==curType;
    const isNewVal = !isNewType && prevVal!==null && prevVal!==curVal;
    const isNewGroup = isNewType || isNewVal;
    prevType=curType; prevVal=curVal;
    const rowCls = `row-${curType} ${isNewGroup ? 'row-new-group' : ''}`;
    html += `<tr class="${rowCls}">`;
    html += `<td class="frozen" style="left:0;min-width:${typeW}px;z-index:5"><span class="type-badge type-${curType}">${esc(r._REPORT_TYPE||'')}</span></td>`;
    html += `<td class="frozen" style="left:${typeW}px;min-width:${frozenW}px;z-index:5;font-weight:500;background:inherit">${esc(String(r[dim]??''))}</td>`;
    html += `<td class="frozen divider-col" style="left:${dividerLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
    columns.forEach(c=>{
      const v=r[c];
      html += `<td class="num ${v>0?'num-pos':v===0?'num-zero':''}">${v!=null ? Number(v).toLocaleString() : ''}</td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  return html;
}

function buildHierarchicalTable(data, dimOrder, reportKey){
  const { columns, rows } = data;
  const nDims = dimOrder.length;
  const frozenW = 120;
  const divLeft = nDims*frozenW;

  function groupRows(items, depth){
    if(depth>=nDims){ return items.map(r=> ({ key: null, items: [], allRows: [r] })); }
    const dim = dimOrder[depth];
    const groups = {};
    items.forEach(r=>{ const k=r[dim]||'(blank)'; if(!groups[k]) groups[k]=[]; groups[k].push(r); });
    return Object.keys(groups).sort().map(k=> ({ key:k, items: groupRows(groups[k], depth+1), allRows: groups[k] }));
  }
  const tree = groupRows(rows, 0);
  function sumRows(arr){
    const s={}; columns.forEach(c=>s[c]=0); arr.forEach(r=> columns.forEach(c=> s[c]+=(Number(r[c])||0))); return s;
  }
  const grandTotal = sumRows(rows);

  let h = `<div class="stat-row"><strong>${rows.length}</strong> detail rows &nbsp; <strong>${columns.length}</strong> cols</div>`;
  h += '<div class="table-wrapper"><table><thead><tr>';
  dimOrder.forEach((d,i)=>{
    const btn = i < nDims-1 ? `<span class="expand-btn" onclick="window.ioExpandLevel(event,${i})" title="Expand/Collapse all">⊞</span>` : '';
    const left = i*frozenW;
    h += `<th class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:16">${esc(DIM_LABELS[d]||d)} ${btn}</th>`;
  });
  h += `<th class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{
    const p=c.split('_');
    h += `<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`;
  });
  h += '</tr></thead><tbody>';

  let path=[];
  const uidBase = Date.now();
  function renderTree(nodes, depth){
    nodes.forEach((node, idx)=>{
      path[depth]=idx;
      const pid = uidBase+'_'+path.slice(0,depth+1).join('_');
      if(depth===nDims-1){
        const agg = sumRows(node.allRows);
        const sampleKey = node.allRows[0]?._REPORT_KEY || reportKey || '';
        h += `<tr class="agg-row row-new-group row-${sampleKey}">`;
        for(let d=0; d<nDims; d++){
          const left = d*frozenW;
          const val = d<depth ? '' : node.key;
          h += `<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5">${esc(val)}</td>`;
        }
        h += `<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ h+= `<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
        h += '</tr>';
      }else{
        const aggregated = node.items.flatMap(n=> n.allRows || []);
        const agg = sumRows(aggregated);
        const sampleKey = aggregated[0]?._REPORT_KEY || reportKey || '';
        h += `<tr class="hierarchy-row agg-row row-new-group row-${sampleKey}" id="${pid}" data-depth="${depth}" onclick="window.ioToggleDetail('${pid}')">`;
        for(let d=0; d<nDims; d++){
          const left = d*frozenW;
          if(d===depth){
            h += `<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5"><span class="toggle" id="tog_${pid}">▶</span>${esc(node.key)}</td>`;
          }else if(d===depth+1){
            h += `<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5">${node.items.length} items</td>`;
          }else{
            h += `<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5"></td>`;
          }
        }
        h += `<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ h+= `<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
        h += '</tr>';
        h += `<tbody id="children_${pid}" data-parent="${pid}" style="display:none">`;
        renderTree(node.items, depth+1);
        h += '</tbody>';
      }
    });
  }
  renderTree(tree,0);

  h += '<tr class="total-row">';
  for(let d=0; d<nDims; d++){
    const left = d*frozenW;
    h += d===0 ? `<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5"><strong>Total</strong></td>` : `<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5"></td>`;
  }
  h += `<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
  columns.forEach(c=>{ h+= `<td class="num"><strong>${Number(grandTotal[c]).toLocaleString()}</strong></td>`; });
  h += '</tr></tbody></table></div>';
  return h;
}

function buildMergedHierarchicalTable(data, dimOrder){
  const { columns, rows } = data;
  // effective dims: Type + dimOrder
  const effDims = ['_REPORT_TYPE', ...dimOrder];
  const nDims = effDims.length;
  const frozenW = 120;
  const typeW = 130;
  // compute left offsets: first is Type 130, rest 120
  const lefts = [];
  let curL = 0;
  effDims.forEach((_, i)=>{
    lefts.push(curL);
    curL += (i===0? typeW : frozenW);
  });
  const divLeft = curL;

  function groupRows(items, depth){
    if(depth>=nDims) return items.map(r=> ({ key:null, items:[], allRows:[r] }));
    const dim = effDims[depth];
    const groups = {};
    items.forEach(r=>{ const k = r[dim]||'(blank)'; if(!groups[k]) groups[k]=[]; groups[k].push(r); });
    // sort: for Type, use REPORTS order
    const keys = Object.keys(groups);
    if(depth===0){
      keys.sort((a,b)=>{
        const ia = REPORTS.findIndex(t=> REPORT_NAMES[t]===a);
        const ib = REPORTS.findIndex(t=> REPORT_NAMES[t]===b);
        return ia-ib;
      });
    }else{
      keys.sort();
    }
    return keys.map(k=> ({ key:k, items: groupRows(groups[k], depth+1), allRows: groups[k], repKey: groups[k][0]?._REPORT_KEY||'' }));
  }
  const tree = groupRows(rows, 0);
  function sumRows(arr){
    const s={}; columns.forEach(c=>s[c]=0); arr.forEach(r=> columns.forEach(c=> s[c]+=(Number(r[c])||0))); return s;
  }
  const grandTotal = sumRows(rows);

  let h = `<div class="stat-row"><strong>${rows.length}</strong> detail rows merged &nbsp; <strong>${columns.length}</strong> cols &nbsp; Types: ${[...new Set(rows.map(r=>r._REPORT_TYPE))].join(', ')}</div>`;
  h += '<div class="table-wrapper"><table><thead><tr>';
  effDims.forEach((d,i)=>{
    const btn = i < nDims-1 ? `<span class="expand-btn" onclick="window.ioExpandLevel(event,${i})" title="Expand/Collapse all">⊞</span>` : '';
    const left = lefts[i];
    const w = i===0? typeW : frozenW;
    const label = d==='_REPORT_TYPE' ? 'Type' : (DIM_LABELS[d]||d);
    h += `<th class="frozen" style="left:${left}px;min-width:${w}px;z-index:16">${esc(label)} ${btn}</th>`;
  });
  h += `<th class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:16"></th>`;
  columns.forEach(c=>{
    const p=c.split('_');
    h += `<th style="min-width:80px">${esc(p[0])}${p[1]?`<br><small>${esc(p[1])}</small>`:''}</th>`;
  });
  h += '</tr></thead><tbody>';

  let path=[];
  const uidBase = Date.now();
  function renderTree(nodes, depth){
    nodes.forEach((node, idx)=>{
      path[depth]=idx;
      const pid = uidBase+'_'+path.slice(0,depth+1).join('_');
      const rk = node.repKey || node.allRows[0]?._REPORT_KEY || '';
      if(depth===nDims-1){
        const agg = sumRows(node.allRows);
        h += `<tr class="agg-row row-new-group row-${rk}">`;
        for(let d=0; d<nDims; d++){
          const left = lefts[d];
          const val = d<depth ? '' : node.key;
          if(d===0){
            const badge = `<span class="type-badge type-${rk}">${esc(val)}</span>`;
            h += `<td class="frozen" style="left:${left}px;min-width:${typeW}px;z-index:5">${badge}</td>`;
          }else{
            h += `<td class="frozen" style="left:${left}px;min-width:${frozenW}px;z-index:5">${esc(val)}</td>`;
          }
        }
        h += `<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ h+= `<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
        h += '</tr>';
      }else{
        const aggregated = node.items.flatMap(n=> n.allRows || []);
        const agg = sumRows(aggregated);
        const repKey = aggregated[0]?._REPORT_KEY || rk || '';
        h += `<tr class="hierarchy-row agg-row row-new-group row-${repKey}" id="${pid}" data-depth="${depth}" onclick="window.ioToggleDetail('${pid}')">`;
        for(let d=0; d<nDims; d++){
          const left = lefts[d];
          const w = d===0? typeW : frozenW;
          if(d===depth){
            if(d===0){
              h += `<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span class="toggle" id="tog_${pid}">▶</span><span class="type-badge type-${repKey}">${esc(node.key)}</span></td>`;
            }else{
              h += `<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><span class="toggle" id="tog_${pid}">▶</span>${esc(node.key)}</td>`;
            }
          }else if(d===depth+1){
            h += `<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5">${node.items.length} items</td>`;
          }else{
            h += `<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"></td>`;
          }
        }
        h += `<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
        columns.forEach(c=>{ h+= `<td class="num">${Number(agg[c]).toLocaleString()}</td>`; });
        h += '</tr>';
        h += `<tbody id="children_${pid}" data-parent="${pid}" style="display:none">`;
        renderTree(node.items, depth+1);
        h += '</tbody>';
      }
    });
  }
  renderTree(tree,0);

  h += '<tr class="total-row">';
  for(let d=0; d<nDims; d++){
    const left = lefts[d];
    const w = d===0? typeW : frozenW;
    h += d===0 ? `<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"><strong>Total</strong></td>` : `<td class="frozen" style="left:${left}px;min-width:${w}px;z-index:5"></td>`;
  }
  h += `<td class="frozen divider-col" style="left:${divLeft}px;min-width:5px;width:5px;z-index:5"></td>`;
  columns.forEach(c=>{ h+= `<td class="num"><strong>${Number(grandTotal[c]).toLocaleString()}</strong></td>`; });
  h += '</tr></tbody></table></div>';
  return h;
}

window.ioToggleDetail = function(pid){
  const t = document.getElementById('tog_'+pid);
  if(!t) return;
  const open = t.textContent==='▼';
  const children = document.getElementById('children_'+pid);
  if(!children) return;
  const show = !open;
  children.style.display = show ? '' : 'none';
  if(!show){
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
    const pid=row.id;
    const t=document.getElementById('tog_'+pid);
    const children=document.getElementById('children_'+pid);
    if(!t||!children) return;
    if(allExpanded){
      children.style.display='none';
      children.querySelectorAll('[id^="children_"]').forEach(el=> el.style.display='none');
      children.querySelectorAll('[id^="tog_"]').forEach(el=> el.textContent='▶');
      t.textContent='▶';
    }else{
      children.style.display='';
      t.textContent='▼';
    }
  });
};

function downloadExcel(type){
  const data = allData?.[type];
  if(!data || !data.rows || !data.rows.length) return;
  const dim = getDimParam();
  const headers = dim==='detail' ? dimOrder : [dimOrder[0] || 'ITEM_NO'];
  const wsData = [];
  wsData.push([...headers.map(h=> DIM_LABELS[h]||h), ...data.columns]);
  data.rows.forEach(row=>{
    const r=[];
    if(dim==='detail'){ headers.forEach(h=> r.push(row[h]||'')); }
    else{ r.push(row[dimOrder[0]]??''); }
    data.columns.forEach(c=> r.push(row[c]??0));
    wsData.push(r);
  });
  if(window.XLSX){
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.aoa_to_sheet(wsData);
    XLSX.utils.book_append_sheet(wb, ws, type.slice(0,31));
    XLSX.writeFile(wb, `${REPORT_NAMES[type]||type}.xlsx`);
  }
}
window.ioDownloadExcel = downloadExcel;

function downloadMerged(gIdx){
  const groupTypes = reportGroups[gIdx];
  if(!groupTypes || groupTypes.length===0) return;
  const merged = mergeTypesData(groupTypes);
  if(!merged.rows.length) return;
  const dim = getDimParam();
  const isDetail = dim==='detail' && dimOrder.length>=2;
  let headers;
  if(isDetail){
    headers = ['Type', ...dimOrder.map(d=> DIM_LABELS[d]||d)];
  }else{
    headers = ['Type', DIM_LABELS[dim]||dim];
  }
  const wsData = [];
  wsData.push([...headers, ...merged.columns]);
  const sorted = [...merged.rows].sort((a,b)=>{
    if(a._REPORT_KEY < b._REPORT_KEY) return -1;
    if(a._REPORT_KEY > b._REPORT_KEY) return 1;
    return 0;
  });
  sorted.forEach(row=>{
    const r=[];
    r.push(row._REPORT_TYPE||'');
    if(isDetail){
      dimOrder.forEach(d=> r.push(row[d]||''));
    }else{
      r.push(row[dim]??'');
    }
    merged.columns.forEach(c=> r.push(row[c]??0));
    wsData.push(r);
  });
  if(window.XLSX){
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.aoa_to_sheet(wsData);
    const name = groupTypes.map(t=> REPORT_NAMES[t]).join('_').slice(0,31);
    XLSX.utils.book_append_sheet(wb, ws, name);
    XLSX.writeFile(wb, `${name}.xlsx`);
  }
}
window.ioDownloadMerged = downloadMerged;

function downloadAll(){
  if(!allData) return;
  if(!window.XLSX){ alert('XLSX library not loaded'); return; }
  const wb = XLSX.utils.book_new();
  reportGroups.forEach((groupTypes,gIdx)=>{
    const merged = mergeTypesData(groupTypes);
    if(!merged.rows.length) return;
    const dim = getDimParam();
    const isDetail = dim==='detail' && dimOrder.length>=2;
    let headers = isDetail ? ['Type', ...dimOrder.map(d=> DIM_LABELS[d]||d)] : ['Type', DIM_LABELS[dim]||dim];
    const wsData = [];
    wsData.push([...headers, ...merged.columns]);
    merged.rows.forEach(row=>{
      const r=[row._REPORT_TYPE||''];
      if(isDetail){ dimOrder.forEach(d=> r.push(row[d]||'')); } else { r.push(row[dim]??''); }
      merged.columns.forEach(c=> r.push(row[c]??0));
      wsData.push(r);
    });
    const ws = XLSX.utils.aoa_to_sheet(wsData);
    const name = groupTypes.map(t=> REPORT_NAMES[t]).join('+').slice(0,31) || `Group${gIdx+1}`;
    XLSX.utils.book_append_sheet(wb, ws, name);
  });
  XLSX.writeFile(wb, `IO_Report_${currentGroup}_${COL_DIM}.xlsx`);
}
window.ioDownloadAll = downloadAll;

// Init
document.addEventListener('DOMContentLoaded', ()=>{
  const active = document.querySelector('.nav-item.active');
  if(active && active.dataset.module==='io-report'){ render(); }
});
document.addEventListener('module-change', (e)=>{ if(e.detail.module==='io-report'){ render(); } });

})();
