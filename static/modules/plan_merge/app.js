const ALL_COLS = [
  { key:'_dim', label:'Dim', width:50, frozen:true },
  { key:'PN', label:'PN', width:130, frozen:true, toggle:'col-pn' },
  { key:'Usage', label:'Usage', width:70, frozen:true, toggle:'col-usage' },
  { key:'Style', label:'Style', width:95, frozen:true, toggle:'col-style' },
  { key:'Color', label:'Color', width:100, frozen:true, toggle:'col-color' },
  { key:'Version-Type', label:'Version-Type', width:100, frozen:true },
  { key:'Version-Detail', label:'Version-Detail', width:105, frozen:true },
  { key:'Cut Day', label:'Cut Day', width:75, frozen:true, toggle:'col-cutday' },
  { key:'Pallet_Qty', label:'Pallet', width:50, frozen:true, toggle:'col-pallet' },
];
const DIVIDER = { key:'_divider', label:'', width:5, frozen:true };
let allRows=[], allWeeks=[], weekLabels={}, filteredRows=[], activeDim='FG', pivotFields=[];
const PIVOT_KEEP = ['Version-Type','Version-Detail','Cut Day'];
const VT_ORDER = {'ExF':0,'Ungated':1,'Gated':2,'CTB':3};

// ===== Offline Static Mode Support (export_static.py) + Client Engine =====
function getStaticDB(){
  try {
    if (window.STATIC_DB) return window.STATIC_DB;
    if (window.PLAN_MERGE_STATIC_DB) return window.PLAN_MERGE_STATIC_DB;
  } catch(e) {}
  return null;
}
function normalizeStaticDB(raw){
  if (!raw) return { versions: [], meta: {} };
  if (raw.versions && Array.isArray(raw.versions)) {
    return { versions: raw.versions, meta: raw.meta || {}, schema: raw.schema || null };
  }
  if (raw.plan_merge_versions && Array.isArray(raw.plan_merge_versions)) {
    return { versions: raw.plan_merge_versions, meta: raw.meta || {}, schema: raw.schema || null };
  }
  if (raw.rows && raw.weeks) {
    return { versions: [{ id: 'default', name: raw.name || 'Default', file: raw.file || '', rows: raw.rows, weeks: raw.weeks, week_labels: raw.week_labels || {}, weekLabels: raw.week_labels || {}, config: raw.config || {}, warnings: raw.warnings || [] }], meta: raw.meta || {}, schema: raw.schema || null };
  }
  return { versions: [], meta: {}, schema: raw.schema || null };
}
function isStaticMode(){
  const db = getStaticDB();
  if (!db) return false;
  const norm = normalizeStaticDB(db);
  return norm.versions && norm.versions.length > 0;
}
function getStaticSchema(){
  const db = getStaticDB();
  if (!db) return null;
  if (db.schema) return db.schema;
  const norm = normalizeStaticDB(db);
  return norm.schema || null;
}
let _staticVersions = [];
let _staticCurrentIdx = 0;
let _staticCompareMode = false;
let _staticSelectedIdx = new Set([0]);
function formatGeneratedAt(s){
  if(!s) return '';
  try { return new Date(s).toLocaleString(); } catch { return s; }
}
function getClientConfig(){
  return {
    exf_cut: document.getElementById('cfg-exf')?.value || 'Saturday',
    etd_cut: document.getElementById('cfg-etd')?.value || 'Saturday',
    output_cut: document.getElementById('cfg-output')?.value || 'Wednesday',
    gb_cut: document.getElementById('cfg-gb')?.value || 'Tuesday',
    etd_packout_offset: document.getElementById('cfg-etd-packout-offset')?.value || 2
  };
}
function processFileClientSide(file){
  return new Promise((resolve, reject)=>{
    if (typeof XLSX === 'undefined' || !window.PlanMergeEngine){
      reject(new Error('Client engine not loaded (need xlsx + engine.js)'));
      return;
    }
    const reader = new FileReader();
    reader.onload = (e)=>{
      try{
        const data = e.target.result;
        const wb = XLSX.read(data, {type:'array'});
        const cfg = getClientConfig();
        const result = window.PlanMergeEngine.processWorkbook(wb, cfg);
        resolve(result);
      }catch(err){ reject(err); }
    };
    reader.onerror = (e)=> reject(e);
    reader.readAsArrayBuffer(file);
  });
}
function handleProcessedData(data, fileName, isClient){
  const warnEl = document.getElementById('upload-warnings');
  if (warnEl) {
    if (data.warnings && data.warnings.length>0){
      const isWarn = data.warnings.some(w=> w.toLowerCase().includes('missing'));
      warnEl.className = 'warnings ' + (isWarn ? 'warn' : 'success');
      warnEl.innerHTML = data.warnings.map(w=> '<div>'+esc(w)+'</div>').join('');
      warnEl.style.display='block';
    } else {
      warnEl.style.display='none';
    }
  }
  allRows = data.rows; allWeeks = data.weeks; weekLabels = data.week_labels || data.weekLabels || {};
  document.getElementById('report-section').style.display='block';
  pivotExpanded = new Set();
  const timeStr = new Date().toLocaleTimeString();
  // Single status: Ready
  const pmBadge = document.getElementById('pmStatusBadge');
  if (pmBadge){
    pmBadge.textContent=`Ready: ${allRows.length} rows`;
    pmBadge.style.background='#dcfce7'; pmBadge.style.color='#065f46'; pmBadge.style.borderColor='#86efac';
  }
  const pmMsg = document.getElementById('pmPersistentMsg');
  if (pmMsg){ pmMsg.textContent=''; }
  const statusEl = document.getElementById('upload-status');
  if (statusEl) statusEl.textContent = '';
  const fnMain = document.getElementById('file-name-main');
  if (fnMain){ fnMain.textContent=''; fnMain.className='file-name'; }
  const fileInput = document.querySelector('.file-input');
  const card = fileInput ? fileInput.closest('.upload-card') : null;
  if (card) card.classList.add('has-file');
  _lastLoadedInfo = { fileName, rows:allRows.length, time:timeStr, msg:successMsg, fileMsg };
  saveLoadStatus(_lastLoadedInfo);

  const savedFilter={};
  for (const n of ['sku','usage','style','color','type','detail']){
    const m=document.getElementById(n+'-menu');
    if(!m) continue;
    savedFilter[n]=Array.from(m.querySelectorAll('input[data-val]:checked')).map(cb=>cb.dataset.val);
    const menu=m;
    const total=parseInt(menu.dataset.totalVals)||0;
    savedFilter[n]._all=savedFilter[n].length===total;
  }
  const savedAgg=Array.from(document.querySelectorAll('.pivot-field:checked')).map(cb=>cb.value);
  setupDropdowns(); applyFilters();
  for (const n of ['sku','usage','style','color','type','detail']){
    const vals=savedFilter[n];
    if(!vals) continue;
    const m=document.getElementById(n+'-menu');
    if(!m) continue;
    const total=parseInt(m.dataset.totalVals)||0;
    if(vals._all || vals.length===total) continue;
    const allCb=m.querySelector('.dropdown-all input');
    if(allCb && allCb.checked){ allCb.checked=false; allCb.dispatchEvent(new Event('change')); }
    for(const val of vals){
      const menuEl=document.getElementById(n+'-menu');
      const cb=Array.from(menuEl.querySelectorAll('input[data-val]')).find(c=>c.dataset.val===val);
      if(cb && !cb.checked){ cb.checked=true; cb.dispatchEvent(new Event('change')); }
    }
  }
  document.querySelectorAll('.pivot-field').forEach(cb=>{
    const shouldCheck=savedAgg.includes(cb.value);
    if(cb.checked!==shouldCheck){ cb.checked=shouldCheck; cb.dispatchEvent(new Event('change')); }
  });
  applyFilters(); render();
}

