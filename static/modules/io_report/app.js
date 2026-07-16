/**
 * I/O Report - 9 Tables (INPUT/OUTPUT/CHECKIN/CHECKOUT daily/cum + BOH)
 * Vertical tabs (stacked), upload module persistent, Day default, divider + thick lines
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
const REPORT_LABELS_FULL = {
  daily_input: 'Daily Input (Checkin type INPUT)',
  daily_output: 'Daily Output',
  daily_checkin: 'Daily Checkin',
  daily_checkout: 'Daily Checkout',
  cum_input: 'Cum Input',
  cum_output: 'Cum Output',
  cum_checkin: 'Cum Checkin',
  cum_checkout: 'Cum Checkout',
  balance: 'BOH (Balance on Hand)'
};

let dimOrder = [];
let currentGroup = 'FG';
let allData = null;
let COL_DIM = 'day';
let dragFromDim = null;
const filterVals = { lineCode: '', itemNo: '', style: '' };
let ioRoot = null;

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

// ---------- Upload HTML builder (plan_merge style) ----------
function buildUploadSectionHTML(isCompact){
  // isCompact = true for reports page top bar, false for full upload page
  const title = isCompact ? '📁 Upload I/O Data (Re-upload to update)' : '📁 Upload I/O Data (3 files required)';
  const wrapperClass = isCompact ? 'section' : 'section';
  const gridStyle = isCompact ? 'display:grid;grid-template-columns:repeat(3,1fr) 1.2fr;gap:10px;align-items:end' : 'display:grid;grid-template-columns:repeat(3,1fr);gap:12px';
  return `
    <div class="${wrapperClass}" id="${isCompact ? 'io-upload-bar' : 'io-upload-section'}">
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
        Place 3 files in <code>data/</code> and click Recheck, or upload below. Supports 4 plan types → 8 report tabs + BOH = 9 tables.
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
            <div class="upload-hint">排产结果表.xlsx<br>LINE, SHIFT, PLAN_ITEM (INPUT/OUTPUT/CHECKIN/CHECKOUT), SKU, DATE, VALUE</div>
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
          ${isCompact ? '<span style="font-size:10px;color:#94a3b8">Supports re-upload while viewing reports</span>' : ''}
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
        let matched=0;
        for(const f of folderInput.files){
          const lower = f.name.toLowerCase();
          if(lower.includes('master') || f.name.includes('料号')){
            files.master=f; document.getElementById('fname_master_full').textContent='✓ '+f.name; markHasFile('card_master_full',true); matched++;
          }else if(lower.includes('schedule') || lower.includes('result') || f.name.includes('排产')){
            files.schedule=f; document.getElementById('fname_schedule_full').textContent='✓ '+f.name; markHasFile('card_schedule_full',true); matched++;
          }else if(lower.includes('balance') || lower.includes('boh') || f.name.includes('结存')){
            files.balance=f; document.getElementById('fname_balance_full').textContent='✓ '+f.name; markHasFile('card_balance_full',true); matched++;
          }
        }
        // fallback: if names not matched but 3 xlsx files, assign by order
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

// ---------- Full upload page (no data) ----------
function renderUploadPage(){
  ioRoot.innerHTML = buildUploadSectionHTML(false) + '<div id="io-schema-box" style="display:none;margin:12px 24px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px"></div>';
  attachUploadLogic(false);

  window.showSchema = async (key)=>{
    const box = document.getElementById('io-schema-box');
    if(!box) return;
    box.style.display='block';
    box.innerHTML = 'Loading schema...';
    try{
      const resp = await fetch('/api/io/templates/schema');
      const data = await resp.json();
      const sc = data[key];
      if(!sc){ box.innerHTML='No schema'; return; }
      let html = `<div style="display:flex;justify-content:space-between"><strong>${esc(sc.file)}</strong><button onclick="this.parentElement.parentElement.style.display='none'" style="border:none;background:none;cursor:pointer">✕</button></div>`;
      html += '<table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:12px"><tr><th style="text-align:left;border-bottom:1px solid #e2e8f0;padding:4px">Field</th><th style="text-align:left;border-bottom:1px solid #e2e8f0;padding:4px">Type</th><th style="text-align:left;border-bottom:1px solid #e2e8f0;padding:4px">Description</th><th style="text-align:left;border-bottom:1px solid #e2e8f0;padding:4px">Example</th></tr>';
      for(const [f,t,d,e] of sc.fields){
        html += `<tr><td style="padding:4px;border-bottom:1px solid #f1f5f9"><code>${esc(f)}</code></td><td style="padding:4px;border-bottom:1px solid #f1f5f9">${esc(t)}</td><td style="padding:4px;border-bottom:1px solid #f1f5f9">${esc(d)}</td><td style="padding:4px;border-bottom:1px solid #f1f5f9">${esc(e)}</td></tr>`;
      }
      html += '</table>';
      if(sc.note) html += `<div style="margin-top:8px;padding:8px;background:#f8fafc;border-radius:4px;font-size:11px;color:#64748b">💡 ${esc(sc.note)}</div>`;
      box.innerHTML = html;
    }catch(e){ box.innerHTML='❌ '+e.message; }
  };
}

// ---------- Reports Page - 9 tables stacked with vertical tabs ----------
function renderReportsPage(){
  // Build upload bar + main
  ioRoot.innerHTML = buildUploadSectionHTML(true) + `
    <div class="section" id="io-main-section">
      <div class="section-header">
        <span class="section-title">📈 I/O Report - 9 Tables (Input/Output/Checkin/Checkout + BOH)</span>
        <div class="section-actions">
          <span id="io-report-status" style="font-size:12px;color:#059669"></span>
          <button id="io-dl-all" class="btn btn-sm btn-outline">📥 Download All (Excel)</button>
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
            <div style="font-size:10px;color:#94a3b8;margin-top:4px">Drag to order. 1 dim = flat, 2+ = expandable groups. Fixed vertical divider before dates.</div>
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

      <div class="container-fluid" style="padding:0;margin-top:12px">
        <div class="row" style="display:flex;gap:12px">
          <div class="col-1" style="flex:0 0 160px;max-width:160px">
            <div class="io-sidebar" style="position:sticky;top:70px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:8px">
              <div style="font-size:11px;font-weight:600;color:#475569;margin-bottom:8px;text-transform:uppercase">Report Tabs (9)</div>
              ${REPORTS.map((r,i)=> `<a class="anchor" href="#io_sec_${r}" data-jump="${r}" style="display:block;padding:6px 8px;border-radius:4px;font-size:12px;color:#334155;text-decoration:none;margin-bottom:2px;cursor:pointer">${i+1}. ${esc(REPORT_NAMES[r])}</a>`).join('')}
              <div style="margin-top:12px;border-top:1px solid #e2e8f0;padding-top:8px;font-size:10px;color:#94a3b8">Click to jump. All 9 tables load together.</div>
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
    <div id="io-schema-box-compact" style="display:none;margin:12px 24px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px"></div>
  `;

  attachUploadLogic(true);
  initReportsPage();
  // jump anchors
  document.querySelectorAll('.io-sidebar .anchor').forEach(a=>{
    a.addEventListener('click', (e)=>{
      e.preventDefault();
      const id = a.getAttribute('href').slice(1);
      document.getElementById(id)?.scrollIntoView({behavior:'smooth', block:'start'});
      // highlight
      document.querySelectorAll('.io-sidebar .anchor').forEach(x=> x.style.background='');
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

// ---------- Reports core ----------
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
  initDragDrop();
  refreshMeta().then(()=> loadAllReports());

  const rb = document.getElementById('ioRefreshBtn');
  if(rb) rb.addEventListener('click', loadAllReports);
  const dlAll = document.getElementById('io-dl-all');
  if(dlAll) dlAll.addEventListener('click', downloadAll);
}

function initDragDrop(){
  document.querySelectorAll('#io-report-section .dim-chip.available').forEach(chip=>{
    chip.addEventListener('dragstart', e=>{
      e.dataTransfer.setData('text/plain', chip.dataset.dim);
      chip.classList.add('dragging');
    });
    chip.addEventListener('dragend', e=> chip.classList.remove('dragging'));
  });
  const well = document.getElementById('ioDimWell');
  if(well){
    well.addEventListener('dragover', onDragOver);
    well.addEventListener('drop', onDrop);
    well.addEventListener('dragleave', ()=> well.classList.remove('drag-over'));
  }
}
function onDragOver(e){ e.preventDefault(); const w=document.getElementById('ioDimWell'); if(w) w.classList.add('drag-over'); }
document.addEventListener('dragend', ()=>{ const w=document.getElementById('ioDimWell'); if(w) w.classList.remove('drag-over'); dragFromDim=null; });
function onDrop(e){
  e.preventDefault();
  const w=document.getElementById('ioDimWell'); if(w) w.classList.remove('drag-over');
  const dim = e.dataTransfer.getData('text/plain');
  if(!dim) return;
  if(dragFromDim){
    const fromIdx = dimOrder.indexOf(dragFromDim);
    if(fromIdx<0) return;
    dimOrder.splice(fromIdx,1);
    const target = e.target.closest('.dim-chip.in-well');
    if(target){
      const toDim = target.dataset.dim;
      const toIdx = dimOrder.indexOf(toDim);
      if(toIdx>=0){ dimOrder.splice(toIdx,0,dim); }else{ dimOrder.push(dim); }
    }else{ dimOrder.push(dim); }
    dragFromDim=null;
    renderDimWell();
  }else if(!dimOrder.includes(dim)){
    dimOrder.push(dim);
    renderDimWell();
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
function onWellChipDragStart(e,dim){ e.dataTransfer.setData('text/plain', dim); dragFromDim = dim; }
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
  if(content) content.innerHTML = '<div style="text-align:center;padding:24px;color:#64748b">⏳ Loading 9 tables...</div>';
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
function renderAllReports(){
  const content = document.getElementById('ioReportContent');
  if(!content) return;
  if(!allData){ content.innerHTML = '<div style="text-align:center;padding:24px;color:#94a3b8">No data</div>'; return; }

  let html = '';
  REPORTS.forEach(rtype=>{
    const data = allData[rtype];
    const title = REPORT_NAMES[rtype] || rtype;
    const fullTitle = REPORT_LABELS_FULL[rtype] || title;
    html += `<div class="report-section" id="io_sec_${rtype}" style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:16px">`;
    html += `<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #3b82f6;padding-bottom:6px;margin-bottom:8px"><h6 style="margin:0;font-size:13px;font-weight:700">${esc(fullTitle)}</h6><div style="display:flex;gap:8px;align-items:center"><span style="font-size:11px;color:#64748b">${data ? data.rows.length : 0} rows × ${data ? data.columns.length : 0} cols</span><button class="btn btn-sm btn-outline" onclick="window.ioDownloadExcel('${rtype}')">📥 Excel</button></div></div>`;
    if(!data || !data.rows || data.rows.length===0){
      html += '<div style="text-align:center;padding:20px;color:#94a3b8">No data for current filters</div>';
    }else{
      const dimParam = getDimParam();
      if(dimParam==='detail' && dimOrder.length>=2){
        html += buildHierarchicalTable(data, dimOrder);
      }else{
        html += buildFlatTable(data, dimOrder[0] || 'ITEM_NO');
      }
    }
    html += '</div>';
  });
  content.innerHTML = html;
}

// ---------- Tables with divider + thick lines ----------
function buildFlatTable(data, dim){
  const { columns, rows } = data;
  const dimLabel = DIM_LABELS[dim] || dim;
  const frozenW = 120;
  const dividerLeft = frozenW;
  const lastCol = columns[columns.length-1];
  let total=0, nz=0;
  rows.forEach(r=>{ const v=r[lastCol]||0; total+=v; if(v>0) nz++; });

  let html = `<div class="stat-row"><strong>${rows.length}</strong> rows &nbsp; <strong>${columns.length}</strong> cols &nbsp; Last col total: <strong>${total.toLocaleString()}</strong> &nbsp; Non-zero: <strong>${nz}</strong></div>`;
  html += '<div class="table-wrapper"><table><thead><tr>';
  html += `<th class="frozen" style="left:0;min-width:${frozenW}px;z-index:16">${esc(dimLabel)}</th>`;
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
    const rowCls = isNewGroup ? 'row-new-group' : '';
    html += `<tr class="${rowCls}">`;
    html += `<td class="frozen" style="left:0;min-width:${frozenW}px;z-index:5;font-weight:500;background:#fff">${esc(String(r[dim]??''))}</td>`;
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

function buildHierarchicalTable(data, dimOrder){
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
      const isNewGroup = true; // each group gets thick line

      if(depth===nDims-1){
        const agg = sumRows(node.allRows);
        h += `<tr class="agg-row row-new-group">`;
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
        h += `<tr class="hierarchy-row agg-row row-new-group" id="${pid}" data-depth="${depth}" onclick="window.ioToggleDetail('${pid}')">`;
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
  }else{
    let csv = '\uFEFF' + wsData[0].join(',') + '\n';
    wsData.slice(1).forEach(r=>{ csv += r.map(v=> `"${String(v).replace(/"/g,'""')}"`).join(',') + '\n'; });
    const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=`${type}.csv`; a.click(); URL.revokeObjectURL(a.href);
  }
}
window.ioDownloadExcel = downloadExcel;

function downloadAll(){
  if(!allData) return;
  if(!window.XLSX){ alert('XLSX library not loaded'); return; }
  const wb = XLSX.utils.book_new();
  REPORTS.forEach(rtype=>{
    const data = allData[rtype];
    if(!data || !data.rows.length) return;
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
    const ws = XLSX.utils.aoa_to_sheet(wsData);
    XLSX.utils.book_append_sheet(wb, ws, rtype.slice(0,31));
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
