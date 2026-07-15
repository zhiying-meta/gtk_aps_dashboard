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

// ===== Upload: mark files =====
document.querySelectorAll('.file-input').forEach(inp => {
  inp.addEventListener('change', () => {
    const card = inp.closest('.upload-card');
    card.classList.toggle('has-file', inp.files.length > 0);
  });
});

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

// ===== Schema Modal =====
const modal = document.getElementById('schema-modal');
document.querySelectorAll('.schema-btn').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    const sheet = btn.dataset.file;
    document.getElementById('schema-title').textContent = sheet + ' - Field Descriptions';
    document.getElementById('schema-body').innerHTML = '<p style="color:#94a3b8">Loading...</p>';
    modal.style.display = 'flex';
    try {
      const resp = await fetch('/api/schema');
      const data = await resp.json();
      const sc = data[sheet];
      if (!sc) { document.getElementById('schema-body').innerHTML = '<p>No field descriptions found</p>'; return; }
      let html = '<table><tr><th>Field</th><th>Type</th><th>Description</th><th>Example</th></tr>';
      for (const [f, t, d, e] of sc.fields) {
        html += `<tr><td><code>${esc(f)}</code></td><td>${esc(t)}</td><td>${esc(d)}</td><td>${esc(String(e))}</td></tr>`;
      }
      html += '</table>';
      if (sc.note) html += `<div class="note">💡 ${esc(sc.note)}</div>`;
      document.getElementById('schema-body').innerHTML = html;
    } catch(e) {
      document.getElementById('schema-body').innerHTML = `<p>❌ ${e.message}</p>`;
    }
  });
});
modal.querySelector('.modal-close').addEventListener('click', () => modal.style.display = 'none');
modal.querySelector('.modal-backdrop').addEventListener('click', () => modal.style.display = 'none');