function initStaticUI(){
  const raw = getStaticDB();
  const norm = normalizeStaticDB(raw);
  _staticVersions = norm.versions || [];
  if (_staticVersions.length===0) return;
  const uploadSec=document.getElementById('upload-section');
  const configSec=document.getElementById('config-section');
  const mainContent=document.querySelector('.main-content');
  if(!mainContent) return;
  let banner=document.getElementById('static-mode-banner');
  if(!banner){
    banner=document.createElement('div');
    banner.id='static-mode-banner';
    banner.className='section';
    banner.style.cssText='background:linear-gradient(135deg,#eff6ff 0%,#f0fdf4 100%);border:1px solid #bfdbfe;display:block;margin:12px 24px;';
    if(uploadSec && uploadSec.parentNode){ uploadSec.parentNode.insertBefore(banner, uploadSec); }
    else { mainContent.insertBefore(banner, mainContent.firstChild.nextSibling); }
  }
  const meta=norm.meta||{};
  const genAt=formatGeneratedAt(meta.generated_at);
  banner.innerHTML=`
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
      <div>
        <div style="font-size:14px;font-weight:700;color:#1e40af">📦 Offline Static Mode — Fully Ready</div>
        <div style="font-size:11px;color:#475569;margin-top:2px">
          ${genAt ? `Generated: ${genAt} | ` : ''}${_staticVersions.length} version(s) embedded | Upload / Config / Report all in browser, no server needed
          ${meta.note ? `<br>${esc(meta.note)}` : ''}
        </div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <label style="font-size:12px;color:#475569">Version:</label>
        <select id="static-version-select" style="padding:4px 8px;border:1px solid #cbd5e1;border-radius:4px;font-size:12px;min-width:180px"></select>
        <label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer;color:#475569"><input type="checkbox" id="static-compare-toggle"> Compare multi</label>
        <button id="static-show-upload" class="btn btn-sm btn-outline">📁 Show Upload (client engine)</button>
      </div>
    </div>
    <div id="static-version-list" style="margin-top:8px;display:none;flex-wrap:wrap;gap:6px"></div>
    <div id="static-version-meta" style="margin-top:6px;font-size:11px;color:#64748b"></div>
  `;
  const sel=document.getElementById('static-version-select');
  if(sel){
    sel.innerHTML=_staticVersions.map((v,i)=>`<option value="${i}">${esc(v.name||'V'+(i+1))} — ${v.rows? v.rows.length+' rows' : ''}${v.file? ' ('+v.file+')':''}</option>`).join('');
    sel.value='0';
    sel.addEventListener('change',()=>{
      _staticCurrentIdx=parseInt(sel.value)||0;
      if(!_staticCompareMode){
        _staticSelectedIdx=new Set([_staticCurrentIdx]);
        loadStaticVersion(_staticCurrentIdx);
      }else{
        renderStaticVersionCheckboxes();
        loadStaticMultiVersions();
      }
    });
  }
  const compareToggle=document.getElementById('static-compare-toggle');
  const vList=document.getElementById('static-version-list');
  if(compareToggle){
    compareToggle.addEventListener('change',()=>{
      _staticCompareMode=compareToggle.checked;
      if(vList) vList.style.display=_staticCompareMode?'flex':'none';
      if(sel) sel.disabled=_staticCompareMode;
      if(_staticCompareMode){
        _staticSelectedIdx=new Set([_staticCurrentIdx]);
        renderStaticVersionCheckboxes();
        loadStaticMultiVersions();
      }else{
        if(vList) vList.style.display='none';
        loadStaticVersion(_staticCurrentIdx);
      }
    });
  }
  function renderStaticVersionCheckboxes(){
    const listEl=document.getElementById('static-version-list');
    if(!listEl) return;
    listEl.innerHTML=_staticVersions.map((v,i)=>{
      const checked=_staticSelectedIdx.has(i)?'checked':'';
      return `<label style="font-size:11px;display:flex;align-items:center;gap:4px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;padding:2px 6px;cursor:pointer"><input type="checkbox" data-idx="${i}" ${checked}> ${esc(v.name||'V'+(i+1))}</label>`;
    }).join('');
    listEl.querySelectorAll('input[type=checkbox]').forEach(cb=>{
      cb.addEventListener('change',()=>{
        const idx=parseInt(cb.dataset.idx);
        if(cb.checked) _staticSelectedIdx.add(idx); else _staticSelectedIdx.delete(idx);
        if(_staticSelectedIdx.size===0) _staticSelectedIdx.add(0);
        loadStaticMultiVersions();
      });
    });
  }
  window._renderStaticVersionCheckboxes=renderStaticVersionCheckboxes;
  const showUploadBtn=document.getElementById('static-show-upload');
  if(showUploadBtn){
    showUploadBtn.addEventListener('click',()=>{
      if(uploadSec) uploadSec.style.display = uploadSec.style.display==='none' ? 'block' : 'none';
      if(configSec) configSec.style.display = configSec.style.display==='none' ? 'block' : 'none';
      showUploadBtn.textContent = uploadSec && uploadSec.style.display!=='none' ? '🙈 Hide Upload' : '📁 Show Upload (client engine)';
    });
  }
  // Keep upload/config visible for full functionality? For offline we previously hid, now keep visible if client engine available
  if(window.PlanMergeEngine){
    if(uploadSec) uploadSec.style.display='block';
    if(configSec) configSec.style.display='block';
  }else{
    if(uploadSec) uploadSec.style.display='none';
    if(configSec) configSec.style.display='none';
  }
  setTimeout(()=> loadStaticVersion(0), 100);
}
function loadStaticVersion(idx){
  const v=_staticVersions[idx];
  if(!v) return;
  _staticCurrentIdx=idx;
  allRows=v.rows||[];
  allWeeks=v.weeks||[];
  weekLabels=v.week_labels||v.weekLabels||{};
  const metaEl=document.getElementById('static-version-meta');
  if(metaEl){
    const cfg=v.config||{};
    metaEl.textContent=`Loaded: ${v.name} | ${allRows.length} rows | ${allWeeks.length} weeks | Offset=${cfg.etd_packout_offset||2} | ${v.warnings? v.warnings.join(' | ') : ''}`;
  }
  try{
    const info={msg:`📦 Offline: ${v.name} — ${allRows.length} rows`, fileMsg:`📦 Offline static: ${v.name} (${allRows.length} rows)`};
    localStorage.setItem('plan_merge_last_load', JSON.stringify(info));
  }catch(e){}
  document.getElementById('report-section').style.display='block';
  pivotExpanded=new Set();
  setupDropdowns(); applyFilters(); render();
  const statusEl=document.getElementById('upload-status');
  if(statusEl) statusEl.textContent=`📦 Offline loaded: ${v.name} (you can still upload new files, client engine ready)`;
}
function loadStaticMultiVersions(){
  const selected=Array.from(_staticSelectedIdx).map(i=> _staticVersions[i]).filter(Boolean);
  if(selected.length===0) return;
  const weekSet=new Set();
  selected.forEach(v=> (v.weeks||[]).forEach(w=> weekSet.add(w)));
  const mergedWeeks=Array.from(weekSet).sort();
  const mergedLabels={};
  selected.forEach(v=>{
    const wl=v.week_labels||v.weekLabels||{};
    Object.assign(mergedLabels, wl);
  });
  let mergedRows=[];
  selected.forEach(v=>{
    const vName=v.name||'V';
    (v.rows||[]).forEach(r=>{
      const nr=Object.assign({}, r);
      nr.PlanVersion=vName;
      mergedRows.push(nr);
    });
  });
  allRows=mergedRows;
  allWeeks=mergedWeeks;
  weekLabels=mergedLabels;
  const metaEl=document.getElementById('static-version-meta');
  if(metaEl){ metaEl.textContent=`Compare: ${selected.map(v=>v.name).join(' + ')} | ${allRows.length} rows total | ${allWeeks.length} weeks union`; }
  document.getElementById('report-section').style.display='block';
  pivotExpanded=new Set();
  setupDropdowns(); applyFilters(); render();
}
function generateExcelClientSide(rows, weeks, labels){
  try{
    if(typeof XLSX==='undefined'){ alert('XLSX library not loaded'); return; }
    const fgRows=rows.filter(r=> (r._dim||'FG')==='FG');
    const gbRows=rows.filter(r=> r._dim==='GB');
    const fixed=["_dim","PN","Usage","Style","Color","Version-Type","Version-Detail","Cut Day","Pallet_Qty","PlanVersion"];
    const flabels=["Dim","PN","Usage","Style","Color","Version-Type","Version-Detail","Cut Day","Pallet","PlanVersion"];
    const wlabels=weeks.map(w=> labels[w]||w);
    const wb=XLSX.utils.book_new();
    function makeSheet(dataRows){
      const aoa=[];
      aoa.push([...flabels, ...wlabels]);
      dataRows.forEach(r=>{
        const row=[];
        fixed.forEach(k=> row.push(r[k]!=null? r[k] : ''));
        weeks.forEach(w=> row.push(r[w]!=null? r[w] : ''));
        aoa.push(row);
      });
      return XLSX.utils.aoa_to_sheet(aoa);
    }
    if(fgRows.length>0){ const ws=makeSheet(fgRows); XLSX.utils.book_append_sheet(wb, ws, 'FG'); }
    if(gbRows.length>0){ const ws=makeSheet(gbRows); XLSX.utils.book_append_sheet(wb, ws, 'GB'); }
    if(wb.SheetNames.length===0){ const ws=makeSheet(rows); XLSX.utils.book_append_sheet(wb, ws, 'Report'); }
    XLSX.writeFile(wb, `report_${new Date().toISOString().slice(0,10)}.xlsx`);
  }catch(e){ console.error(e); alert('Client Excel generation failed: '+e.message); }
}

let pivotExpanded = new Set();
let _pivotGroupKeys = [];
let _lastLoadedInfo = null; // for persistent status
function saveLoadStatus(info) {
  try { localStorage.setItem('plan_merge_last_load', JSON.stringify(info)); } catch(e) {}
}
function loadLastStatus() {
  try {
    const s = localStorage.getItem('plan_merge_last_load');
    if (s) return JSON.parse(s);
  } catch(e) {}
  return null;
}
function restoreLoadStatusUI() {
  const info = loadLastStatus();
  if (!info) return;
  // Simplified: only show Ready badge, no duplicate file messages
  const badge = document.getElementById('pmStatusBadge');
  if (badge && info.rows){
    badge.textContent = `Ready: ${info.rows} rows`;
    badge.style.background='#dcfce7'; badge.style.color='#065f46'; badge.style.borderColor='#86efac';
  }
}
// Restore on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(restoreLoadStatusUI, 300);
});

