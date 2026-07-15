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
let allRows=[], allWeeks=[], weekLabels={}, filteredRows=[], activeDim='FG';

// ===== Upload: mark files =====
document.querySelectorAll('.file-input').forEach(inp => {
  inp.addEventListener('change', () => {
    const card = inp.closest('.upload-card');
    card.classList.toggle('has-file', inp.files.length > 0);
  });
});

// ===== Schema Modal =====
const modal = document.getElementById('schema-modal');
document.querySelectorAll('.schema-btn').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    const sheet = btn.dataset.file;
    document.getElementById('schema-title').textContent = sheet + ' - 字段说明';
    document.getElementById('schema-body').innerHTML = '<p style="color:#94a3b8">加载中...</p>';
    modal.style.display = 'flex';
    try {
      const resp = await fetch('/api/schema');
      const data = await resp.json();
      const sc = data[sheet];
      if (!sc) { document.getElementById('schema-body').innerHTML = '<p>未找到字段说明</p>'; return; }
      let html = '<table><tr><th>字段</th><th>类型</th><th>说明</th><th>示例</th></tr>';
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
  btn.disabled = true; status.textContent = '⏳ 上传处理中...';

  const form = new FormData();
  const fileInput = document.querySelector('.file-input');
  if (!fileInput || !fileInput.files.length) {
    status.textContent = '❌ 请选择输入文件'; btn.disabled = false; return;
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
    document.getElementById('upload-status').textContent = `✅ ${allRows.length} 行`;
    setupDropdowns(); applyFilters(); renderTable();
  } catch(e) {
    status.textContent = `❌ ${e.message}`;
  } finally {
    btn.disabled = false; document.getElementById('loading').style.display = 'none';
  }
});

// ===== Filters =====
function setupDropdowns() {
  for (const [name, opts] of Object.entries({
    sku: { items:extractUnique('PN') },
    usage: { items:extractUnique('Usage').filter(Boolean) },
    style: { items:extractUnique('Style') },
    color: { items:extractUnique('Color') },
    type: { items:extractUnique('Version-Type') },
    detail: { items:extractUnique('Version-Detail').filter(Boolean) },
  })) setupDropdown(name, opts.items, opts.map);
}
function extractUnique(f) { const s=new Set(); for(const r of allRows){ const v=r[f]; if(v!=null&&v!=='') s.add(v); } return [...s].sort(); }

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
    btn.textContent=vals.length===0?'-':(sc===vals.length?`All (${vals.length})`:sc===0?'(none)':`${sc} selected`);
    const fv=filtered();
    let h=`<div class="dropdown-search"><input type="text" placeholder="搜索..." value="${esc(searchTerm)}"></div>`;
    h+=`<div class="dropdown-all"><input type="checkbox" ${ac?'checked':''}> All (${vals.length})</div>`;
    for(const v of fv) h+=`<label><input type="checkbox" data-val="${v}" ${chk[v]?'checked':''}> ${lbl(v)}</label>`;
    if (vals.length===0) h+=`<div style="padding:8px;color:#94a3b8;font-size:12px">无可用值</div>`;
    else if (fv.length===0) h+=`<div style="padding:8px;color:#94a3b8;font-size:12px">无匹配</div>`;
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
function fltr() { clearTimeout(_ft); _ft=setTimeout(()=>{applyFilters();renderTable();},80); }
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
  document.getElementById('row-count').textContent=`${filteredRows.length} 行`;
}
function setDimTab(dim) {
  activeDim = dim;
  document.querySelectorAll('.dim-tab').forEach(t => t.classList.toggle('active', t.dataset.dim === dim));
  applyFilters(); renderTable();
}
document.querySelectorAll('.dim-tab').forEach(tab => {
  tab.addEventListener('click', () => setDimTab(tab.dataset.dim));
});

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
  if(filteredRows.length===0){tb.innerHTML='<tr><td colspan="999" style="text-align:center;padding:40px;color:#94a3b8">无匹配数据</td></tr>';return;}
  const grp=document.getElementById('group-by').value; let dr=filteredRows,gh=[];
  if(grp){const gs={};for(const r of filteredRows){(gs[r[grp]||'(blank)']=gs[r[grp]||'(blank)']||[]).push(r);}dr=[];for(const k of Object.keys(gs).sort()){gh.push({label:`${grp}: ${k}`,count:gs[k].length});dr.push(...gs[k]);}}
  let html='',gi=0,ri=0,lpn=null;
  for(let i=0;i<dr.length;i++){
    const r=dr[i],tp=r['Version-Type'],dm=r._dim||'FG';
    if(grp&&gh.length>0&&gi<gh.length){if(ri===0){html+='<tr class="row-group">';for(let ci=0;ci<vc.length;ci++){const c=vc[ci];const ex=c.key==='_divider'?' divider-col':'';const s=c.frozen?` style="left:${c._left}px" class="frozen${ex}"`:'';html+=`<td${s}>${ci===0?`📁 ${gh[gi].label} (${gh[gi].count})`:''}</td>`;}for(const w of allWeeks)html+='<td></td>';html+='</tr>';}if(++ri>=gh[gi].count){gi++;ri=0;}}
    const isNP=r.PN!==lpn;if(isNP)lpn=r.PN;
    html+=`<tr class="row-${tp}${isNP?' row-newpn':''}">`;
    for(let ci=0;ci<vc.length;ci++){const c=vc[ci];const isDiv=c.key==='_divider';const ex=isDiv?' divider-col':(ci===vc.length-1||!vc[ci+1].frozen?' frozen-last':'');const s=c.frozen?` style="left:${c._left}px" class="frozen data-cell${ex}"`:' class="data-cell"';let inn='';if(!isDiv){const v=r[c.key];if(c.key==='_dim')inn=`<span class="dim-badge dim-${dm}">${dm}</span>`;else if(c.key==='Version-Type')inn=`<span class="type-badge type-${tp}">${tp}</span>`;else if(c.key==='PN')inn=esc(String(v??''));else if(['Pallet_Qty','Cut Day','Usage'].includes(c.key))inn=v!=null?String(v):'';else inn=esc(String(v??''));}html+=`<td${s}>${inn}</td>`;}
    for(const w of allWeeks){const v=r[w];html+=`<td class="data-cell ${numCls(v)}">${fmtNum(v)}</td>`;}
    html+='</tr>';
  }
  tb.innerHTML=html;
}
function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}

// ===== Column toggles & group =====
['col-pn','col-usage','col-style','col-color','col-cutday','col-pallet','group-by'].forEach(id=>{const e=document.getElementById(id);if(e)e.addEventListener('change',renderTable);});

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
  btn.textContent='⏳ 生成中...';btn.disabled=true;
  try{
    const resp=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:allData,weeks:allWeeks,week_labels:weekLabels})});
    if(!resp.ok)throw new Error(`HTTP ${resp.status}`);
    const blob=await resp.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='report.xlsx';a.click();URL.revokeObjectURL(a.href);
  }catch(e){alert('下载失败: '+e.message);}
  finally{btn.textContent='📥 下载 Excel';btn.disabled=false;}
});