// ===== Generate =====
document.getElementById('btn-generate').addEventListener('click', async () => {
  const btn = document.getElementById('btn-generate');
  const status = document.getElementById('upload-status');
  btn.disabled = true; status.textContent = '⏳ Uploading & processing...';

  const form = new FormData();
  const fileInput = document.querySelector('.file-input');
  if (!fileInput || !fileInput.files.length) {
    status.textContent = '❌ Please select a file'; btn.disabled = false; return;
  }
  form.append('main', fileInput.files[0]);

  form.append('exf_cut', document.getElementById('cfg-exf').value);
  form.append('etd_cut', document.getElementById('cfg-etd').value);
  form.append('output_cut', document.getElementById('cfg-output').value);
  form.append('gb_cut', document.getElementById('cfg-gb').value);

  document.getElementById('loading').style.display = 'flex';
  try {
    const resp = await fetch('/api/process', { method:'POST', body: form });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);

    allRows = data.rows; allWeeks = data.weeks; weekLabels = data.week_labels;
    document.getElementById('report-section').style.display = 'block';
    document.getElementById('upload-status').textContent = `✅ ${allRows.length} rows`;

    // Save filter & aggregate state
    const savedFilter = {};
    for (const n of ['sku','usage','style','color','type','detail']) {
      const m = document.getElementById(n+'-menu');
      if (!m) continue;
      savedFilter[n] = Array.from(m.querySelectorAll('input[data-val]:checked')).map(cb => cb.dataset.val);
      const menu = m;
      const total = parseInt(menu.dataset.totalVals) || 0;
      savedFilter[n]._all = savedFilter[n].length === total;
    }
    const savedAgg = Array.from(document.querySelectorAll('.pivot-field:checked')).map(cb => cb.value);

    setupDropdowns(); applyFilters(); // no render yet — restore will trigger final render

    // Restore filter state
    for (const n of ['sku','usage','style','color','type','detail']) {
      const vals = savedFilter[n];
      if (!vals) continue;
      const m = document.getElementById(n+'-menu');
      if (!m) continue;
      const total = parseInt(m.dataset.totalVals) || 0;
      if (vals._all || vals.length === total) continue;
      const allCb = m.querySelector('.dropdown-all input');
      if (allCb && allCb.checked) { allCb.checked = false; allCb.dispatchEvent(new Event('change')); }
      for (const val of vals) {
        const menuEl = document.getElementById(n+'-menu');
        const cb = Array.from(menuEl.querySelectorAll('input[data-val]')).find(c => c.dataset.val === val);
        if (cb && !cb.checked) { cb.checked = true; cb.dispatchEvent(new Event('change')); }
      }
    }
    // Restore aggregate state
    document.querySelectorAll('.pivot-field').forEach(cb => {
      const shouldCheck = savedAgg.includes(cb.value);
      if (cb.checked !== shouldCheck) { cb.checked = shouldCheck; cb.dispatchEvent(new Event('change')); }
    });
    // Render with restored filters
    applyFilters(); render();
  } catch(e) {
    status.textContent = `❌ ${e.message}`;
  } finally {
    btn.disabled = false; document.getElementById('loading').style.display = 'none';
  }
});

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
function extractUnique(f, dim, keepEmpty) { const s=new Set(); for(const r of allRows){ if(dim && r._dim!==dim) continue; const v=r[f]; if(v!=null&&(keepEmpty||v!=='')) s.add(v); } return [...s].sort(); }

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
    let h=`<div class="dropdown-search"><input type="text" placeholder="Search..." value="${esc(searchTerm)}"></div>`;
    h+=`<div class="dropdown-all"><input type="checkbox" ${ac?'checked':''}> All (${vals.length})</div>`;
    for(const v of fv) h+=`<label><input type="checkbox" data-val="${v}" ${chk[v]?'checked':''}> ${lbl(v)}</label>`;
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
  return allRows.filter(r=>{
    if(useDim && activeDim && r._dim!==activeDim) return false;
    if(s&&s.length&&!s.includes(r.PN)) return false;
    if(u&&u.length&&!u.includes(r.Usage)) return false;
    if(st&&st.length&&!st.includes(r.Style)) return false;
    if(co&&co.length&&!co.includes(r.Color)) return false;
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

const PIVOT_KEEP = ['Version-Type','Version-Detail','Cut Day'];
const VT_ORDER = {'ExF':0,'Ungated':1,'Gated':2,'CTB':3};
let pivotExpanded = new Set();

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
    return;
  }

  const groups = {};
  for (const r of rows) {
    const grpKey = pivotFields.map(f => r[f] || '(blank)').concat(
      PIVOT_KEEP.map(k => r[k] != null ? String(r[k]) : '')
    ).join('||');
    if (!groups[grpKey]) {
      const g = { fields: {}, weeks: {}, children: [] };
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

  // Data rows
  let html = '', lastGroupStr = '';
  for (const gk of groupKeys) {
    const g = groups[gk];
    const isExp = pivotExpanded.has(gk);

    // Detect aggregate group change for separator
    const curGroupStr = pivotFields.map(f => g.fields[f]).join('||');
    const isNewGroup = curGroupStr !== lastGroupStr;
    lastGroupStr = curGroupStr;

    const vtCls = 'row-' + (g.fields['Version-Type'] || 'ExF');
    const rowCls = `pivot-group-row ${vtCls}${isExp?' pivot-expanded':''}${isNewGroup?' pivot-new-group':''}`;
    html += `<tr class="${rowCls}" data-pkey="${esc(gk)}">`;
    for (const c of pivotColsFiltered) {
      const isLast = c === pivotColsFiltered[pivotColsFiltered.length - 1];
      const ex = isLast || !c.frozen ? ' frozen-last' : '';
      const s = `left:${c._left}px`;
      if (c.key === '_exp') {
        html += `<td class="data-cell pivot-toggle frozen${ex}" style="${s};text-align:center;cursor:pointer;font-size:13px">${isExp?'▾':'▸'}</td>`;
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

  // Delegated toggle click
  tb.onclick = (e) => {
    const td = e.target.closest('.pivot-toggle');
    if (!td) return;
    const tr = td.closest('tr');
    const key = tr.dataset.pkey;
    if (!key) return;
    if (pivotExpanded.has(key)) pivotExpanded.delete(key);
    else pivotExpanded.add(key);
    renderPivotTable();
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
}
function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}

// ===== Column toggles =====
['col-pn','col-usage','col-style','col-color','col-cutday','col-pallet'].forEach(id=>{const e=document.getElementById(id);if(e)e.addEventListener('change',()=>render());});

// ===== Auto-load demo on startup =====
(async function autoLoad() {
  try {
    const resp = await fetch('/demo');
    const blob = await resp.blob();
    const inp = document.querySelector('.file-input');
    if (!inp) return;
    const dt = new DataTransfer();
    dt.items.add(new File([blob], 'input_demo.xlsx', {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
    inp.files = dt.files;
    inp.closest('.upload-card').classList.add('has-file');
    // Auto-generate
    document.getElementById('btn-generate').click();
  } catch(e) {
    console.log('Auto-load demo failed:', e.message);
  }
})();

// ===== Download Excel =====
document.getElementById('btn-dl-excel').addEventListener('click',async()=>{
  const allData=getFilteredRows(false);
  if(allData.length===0)return;
  const btn=document.getElementById('btn-dl-excel');
  btn.textContent='⏳ Generating...';btn.disabled=true;
  try{
    const resp=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:allData,weeks:allWeeks,week_labels:weekLabels})});
    if(!resp.ok)throw new Error(`HTTP ${resp.status}`);
    const blob=await resp.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='report.xlsx';a.click();URL.revokeObjectURL(a.href);
  }catch(e){alert('Download failed: '+e.message);}
  finally{btn.textContent='📥 Download Excel';btn.disabled=false;}
});