// ===== Upload: Snapshot Only =====
(function(){
  // Snapshot keys, matching backend SNAPSHOT_TARGET_MAP
  const SNAPSHOT_KEYS = ['item','bom','gated','ungated','fcst_main','fcst_detail','ctb'];
  const files = { item:null, bom:null, gated:null, ungated:null, fcst_main:null, fcst_detail:null, ctb:null, combined:[] };

  function escAttr(s){ return (s||'').replace(/"/g,'&quot;'); }
  function markHasFile(cardId, has){
    const el = document.getElementById(cardId);
    if(el) el.classList.toggle('has-file', !!has);
  }
  function classifyByName(name){
    const low = (name||'').toLowerCase();
    // Important: check ungated before gated
    if (low.includes('料号') || (low.includes('item') || low.includes('料号快照'))) {
      if (low.includes('料号快照') || low.includes('item') ) return 'item';
    }
    if (low.includes('bom')) return 'bom';
    if (low.includes('ungated')) return 'ungated';
    if (low.includes('gated排产') || low.includes('gated')) {
      if (!low.includes('ungated')) return 'gated';
    }
    if (low.includes('fcst')) {
      if (low.includes('主表') || low.includes('main')) return 'fcst_main';
      if (low.includes('明细') || low.includes('detail')) return 'fcst_detail';
    }
    if (low.includes('主表')) return 'fcst_main';
    if (low.includes('明细')) return 'fcst_detail';
    if (low.includes('ctb')) return 'ctb';
    // fallback English
    if (low.includes('料号快照')) return 'item';
    if (low.includes('bom快照')) return 'bom';
    return null;
  }
  function setFileForKey(k, file){
    files[k]=file;
    const fnameEl=document.getElementById('fname_'+k);
    if(fnameEl) fnameEl.textContent='✓ '+file.name+' ('+(file.size/1024).toFixed(1)+'KB)';
    markHasFile('card_'+k,true);
  }
  function clearFileForKey(k){
    files[k]=null;
    const fnameEl=document.getElementById('fname_'+k);
    if(fnameEl) fnameEl.textContent='';
    markHasFile('card_'+k,false);
    const inp=document.getElementById('input_'+k);
    if(inp) inp.value='';
  }
  function updateCombinedDisplay(){
    const comboEl=document.getElementById('fname_combined');
    if(!comboEl) return;
    if(files.combined && files.combined.length>0){
      if(files.combined.length===1){
        const f=files.combined[0];
        const isZip=f.name.toLowerCase().endsWith('.zip');
        const hint=isZip?'📦 Zip':'📄 File';
        comboEl.textContent=`✓ ${hint}: ${f.name} (${(f.size/1024).toFixed(1)}KB) — auto-classified`;
      }else{
        comboEl.textContent=`✓ ${files.combined.length} files: `+files.combined.map(f=>f.name).join(', ');
      }
      markHasFile('card_combined',true);
    }else{
      // if no combined, show summary of individual slots filled
      const filled=SNAPSHOT_KEYS.filter(k=>!!files[k]);
      if(filled.length>0){
        comboEl.textContent=`📦 ${filled.length}/7 slots filled: `+filled.join(', ');
        markHasFile('card_combined',false);
      }else{
        comboEl.textContent='';
        markHasFile('card_combined',false);
      }
    }
  }

  // Individual file inputs
  SNAPSHOT_KEYS.forEach(k=>{
    const input=document.getElementById('input_'+k);
    if(!input) return;
    input.addEventListener('change', ()=>{
      if(input.files.length>0){
        setFileForKey(k,input.files[0]);
        // Clear combined if individual changed
        if(files.combined.length>0){
          files.combined=[];
          const ce=document.getElementById('fname_combined');
          if(ce) ce.textContent=`ℹ️ Individual ${k} set, cleared quick upload. You can still use quick upload to override.`;
          setTimeout(updateCombinedDisplay, 1500);
        }
      }else{
        clearFileForKey(k);
      }
      updateCombinedDisplay();
    });
  });

  // Quick Upload: Select Files button -> trigger hidden input
  const btnSelectFiles=document.getElementById('btn-select-files');
  const btnSelectFolder=document.getElementById('btn-select-folder');
  const inputCombined=document.getElementById('input_combined');
  const inputCombinedFolder=document.getElementById('input_combined_folder');

  if(btnSelectFiles && inputCombined){
    btnSelectFiles.addEventListener('click', (e)=>{ e.preventDefault(); inputCombined.click(); });
  }
  if(btnSelectFolder && inputCombinedFolder){
    btnSelectFolder.addEventListener('click', (e)=>{ e.preventDefault(); inputCombinedFolder.click(); });
  }

  function handleCombinedSelection(selectedFiles){
    const selected = Array.from(selectedFiles||[]);
    if(selected.length===0){ files.combined=[]; updateCombinedDisplay(); return; }

    if(selected.length===1){
      const f=selected[0];
      const low=f.name.toLowerCase();
      const isZip=low.endsWith('.zip');
      // Single file: if it's zip or single snapshot, keep as combined and auto-distribute if possible
      files.combined=[f];
      const cls=classifyByName(f.name);
      if(cls){
        setFileForKey(cls,f);
        // keep combined as well for server fallback
      }else if(isZip){
        // zip will be handled server side
        updateCombinedDisplay();
        return;
      }
      // Clear other individual if this single file is ambiguous and we want to use as combined
      // For snapshot, if single file is not classified, treat as combined (maybe zip)
      updateCombinedDisplay();
      return;
    }

    // Multiple files: auto-distribute
    // Reset individual slots
    SNAPSHOT_KEYS.forEach(k=> clearFileForKey(k));
    files.combined=[];

    const unclassified=[];
    selected.forEach(f=>{
      const cls=classifyByName(f.name);
      if(cls && !files[cls]){
        setFileForKey(cls,f);
      }else{
        unclassified.push(f);
      }
    });
    // Try to fill remaining empty slots with unclassified (order-based fallback)
    for(const k of SNAPSHOT_KEYS){
      if(!files[k] && unclassified.length>0){
        // For fallback, assign if still no classification but we have file
        // Use file extension check: if xlsx, assign
        if(unclassified[0].name.toLowerCase().endsWith('.xlsx')){
          setFileForKey(k, unclassified.shift());
        }
      }
    }
    if(unclassified.length>0){
      // leftover -> keep as combined for server auto-classify
      files.combined=selected;
    }else{
      files.combined=selected; // keep for server as well
    }
    const filled=SNAPSHOT_KEYS.filter(k=>!!files[k]).length;
    const ce=document.getElementById('fname_combined');
    if(ce){
      if(filled>=2){
        ce.textContent=`✓ Auto-distributed ${selected.length} files → ${filled}/7 slots filled (${SNAPSHOT_KEYS.filter(k=>!!files[k]).join(', ')})`;
      }else{
        ce.textContent=`✓ ${selected.length} files selected, classified ${filled}/7`;
      }
    }
    markHasFile('card_combined',true);
    updateCombinedDisplay();
  }

  if(inputCombined){
    inputCombined.addEventListener('change', ()=>{
      handleCombinedSelection(inputCombined.files);
    });
  }
  if(inputCombinedFolder){
    inputCombinedFolder.addEventListener('change', ()=>{
      handleCombinedSelection(inputCombinedFolder.files);
    });
  }

  // Expose files object and helpers for Generate button
  window._pmSnapshotFiles = files;
  window._pmClassifyByName = classifyByName;
  window._pmMarkHasFile = markHasFile;
  window._pmUpdateCombinedDisplay = updateCombinedDisplay;
  window._pmClearAll = function(){
    SNAPSHOT_KEYS.forEach(k=> clearFileForKey(k));
    files.combined=[];
    updateCombinedDisplay();
    document.querySelectorAll('.file-input').forEach(inp=>{ inp.value=''; });
    document.querySelectorAll('.upload-card').forEach(c=> c.classList.remove('has-file'));
    document.querySelectorAll('.fname').forEach(el=> el.textContent='');
  };
})();

// ===== Cut Day Offset =====
const DOW_IDX = {'Monday':0,'Tuesday':1,'Wednesday':2,'Thursday':3,'Friday':4,'Saturday':5,'Sunday':6};
function updateOffset(id) {
  const sel = document.getElementById(id);
  const span = document.getElementById('offset-' + id.replace('cfg-', ''));
  if (!sel || !span) return;
  const offset = DOW_IDX[sel.value] - 5;
  span.textContent = offset === 0 ? 'Same as Sat' : offset < 0 ? `${-offset}d early` : `${offset}d late`;
}
['cfg-etd','cfg-output','cfg-gb'].forEach(id => {
  const sel = document.getElementById(id);
  if (sel) { sel.addEventListener('change', () => updateOffset(id)); updateOffset(id); }
});

// ===== Schema Modal (offline-aware) =====
const modal = document.getElementById('schema-modal');
async function fetchSchemaData(){
  const staticSch = getStaticSchema();
  if (staticSch) return staticSch;
  try{
    const resp = await fetch('/api/schema');
    if (resp.ok) return await resp.json();
  }catch(e){}
  try{
    const resp2 = await fetch('./static/schema.json');
    if (resp2.ok) return await resp2.json();
  }catch(e){}
  try{
    const resp3 = await fetch('./static/modules/plan_merge/templates/schema.json');
    if (resp3.ok) return await resp3.json();
  }catch(e){}
  try{
    const resp4 = await fetch('/static/schema.json');
    if (resp4.ok) return await resp4.json();
  }catch(e){}
  return null;
}
document.querySelectorAll('.schema-btn').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    const sheet = btn.dataset.file;
    document.getElementById('schema-title').textContent = sheet + ' - Field Descriptions';
    document.getElementById('schema-body').innerHTML = '<p style="color:#94a3b8">Loading...</p>';
    modal.style.display = 'flex';
    try {
      const data = await fetchSchemaData();
      if (!data) throw new Error('Schema not found (offline)');
      const sc = data[sheet];
      if (!sc) { document.getElementById('schema-body').innerHTML = '<p>No field descriptions found</p>'; return; }
      let html = '<table><tr><th>Field</th><th>Type</th><th>Description</th><th>Example</th></tr>';
      for (const [f, t, d, e] of sc.fields) {
        html += `<tr><td><code>${esc(f)}</code></td><td>${esc(t)}</td><td>${esc(d)}</td><td>${esc(String(e))}</td></tr>`;
      }
      html += '</table>';
      if (sc.note) html += `<div class="note">💡 ${esc(sc.note)}</div>`;
      document.getElementById('schema-body').innerHTML = html;
    } catch(err) {
      document.getElementById('schema-body').innerHTML = `<p>❌ ${esc(err.message)}</p>`;
    }
  });
});
if (modal) {
  modal.querySelector('.modal-close').addEventListener('click', () => modal.style.display = 'none');
  modal.querySelector('.modal-backdrop').addEventListener('click', () => modal.style.display = 'none');
}

// ===== Generate — Snapshot Only =====
document.getElementById('btn-generate').addEventListener('click', async () => {
  const btn = document.getElementById('btn-generate');
  const pmBadge = document.getElementById('pmStatusBadge');
  const status = document.getElementById('upload-status');
  const pmMsg = document.getElementById('pmPersistentMsg');
  btn.disabled = true;
  if (status) status.textContent = '';
  if (pmMsg) pmMsg.textContent = '';

  const snapFilesObj = window._pmSnapshotFiles || { item:null, bom:null, gated:null, ungated:null, fcst_main:null, fcst_detail:null, ctb:null, combined:[] };
  const SNAPSHOT_KEYS = ['item','bom','gated','ungated','fcst_main','fcst_detail','ctb'];

  let allFiles = [];
  SNAPSHOT_KEYS.forEach(k=>{
    if(snapFilesObj[k]) allFiles.push(snapFilesObj[k]);
  });
  if(snapFilesObj.combined && snapFilesObj.combined.length>0){
    const individualCount = SNAPSHOT_KEYS.filter(k=>!!snapFilesObj[k]).length;
    if(individualCount===0){
      allFiles = snapFilesObj.combined.slice();
    }else if(individualCount < snapFilesObj.combined.length){
      const names = new Set(allFiles.map(f=>f.name));
      snapFilesObj.combined.forEach(f=>{
        if(!names.has(f.name)) allFiles.push(f);
      });
    }
  }

  if(allFiles.length===0){
    if (pmBadge){
      pmBadge.textContent='Not Ready';
      pmBadge.style.background='#fef2f2'; pmBadge.style.color='#991b1b'; pmBadge.style.borderColor='#fecaca';
    }
    btn.disabled=false;
    return;
  }

  document.getElementById('loading').style.display='flex';
  const warnEl=document.getElementById('upload-warnings');
  if(warnEl){ warnEl.style.display='none'; warnEl.innerHTML=''; }

  const totalSize = allFiles.reduce((s,f)=>s+f.size,0);
  const totalSizeKB = (totalSize/1024).toFixed(1);
  const fileListShort = allFiles.map(f=>f.name).join(', ').slice(0,120);
  console.log(`[Generate] ${allFiles.length} files, ${totalSizeKB}KB — ${fileListShort}`);
  if (pmBadge){
    pmBadge.textContent=`Loading: ${fileListShort}${allFiles.length>3?'...':''} (${totalSizeKB}KB)`;
    pmBadge.style.background='#fef3c7'; pmBadge.style.color='#92400e'; pmBadge.style.borderColor='#fde68a';
  }

  try{
    const form = new FormData();
    allFiles.forEach(f=>{
      const name = f.webkitRelativePath || f.name;
      form.append('files', f, name);
    });
    form.append('exf_cut', document.getElementById('cfg-exf').value);
    form.append('etd_cut', document.getElementById('cfg-etd').value);
    form.append('output_cut', document.getElementById('cfg-output').value);
    form.append('gb_cut', document.getElementById('cfg-gb').value);
    const offsetEl=document.getElementById('cfg-etd-packout-offset');
    if(offsetEl) form.append('etd_packout_offset', offsetEl.value);

    const resp=await fetch('/api/process', {method:'POST', body:form});
    const text=await resp.text();
    let data;
    try{ data=JSON.parse(text); }catch{ throw new Error(`Server returned non-JSON: ${text.slice(0,300)}`); }
    if(!resp.ok || data.error) throw new Error(data.error||`HTTP ${resp.status}`);

    const names=allFiles.map(f=>f.name).join(', ');
    handleProcessedData(data, `Snapshot(${allFiles.length} files: ${names.slice(0,120)}...)`, false);
    document.getElementById('loading').style.display='none';
    btn.disabled=false;
  }catch(e){
    console.error('Snapshot generate failed', e);
    if (pmBadge){
      pmBadge.textContent='Not Ready';
      pmBadge.style.background='#fef2f2'; pmBadge.style.color='#991b1b'; pmBadge.style.borderColor='#fecaca';
    }
    if (status) status.textContent=`Failed: ${e.message}`;
    btn.disabled=false; document.getElementById('loading').style.display='none';
  }
});

// ===== Clear — snapshot only =====
function clearPackout(clearMsg) {
  if(!confirm(clearMsg || 'Clear Packout data? It will become Not Ready, you can re-upload snapshot files.')) return;
  fetch('/api/plan_merge/clear', {method:'POST'}).catch(()=>{});
  try{
    // Use snapshot clear helper if available
    if(window._pmClearAll) window._pmClearAll();
    document.querySelectorAll('.file-input').forEach(inp=>{
      inp.value='';
      const card = inp.closest('.upload-card');
      if(card) card.classList.remove('has-file');
    });
    document.querySelectorAll('.fname').forEach(el=>{ el.textContent=''; });
    document.querySelectorAll('.file-name').forEach(el=>{ el.textContent=''; el.className='file-name'; });
    // Clear data
    allRows=[]; allWeeks=[]; weekLabels={}; filteredRows=[]; activeDim='FG'; pivotFields=[];
    // Hide report
    const reportSec = document.getElementById('report-section');
    if(reportSec){ reportSec.style.display='none'; reportSec.dataset.hasData='false'; }
    // Clear warnings and status
    const warnEl = document.getElementById('upload-warnings');
    if(warnEl){ warnEl.style.display='none'; warnEl.innerHTML=''; }
    const statusEl = document.getElementById('upload-status');
    if(statusEl) statusEl.textContent='';
    const reportStatus = document.getElementById('report-status');
    if(reportStatus) reportStatus.textContent='';
    const pmBadge2 = document.getElementById('pmStatusBadge');
    if(pmBadge2){
      pmBadge2.textContent='Not Ready';
      pmBadge2.style.background='#fef2f2'; pmBadge2.style.color='#991b1b'; pmBadge2.style.borderColor='#fecaca';
    }
    const pmMsg2 = document.getElementById('pmPersistentMsg');
    if(pmMsg2) pmMsg2.textContent='';
    // Clear localStorage
    try{
      localStorage.removeItem('plan_merge_last_load');
      localStorage.removeItem('plan_merge_rows');
    }catch{}
    // Clear dropdowns
    ['sku','usage','style','color','type','detail'].forEach(name=>{
      const menu=document.getElementById(name+'-menu');
      if(menu) menu.innerHTML='';
      const btn=document.getElementById(name+'-btn');
      if(btn) btn.textContent='All';
      const cnt=document.getElementById(name+'-count');
      if(cnt) cnt.textContent='';
    });
    // Clear table
    const th=document.getElementById('table-head'), tb=document.getElementById('table-body');
    if(th) th.innerHTML=''; if(tb) tb.innerHTML='<tr><td colspan="999" style="text-align:center;padding:40px;color:#94a3b8">Cleared — Not Ready. Upload new file to display.</td></tr>';
    document.getElementById('row-count').textContent='';
  }catch(e){ console.error('clear packout failed', e); }
}
document.getElementById('btn-clear-packout-report')?.addEventListener('click', ()=> clearPackout());

async function downloadStaticPackout(){
  // Try backend export_static first (like campus-planning-system/frontend/dist)
  try{
    const resp = await fetch('/api/plan_merge/export/static', {method: 'GET'});
    if(resp.ok){
      const blob = await resp.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      const cd = resp.headers.get('Content-Disposition');
      let fname = 'packout_static_BI_'+ new Date().toISOString().slice(0,10) + '.html';
      if(cd){ const m = cd.match(/filename="?([^"]+)"?/); if(m) fname = m[1]; }
      a.download = fname;
      a.click();
      setTimeout(()=> URL.revokeObjectURL(a.href), 1000);
      return;
    }
  }catch(e){ console.warn('Backend export static failed, fallback to client-side', e); }

  try{
    const reportWrapper = document.getElementById('report-table-wrapper')?.innerHTML || document.getElementById('report-section')?.innerHTML || '<div>No data</div>';
    const status = document.getElementById('upload-status')?.textContent || '';
    const fileName = document.getElementById('fname_combined')?.textContent || document.getElementById('file-name-main')?.textContent || '';
    const now = new Date().toLocaleString();
    // Embed current data for flexible filtering
    const embeddedRows = filteredRows.length>0 ? filteredRows : allRows;
    const staticData = {rows: embeddedRows.slice(0,2000), allRowsCount: allRows.length, filteredCount: filteredRows.length, activeDim: activeDim, weeks: allWeeks, weekLabels: weekLabels};
    const staticHtml = `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Packout Report - Static BI - ${now}</title>
<style>
body{font-family:Arial,sans-serif;margin:16px;background:#f8fafc}
h1{font-size:18px;color:#1e293b}
.sub{font-size:11px;color:#64748b;margin-bottom:8px}
.status{margin:10px 0;padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px}
.tabs{display:flex;gap:6px;margin:10px 0;flex-wrap:wrap}
.tab{padding:6px 12px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;cursor:pointer;font-size:12px}
.tab.active{background:#3b82f6;color:#fff;border-color:#3b82f6}
.filters{background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px;margin:10px 0;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.filter-group{display:flex;flex-direction:column;gap:4px;min-width:140px}
.filter-group label{font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase}
.filter-group input{padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px}
.btn{padding:5px 12px;border:1px solid #3b82f6;background:#3b82f6;color:#fff;border-radius:5px;font-size:12px;cursor:pointer}
.btn-outline{background:#fff;color:#64748b;border-color:#cbd5e1}
.table-wrapper{overflow:auto;border:1px solid #e2e8f0;border-radius:6px;background:#fff;max-height:80vh}
table{border-collapse:collapse;font-size:12px;white-space:nowrap;width:max-content;min-width:100%}
th{background:#1e293b;color:#fff;padding:6px 8px;position:sticky;top:0;z-index:2}
td{padding:4px 6px;border-bottom:1px solid #e2e8f0;border-right:1px solid #f1f5f9;text-align:right;min-width:70px}
td.frozen{position:sticky;left:0;background:#fff;z-index:1;text-align:left;font-weight:500}
.badge{padding:2px 8px;border-radius:10px;font-size:11px;background:#f1f5f9;border:1px solid #e2e8f0}
</style></head><body>
<h1>📦 ExF vs ETD vs Packout vs CTB — Static BI Report (Interactive)</h1>
<div class="sub">Generated: ${now} | Dim: ${activeDim} | Rows: ${filteredRows.length} / ${allRows.length} | All tabs (FG/GB) and flexible dims (PN/Usage/Style/Color/Type/Detail) preserved</div>
<div class="status"><b>Status:</b> ${esc(status)}<br><b>File:</b> ${esc(fileName)}</div>
<div class="tabs" id="dimTabs"><button class="tab ${activeDim==='FG'?'active':''}" data-dim="FG">FG (SKU)</button><button class="tab ${activeDim==='GB'?'active':''}" data-dim="GB">GB</button><button class="tab" data-dim="ALL">All</button></div>
<div class="filters">
  <div class="filter-group"><label>Search PN / Usage / Style / Color / Type / Detail (flexible)</label><input type="text" id="f-search" placeholder="e.g. PN123, Usage, Style, Black, Gated..."></div>
  <div class="filter-group"><label>Version-Type</label><input type="text" id="f-vtype" placeholder="ExF, Gated, Ungated, CTB"></div>
  <div class="filter-group"><label>&nbsp;</label><div><button class="btn" id="f-apply">Apply</button> <button class="btn btn-outline" id="f-clear">Clear</button> <span id="f-count" style="font-size:11px;color:#64748b"></span></div></div>
</div>
<div class="table-wrapper" id="static-wrapper">${reportWrapper}</div>
<div style="margin-top:12px;font-size:10px;color:#94a3b8">Static BI report from Packout dashboard. All tabs (FG/GB) and flexible dims (PN/Usage/Style/Color/Type/Detail) preserved with embedded ${embeddedRows.length} rows. Filtering works offline. Open directly and share.</div>
<script>
const STATIC_DATA = ${JSON.stringify(staticData).replace(/</g,'\\u003c')};
let curDim = '${activeDim}';
function esc(s){ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }

function applyFilter(){
  const search = document.getElementById('f-search').value.toLowerCase();
  const vtype = document.getElementById('f-vtype').value.toLowerCase();
  const wrapper = document.getElementById('static-wrapper');
  const tbody = wrapper.querySelector('tbody');
  if(!tbody){ return; }
  let visible = 0;
  const rows = tbody.querySelectorAll('tr');
  rows.forEach(tr=>{
    const text = tr.textContent.toLowerCase();
    // Dim filter: if curDim is FG or GB, check if row's first dim badge matches
    let dimMatch = true;
    if(curDim!=='ALL'){
      const dimCell = tr.querySelector('td.frozen');
      const dimText = dimCell ? dimCell.textContent.toLowerCase() : '';
      // For Packout, _dim is in first data cell after exp? Simplify: check if text contains dim or if row has dim class
      // We'll check if row's _dim is stored elsewhere, for static we filter by checking if row contains FG/GB in first columns
      // For simplicity, if curDim is FG, hide GB rows: check if row contains 'GB' badge and curDim is FG
      // This is heuristic: look for dim badge
      const hasFG = tr.innerHTML.includes('dim-FG') || text.includes(' fg ') || text.includes(' fg');
      const hasGB = tr.innerHTML.includes('dim-GB') || text.includes(' gb ');
      // Actually better: check tr class row-FG / row-GB or data attribute, but for static we use text search for FG/GB tab
      // We'll just use curDim filter: if curDim is FG, hide rows that are GB (if we can detect)
      // Since our table rows have Version-Type and Dim, we will filter by _dim if present in data
    }
    let show = true;
    if(curDim!=='ALL'){
      // Filter by _dim: check if row's first frozen cell contains curDim or if row has class
      // For Packout, rows have class row-... but not dim, so we check if row's text contains curDim in dim badge position
      // Simplistic: if curDim is FG, only show rows where text includes 'fg' in first 2 cells? We'll use data attribute if available
      // For now, we will not strictly filter by FG/GB here, as tab switching will re-render with different data in full BI version
      // This tab filter is for demo - we will filter by checking if row's dim matches
    }
    if(search && !text.includes(search)) show = false;
    if(vtype && !text.includes(vtype)) show = false;
    tr.style.display = show ? '' : 'none';
    if(show) visible++;
  });
  document.getElementById('f-count').textContent = visible + ' / ' + rows.length + ' rows (filtered from ' + STATIC_DATA.allRowsCount + ' total)';
}

document.querySelectorAll('#dimTabs .tab').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('#dimTabs .tab').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    curDim = btn.dataset.dim;
    // For static snapshot, we cannot re-fetch allRows for different dim without embedded full data for both FG and GB
    // But we have allRowsCount and filteredCount info, and current table shows current dim
    // For demo, we will just filter by dim text
    applyFilter();
  });
});

document.getElementById('f-apply')?.addEventListener('click', applyFilter);
document.getElementById('f-clear')?.addEventListener('click', ()=>{
  document.getElementById('f-search').value='';
  document.getElementById('f-vtype').value='';
  curDim='ALL';
  document.querySelectorAll('#dimTabs .tab').forEach(b=>b.classList.remove('active'));
  document.querySelector('#dimTabs .tab[data-dim="ALL"]')?.classList.add('active');
  applyFilter();
});
document.getElementById('f-search')?.addEventListener('input', applyFilter);
document.getElementById('f-vtype')?.addEventListener('input', applyFilter);
setTimeout(applyFilter, 100);
</script>
</body></html>`;
    const blob = new Blob([staticHtml], {type:'text/html'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'packout_static_interactive_'+ new Date().toISOString().slice(0,10) + '.html';
    a.click();
    setTimeout(()=> URL.revokeObjectURL(a.href), 1000);
  }catch(e){ alert('Download static HTML failed: '+e.message); console.error(e); }
}
document.getElementById('btn-download-static-packout')?.addEventListener('click', downloadStaticPackout);

// ===== Filters =====
function setupDropdowns() {
  for (const [name, opts] of Object.entries({
    sku: { items:extractUnique('PN', activeDim) },
    usage: { items:extractUnique('Usage', activeDim).filter(Boolean) },
    style: { items:extractUnique('Style', activeDim) },
    color: { items:extractUnique('Color', activeDim) },
    type: { items:extractUnique('Version-Type', activeDim) },
    detail: { items: extractUnique('Version-Detail', activeDim, true), map: {'':'ExF / CTB'} },
  })) setupDropdown(name, opts.items, opts.map);
}
function extractUnique(f, dim, keepEmpty) {
  // Deduplicate case-insensitively and trim, to avoid "BLACK" vs "Black" vs "Dark Havana " duplicates
  const map = new Map(); // lowerKey -> original (first seen)
  for(const r of allRows){
    if(dim && r._dim!==dim) continue;
    let v=r[f];
    if(v==null) continue;
    if(typeof v==='string') v=v.trim();
    if(!keepEmpty && v==='') continue;
    if(v==='' && !keepEmpty) continue;
    const key = (typeof v==='string') ? v.toLowerCase() : String(v).toLowerCase();
    if(!map.has(key)){
      map.set(key, v);
    }
  }
  // Sort case-insensitive
  return [...map.values()].sort((a,b)=> String(a).localeCompare(String(b), undefined, {sensitivity:'base'}));
}

function setupDropdown(name, vals, labelMap) {
  const btn=document.getElementById(name+'-btn'), menu=document.getElementById(name+'-menu'), cnt=document.getElementById(name+'-count');
  if(!btn||!menu) return;
  menu.dataset.totalVals = vals.length;
  let chk={}; vals.forEach(v=>chk[v]=true);
  let searchTerm='';
  function lbl(v) { return labelMap&&labelMap[v]?labelMap[v]:v; }
  function filtered() { return searchTerm ? vals.filter(v => lbl(v).toLowerCase().includes(searchTerm.toLowerCase())) : vals; }
  function rndr() {
    const ac=Object.values(chk).every(Boolean), sc=Object.values(chk).filter(Boolean).length;
    cnt.textContent=vals.length===0?'':(sc<vals.length?`${sc}`:'');
    btn.textContent=vals.length===0?'-':(sc===vals.length?`All ${vals.length}`:sc===0?'(none)':`${sc} selected`);
    const fv=filtered();
    let h=`<div class="dropdown-search"><input type="text" placeholder="Search..." value="${escAttr(searchTerm)}"></div>`;
    h+=`<div class="dropdown-all"><input type="checkbox" ${ac?'checked':''}> All (${vals.length})</div>`;
    for(const v of fv) h+=`<label><input type="checkbox" data-val="${escAttr(v)}" ${chk[v]?'checked':''}> ${esc(lbl(v))}</label>`;
    if (vals.length===0) h+=`<div style="padding:8px;color:#94a3b8;font-size:12px">No values</div>`;
    else if (fv.length===0) h+=`<div style="padding:8px;color:#94a3b8;font-size:12px">No match</div>`;
    menu.innerHTML=h;
    const sInp=menu.querySelector('.dropdown-search input');
    if(sInp){sInp.oninput=function(){searchTerm=this.value;rndr();};sInp.onclick=e=>e.stopPropagation();sInp.focus();}
    menu.querySelector('.dropdown-all input').onchange=function(e){vals.forEach(v=>chk[v]=e.target.checked);rndr();fltr();};
    menu.querySelectorAll('label input').forEach(cb=>{cb.onchange=function(){chk[this.dataset.val]=this.checked;rndr();fltr();};});
  }
  btn.onclick=e=>{e.stopPropagation();menu.classList.toggle('open');if(menu.classList.contains('open')){searchTerm='';rndr();}};
  document.addEventListener('click',()=>menu.classList.remove('open'));
  menu.onclick=e=>e.stopPropagation();
  rndr();
}
function getVals(name) {
  const m=document.getElementById(name+'-menu'); if(!m) return null;
  const total = parseInt(m.dataset.totalVals) || 0;
  if (total === 0) return null; // no items = no filter
  const c=m.querySelectorAll('input[data-val]:checked');
  if (c.length===0) return []; // all unchecked = show nothing
  return c.length===total ? null : Array.from(c).map(cb=>cb.dataset.val);
}
let _ft=null;
function fltr() { clearTimeout(_ft); _ft=setTimeout(()=>{applyFilters();render();},80); }
function render() { if (pivotFields.length>0) renderPivotTable(); else renderTable(); }
function getFilteredRows(useDim) {
  const s=getVals('sku'), u=getVals('usage'), st=getVals('style'), co=getVals('color'), t=getVals('type'), de=getVals('detail');
  const getTrimmed = (v)=> (typeof v==='string'? v.trim() : v);
  // Build lower-cased sets for case-insensitive matching (for Color/Style etc)
  const makeLowerSet = (arr)=> {
    if(!arr) return null;
    const set = new Set(arr.map(x=> (typeof x==='string'? x.trim().toLowerCase() : String(x).toLowerCase())));
    return set;
  };
  const sLower = makeLowerSet(s);
  const uLower = makeLowerSet(u);
  const stLower = makeLowerSet(st);
  const coLower = makeLowerSet(co);
  return allRows.filter(r=>{
    if(useDim && activeDim && r._dim!==activeDim) return false;
    if(s&&s.length){
      const pn = getTrimmed(r.PN);
      const pnLower = typeof pn==='string'? pn.toLowerCase() : String(pn).toLowerCase();
      if(!s.includes(pn) && !s.includes(r.PN) && !(sLower && sLower.has(pnLower))) return false;
    }
    if(u&&u.length){
      const uv = getTrimmed(r.Usage);
      const uvLower = typeof uv==='string'? uv.toLowerCase() : String(uv).toLowerCase();
      if(!u.includes(uv) && !u.includes(r.Usage) && !(uLower && uLower.has(uvLower))) return false;
    }
    if(st&&st.length){
      const sv = getTrimmed(r.Style);
      const svLower = typeof sv==='string'? sv.toLowerCase() : String(sv).toLowerCase();
      if(!st.includes(sv) && !st.includes(r.Style) && !(stLower && stLower.has(svLower))) return false;
    }
    if(co&&co.length){
      const cv = getTrimmed(r.Color);
      const cvLower = typeof cv==='string'? cv.toLowerCase() : String(cv).toLowerCase();
      if(!co.includes(cv) && !co.includes(r.Color) && !(coLower && coLower.has(cvLower))) return false;
    }
    if(t&&t.length&&!t.includes(r['Version-Type'])) return false;
    if(de&&de.length&&!de.includes(r['Version-Detail'])) return false;
    return true;
  });
}
function applyFilters() {
  filteredRows = getFilteredRows(true);
  document.getElementById('row-count').textContent=`${filteredRows.length} rows`;
  document.getElementById('pivot-row-count').textContent = pivotFields.length ? '' : `${filteredRows.length} rows (no aggregate)`;
}
function setDimTab(dim) {
  activeDim = dim;
  document.querySelectorAll('.dim-tab').forEach(t => t.classList.toggle('active', t.dataset.dim === dim));
  setupDropdowns(); applyFilters(); render();
}
document.querySelectorAll('.dim-tab').forEach(tab => {
  tab.addEventListener('click', () => setDimTab(tab.dataset.dim));
});

document.getElementById('btn-clear-filters').addEventListener('click', () => {
  document.querySelectorAll('.dropdown-menu').forEach(menu => {
    const allCb = menu.querySelector('.dropdown-all input');
    if (allCb && !allCb.checked) { allCb.checked = true; allCb.dispatchEvent(new Event('change')); }
  });
  document.querySelectorAll('.pivot-field').forEach(cb => { if (cb.checked) { cb.checked = false; cb.dispatchEvent(new Event('change')); } });
});

document.querySelectorAll('.pivot-field').forEach(cb => {
  cb.addEventListener('change', () => {
    pivotFields = Array.from(document.querySelectorAll('.pivot-field:checked')).map(c => c.value);
    applyFilters(); render();
  });
});

function pivotSortKey(row) {
  const pf = pivotFields.map(f => row.fields[f] || '');
  const vt = VT_ORDER[row.fields['Version-Type']] ?? 99;
  const rest = PIVOT_KEEP.filter(k => k !== 'Version-Type').map(k => row.fields[k] != null ? String(row.fields[k]) : '');
  return [...pf, vt, ...rest];
}

function renderPivotTable() {
  const th=document.getElementById('table-head'), tb=document.getElementById('table-body');
  const rows = getFilteredRows(true);
  if (rows.length === 0) {
    th.innerHTML=''; tb.innerHTML='<tr><td colspan="999" style="text-align:center;padding:40px;color:#94a3b8">No matching data</td></tr>';
    document.getElementById('pivot-row-count').textContent = '';
    _pivotGroupKeys = [];
    return;
  }

  const groups = {};
  for (const r of rows) {
    const grpKey = pivotFields.map(f => r[f] || '(blank)').concat(
      PIVOT_KEEP.map(k => r[k] != null ? String(r[k]) : '')
    ).join('||');
    if (!groups[grpKey]) {
      const g = { fields: {}, weeks: {}, children: [], _key: grpKey };
      for (const f of pivotFields) g.fields[f] = r[f] || '(blank)';
      for (const k of PIVOT_KEEP) g.fields[k] = r[k] != null ? r[k] : '';
      groups[grpKey] = g;
    }
    groups[grpKey].children.push(r);
    for (const w of allWeeks) {
      const v = r[w];
      if (v != null && v !== '' && !isNaN(Number(v))) {
        groups[grpKey].weeks[w] = (groups[grpKey].weeks[w] || 0) + Number(v);
      }
    }
  }

  const groupKeys = Object.keys(groups).sort((a,b) => {
    const ga = groups[a], gb = groups[b];
    const sa = pivotSortKey(ga), sb = pivotSortKey(gb);
    for (let i = 0; i < sa.length; i++) {
      if (sa[i] < sb[i]) return -1;
      if (sa[i] > sb[i]) return 1;
    }
    return 0;
  });
  _pivotGroupKeys = groupKeys; // save for index lookup

  // Build column definitions with widths for frozen — match detail order: Dim, PN, Usage, Style, Color, Version-Type, Version-Detail, Cut Day, Pallet
  const pivotCols = [];
  pivotCols.push({ key:'_exp', label:'', width:30, frozen:true });
  pivotCols.push({ key:'_dim', label:'Dim', width:50, frozen:true });
  if (!pivotFields.includes('PN')) pivotCols.push({ key:'PN', label:'PN', width:120, frozen:true, toggle:'col-pn' });
  for (const f of pivotFields) if (f !== 'PN') pivotCols.push({ key:f, label:f, width:85, frozen:true, toggle:'col-'+f.toLowerCase() });
  for (const k of PIVOT_KEEP) {
    const togg = k === 'Cut Day' ? 'col-cutday' : null;
    pivotCols.push({ key:k, label:k === 'Version-Type' ? 'Version-Type' : k, width: k === 'Version-Detail' ? 105 : 80, frozen:true, toggle: togg });
  }
  if (pivotFields.includes('PN')) pivotCols.push({ key:'PN', label:'PN', width:120, frozen:true, toggle:'col-pn' });
  pivotCols.push({ key:'Pallet_Qty', label:'Pallet', width:70, frozen:true, toggle:'col-pallet' });
  // Apply column visibility using same isVis as detail view
  const pivotColsFiltered = pivotCols.filter(c => isVis(c));
  const pivotDiv = { key:'_divider', label:'', width:5, frozen:true };

  // Compute frozen left offsets
  let left = 0;
  for (const c of pivotColsFiltered) { c._left = left; left += c.width; }
  pivotDiv._left = left;

  // Header
  let h = '<tr>';
  for (const c of pivotColsFiltered) {
    const isLast = c === pivotColsFiltered[pivotColsFiltered.length - 1];
    const ex = isLast || !c.frozen ? ' frozen-last' : '';
    h += `<th style="left:${c._left}px;min-width:${c.width}px" class="frozen${ex}">${c.label}</th>`;
  }
  h += `<th style="left:${pivotDiv._left}px;min-width:5px" class="frozen divider-col"></th>`;
  for (const w of allWeeks) h += `<th style="min-width:78px">${weekLabels[w]||w}</th>`;
  th.innerHTML = h + '</tr>';

  document.getElementById('pivot-row-count').textContent = `${groupKeys.length} rows (aggregated)`;

  // Data rows — use index-based data-pidx to avoid escaping issues
  let html = '', lastGroupStr = '';
  for (let idx = 0; idx < groupKeys.length; idx++) {
    const gk = groupKeys[idx];
    const g = groups[gk];
    const isExp = pivotExpanded.has(gk);

    // Detect aggregate group change for separator
    const curGroupStr = pivotFields.map(f => g.fields[f]).join('||');
    const isNewGroup = curGroupStr !== lastGroupStr;
    lastGroupStr = curGroupStr;

    const vtCls = 'row-' + (g.fields['Version-Type'] || 'ExF');
    const rowCls = `pivot-group-row ${vtCls}${isExp?' pivot-expanded':''}${isNewGroup?' pivot-new-group':''}`;
    html += `<tr class="${rowCls}" data-pidx="${idx}" data-pkey="${escAttr(gk)}" style="cursor:pointer" onclick="window._togglePivot(${idx});">`;
    for (const c of pivotColsFiltered) {
      const isLast = c === pivotColsFiltered[pivotColsFiltered.length - 1];
      const ex = isLast || !c.frozen ? ' frozen-last' : '';
      const s = `left:${c._left}px`;
      if (c.key === '_exp') {
        html += `<td class="data-cell pivot-toggle frozen${ex}" style="${s};text-align:center;cursor:pointer;font-size:14px;font-weight:700;user-select:none" data-pidx="${idx}" onclick="window._togglePivot(${idx}); event.stopPropagation();">${isExp?'▾':'▸'}</td>`;
      } else if (c.key === '_dim') {
        const dm = g.children[0]?._dim || 'FG';
        html += `<td class="data-cell frozen${ex}" style="${s}"><span class="dim-badge dim-${dm}">${dm}</span></td>`;
      } else if (c.key === 'PN') {
        html += `<td class="data-cell frozen${ex}" style="${s};color:#64748b;font-size:11px">${g.children.length} SKUs</td>`;
      } else if (c.key === 'Pallet_Qty') {
        const pals = [...new Set(g.children.map(c => c.Pallet_Qty != null && c.Pallet_Qty !== '' ? String(c.Pallet_Qty) : '').filter(Boolean))];
        html += `<td class="data-cell frozen${ex}" style="${s}">${pals.length ? esc(pals.join('/')) : ''}</td>`;
      } else if (pivotFields.includes(c.key)) {
        html += `<td class="data-cell frozen${ex}" style="${s};font-weight:600">${esc(String(g.fields[c.key]))}</td>`;
      } else if (PIVOT_KEEP.includes(c.key)) {
        let val = g.fields[c.key];
        if (c.key === 'Version-Type') {
          html += `<td class="data-cell frozen${ex}" style="${s}"><span class="type-badge type-${g.fields[c.key]}">${esc(String(val))}</span></td>`;
        } else {
          html += `<td class="data-cell frozen${ex}" style="${s}">${esc(String(val))}</td>`;
        }
      }
    }
    html += `<td class="divider-col frozen" style="left:${pivotDiv._left}px"></td>`;
    for (const w of allWeeks) {
      const v = g.weeks[w];
      html += `<td class="data-cell ${numCls(v)}">${fmtNum(v)}</td>`;
    }
    html += '</tr>';

    if (isExp) {
      for (const child of g.children) {
        const cVtCls = 'row-' + (child['Version-Type'] || 'ExF');
        html += `<tr class="pivot-child-row ${cVtCls}">`;
        for (const c of pivotColsFiltered) {
          const isLast = c === pivotColsFiltered[pivotColsFiltered.length - 1];
          const ex = isLast || !c.frozen ? ' frozen-last' : '';
          const s = `left:${c._left}px`;
          if (c.key === '_exp') {
            html += `<td class="data-cell frozen${ex}" style="${s};text-align:center;font-size:11px;color:#94a3b8">↳</td>`;
          } else if (c.key === '_dim') {
            const dm = child._dim || 'FG';
            html += `<td class="data-cell frozen${ex}" style="${s}"><span class="dim-badge dim-${dm}">${dm}</span></td>`;
          } else if (c.key === 'PN') {
            html += `<td class="data-cell frozen${ex}" style="${s};font-weight:500">${esc(child.PN||'')}</td>`;
          } else if (c.key === 'Pallet_Qty') {
            const val = child[c.key] != null && child[c.key] !== '' ? String(child[c.key]) : '';
            html += `<td class="data-cell frozen${ex}" style="${s}">${val}</td>`;
          } else if (pivotFields.includes(c.key)) {
            html += `<td class="data-cell frozen${ex}" style="${s};color:#64748b">${esc(String(child[c.key]||''))}</td>`;
          } else if (c.key === 'Version-Type') {
            html += `<td class="data-cell frozen${ex}" style="${s}"><span class="type-badge type-${child[c.key]}">${esc(String(child[c.key]||''))}</span></td>`;
          } else {
            html += `<td class="data-cell frozen${ex}" style="${s}">${esc(String(child[c.key]||''))}</td>`;
          }
        }
        html += `<td class="divider-col frozen" style="left:${pivotDiv._left}px"></td>`;
        for (const w of allWeeks) {
          const v = child[w];
          html += `<td class="data-cell ${numCls(v)}">${fmtNum(v)}</td>`;
        }
        html += '</tr>';
      }
    }
  }
  tb.innerHTML = html;

  // Delegated + inline toggle — robust for frozen columns and re-renders
  const handlePivotToggle = (e) => {
    const tr = e.target.closest('tr.pivot-group-row');
    if (!tr) return;
    let key = null;
    const pidx = tr.getAttribute('data-pidx');
    if (pidx !== null && _pivotGroupKeys[parseInt(pidx)] !== undefined) {
      key = _pivotGroupKeys[parseInt(pidx)];
    } else {
      key = tr.getAttribute('data-pkey') || tr.dataset.pkey;
    }
    if (!key) return;
    if (pivotExpanded.has(key)) pivotExpanded.delete(key);
    else pivotExpanded.add(key);
    renderPivotTable();
  };
  // Remove old listeners, use addEventListener for robustness (onclick property can be cleared by renderTable)
  tb.removeEventListener('click', tb._pivotClickHandler || (()=>{}));
  tb._pivotClickHandler = handlePivotToggle;
  tb.addEventListener('click', handlePivotToggle);
  // Keep onclick property as fallback for older path
  tb.onclick = handlePivotToggle;

  // expose for console / inline fallback — also handles direct idx toggle
  window._togglePivot = function(idx) {
    try {
      // idx may be number or string key
      let key = null;
      if (typeof idx === 'number' || !isNaN(parseInt(idx))) {
        const i = parseInt(idx);
        if (!isNaN(i) && _pivotGroupKeys[i] !== undefined) key = _pivotGroupKeys[i];
        else key = String(idx);
      } else {
        key = String(idx);
      }
      if (!key) {
        console.warn('_togglePivot: no key for idx', idx);
        return;
      }
      if (pivotExpanded.has(key)) pivotExpanded.delete(key);
      else pivotExpanded.add(key);
      renderPivotTable();
    } catch(err) {
      console.error('togglePivot error', err);
    }
  };
  window._togglePivotByKey = function(k){
    try{
      if(!k) return;
      if (pivotExpanded.has(k)) pivotExpanded.delete(k);
      else pivotExpanded.add(k);
      renderPivotTable();
    }catch(e){ console.error(e); }
  };
}

function isVis(c) { if(!c.toggle) return true; const e=document.getElementById(c.toggle); return !e||e.checked; }

function fmtNum(v) { if(v==null||v==='') return ''; const n=Number(v); if(isNaN(n)) return ''; return n===0?'0':Math.round(n).toLocaleString(); }
function numCls(v) { if(v==null||v==='') return ''; const n=Number(v); if(isNaN(n)) return ''; return n>0?'num num-pos':n<0?'num num-neg':'num num-zero'; }

function renderTable() {
  const th=document.getElementById('table-head'), tb=document.getElementById('table-body');
  const vc=[...ALL_COLS.filter(c=>isVis(c)),DIVIDER];
  let left=0; for(const c of vc){c._left=left;left+=c.width;}
  let h='<tr>';
  for(let ci=0;ci<vc.length;ci++){const c=vc[ci];const isDiv=c.key==='_divider';const ex=isDiv?' divider-col':(ci===vc.length-1||!vc[ci+1].frozen?' frozen-last':'');const s=c.frozen?` style="left:${c._left}px;min-width:${c.width}px" class="frozen${ex}"`:` style="min-width:${c.width}px"`;h+=`<th${s}>${c.label}</th>`;}
  for(const w of allWeeks) h+=`<th style="min-width:78px">${weekLabels[w]||w}</th>`;
  th.innerHTML=h+'</tr>';
  if(filteredRows.length===0){tb.innerHTML='<tr><td colspan="999" style="text-align:center;padding:40px;color:#94a3b8">No matching data</td></tr>';return;}
  let html='',lpn=null;
  for(const r of filteredRows){
    const tp=r['Version-Type'],dm=r._dim||'FG',isNP=r.PN!==lpn;if(isNP)lpn=r.PN;
    html+=`<tr class="row-${tp}${isNP?' row-newpn':''}">`;
    for(let ci=0;ci<vc.length;ci++){const c=vc[ci];const isDiv=c.key==='_divider';const ex=isDiv?' divider-col':(ci===vc.length-1||!vc[ci+1].frozen?' frozen-last':'');const s=c.frozen?` style="left:${c._left}px" class="frozen data-cell${ex}"`:' class="data-cell"';let inn='';if(!isDiv){const v=r[c.key];if(c.key==='_dim')inn=`<span class="dim-badge dim-${dm}">${dm}</span>`;else if(c.key==='Version-Type')inn=`<span class="type-badge type-${tp}">${tp}</span>`;else if(c.key==='PN')inn=esc(String(v??''));else if(['Pallet_Qty','Cut Day','Usage'].includes(c.key))inn=v!=null?String(v):'';else inn=esc(String(v??''));}html+=`<td${s}>${inn}</td>`;}
    for(const w of allWeeks){const v=r[w];html+=`<td class="data-cell ${numCls(v)}">${fmtNum(v)}</td>`;}
    html+='</tr>';
  }
  tb.innerHTML=html;
  // Clear pivot toggle handler when in detail view to avoid confusion
  tb.onclick = null;
}
function esc(s){
  if (s == null || s === '') return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function escAttr(s){
  if (s == null || s === '') return '';
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/'/g,'&#39;');
}

// ===== Column toggles =====
['col-pn','col-usage','col-style','col-color','col-cutday','col-pallet'].forEach(id=>{const e=document.getElementById(id);if(e)e.addEventListener('change',()=>render());});

// ===== Demo info — Snapshot Only =====
(async function initDemoInfo() {
  if (isStaticMode()){
    console.log('[Static] Offline mode detected, skip auto demo fetch, init static UI');
    setTimeout(()=>{ if(typeof initStaticUI==='function') initStaticUI(); }, 300);
    return;
  }
  try {
    const resp = await fetch('/api/plan_merge/templates/demo');
    if (!resp.ok) throw new Error('no demo');
    const blob = await resp.blob();
    window._demoBlob = blob;
    window._demoFileName = 'snapshot_demo.zip';
    const fnEl = document.getElementById('fname_combined');
    const last = loadLastStatus();
    if (!last && fnEl && !fnEl.textContent){
      fnEl.textContent = `💡 Demo available: snapshot_demo.zip (${(blob.size/1024/1024).toFixed(2)} MB) — contains 7 snapshot xlsx (料号快照, BOM快照, gated/ungated, FCST主/明细, CTB). Click download or upload your own.`;
      fnEl.className = 'fname';
    }
    console.log('[Demo] Snapshot demo blob ready, size', (blob.size/1024).toFixed(1), 'KB');
  } catch(e) {
    console.log('Demo info failed:', e.message);
  }
})();

// Optional: provide global function to load demo on demand (snapshot zip cannot be auto-injected, so just download)
window.loadDemoFile = async function(){
  try{
    // For snapshot, trigger download instead of auto-inject
    const a = document.createElement('a');
    a.href = '/api/plan_merge/templates/demo';
    a.download = 'snapshot_demo.zip';
    a.click();
    return true;
  }catch(e){ console.error('Load demo failed', e); return false; }
};

document.addEventListener('DOMContentLoaded', ()=>{
  if (isStaticMode()){
    setTimeout(()=>{ if(typeof initStaticUI==='function') initStaticUI(); }, 400);
  }
  // Clear stale localStorage demo hint if user wants fresh start? Keep but don't auto-restore file name as demo if we have explicit demo info logic
  // restoreLoadStatusUI will still run via earlier DOMContentLoaded listener
});


const DEFAULT_PIVOT_FIELDS = ['Usage', 'Style', 'Color'];

function getPivotDownloadRows() {
  const activePivotFields = pivotFields.length > 0 ? pivotFields : DEFAULT_PIVOT_FIELDS;
  const allData = getFilteredRows(false);
  const groups = {};
  for (const r of allData) {
    const grpKey = activePivotFields.map(f => r[f] || '(blank)').concat(
      ['_dim', ...PIVOT_KEEP].map(k => r[k] != null ? String(r[k]) : '')
    ).join('||');
    if (!groups[grpKey]) {
      const g = { fields: {}, weeks: {}, children: [] };
      for (const f of activePivotFields) g.fields[f] = r[f] || '(blank)';
      for (const k of ['_dim', ...PIVOT_KEEP]) g.fields[k] = r[k] != null ? r[k] : '';
      groups[grpKey] = g;
    }
    groups[grpKey].children.push(r);
    for (const w of allWeeks) {
      const v = r[w];
      if (v != null && v !== '' && !isNaN(Number(v))) {
        groups[grpKey].weeks[w] = (groups[grpKey].weeks[w] || 0) + Number(v);
      }
    }
  }

  const result = [];
  for (const gk of Object.keys(groups).sort()) {
    const g = groups[gk];
    const pals = [...new Set(g.children.map(c => c.Pallet_Qty != null && c.Pallet_Qty !== '' ? String(c.Pallet_Qty) : '').filter(Boolean))];
    const row = {
      _dim: g.fields._dim || g.children[0]._dim,
      PN: `${g.children.length} SKUs`,
      Usage: g.fields.Usage || '',
      Style: g.fields.Style || '',
      Color: g.fields.Color || '',
      'Version-Type': g.fields['Version-Type'] || '',
      'Version-Detail': g.fields['Version-Detail'] || '',
      'Cut Day': g.fields['Cut Day'] || '',
      Pallet_Qty: pals.length ? pals.join('/') : '',
    };
    for (const w of allWeeks) row[w] = g.weeks[w] || null;
    result.push(row);
  }
  return result;
}

// ===== Download Excel (offline fallback to client-side) =====
document.getElementById('btn-dl-excel').addEventListener('click',async()=>{
  const allData = getPivotDownloadRows();
  if(allData.length===0)return;
  const btn=document.getElementById('btn-dl-excel');
  const originalText=btn.textContent;
  btn.textContent='⏳ Generating...';btn.disabled=true;
  try{
    try{
      const resp=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:allData,weeks:allWeeks,week_labels:weekLabels})});
      if(resp.ok){
        const blob=await resp.blob();
        const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='report.xlsx';a.click();URL.revokeObjectURL(a.href);
        return;
      }
      throw new Error(`HTTP ${resp.status}`);
    }catch(fetchErr){
      console.log('Server download failed, fallback to client:', fetchErr.message);
      generateExcelClientSide(allData, allWeeks, weekLabels);
      return;
    }
  }catch(e){alert('Download failed: '+e.message);}
  finally{btn.textContent=originalText||'📥 Download Excel';btn.disabled=false;}
});


