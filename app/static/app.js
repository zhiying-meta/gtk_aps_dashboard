const API_URL = '/api/data';
const ALL_COLS = [
  { key: '_dim', label: 'Dim', width: 50, frozen: true },
  { key: 'PN', label: 'PN', width: 130, frozen: true, toggle: 'col-pn' },
  { key: 'Usage', label: 'Usage', width: 70, frozen: true, toggle: 'col-usage' },
  { key: 'Style', label: 'Style', width: 95, frozen: true, toggle: 'col-style' },
  { key: 'Color', label: 'Color', width: 100, frozen: true, toggle: 'col-color' },
  { key: 'Version-Type', label: 'Version-Type', width: 100, frozen: true },
  { key: 'Version-Detail', label: 'Version-Detail', width: 105, frozen: true },
  { key: 'Cut Day', label: 'Cut Day', width: 75, frozen: true, toggle: 'col-cutday' },
  { key: 'Pallet_Qty', label: 'Pallet', width: 50, frozen: true, toggle: 'col-pallet' },
];
const DIVIDER_COL = { key: '_divider', label: '', width: 5, frozen: true };
const CONFIG = { etd_cut: "Saturday", output_cut: "Wednesday", exf_cut: "Saturday" };

let allRows = [], allWeeks = [], weekLabels = {};
let filteredRows = [];

async function loadData() {
  document.getElementById('loading').style.display = 'flex';
  try {
    const resp = await fetch(API_URL, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(CONFIG)
    });
    const data = await resp.json();
    allRows = data.rows;
    allWeeks = data.weeks;
    weekLabels = data.week_labels;
    setupDropdowns();
    applyFilters();
    renderTable();
    document.getElementById('status').textContent = `✅ ${allRows.length} 行`;
  } catch (err) {
    document.getElementById('status').textContent = `❌ ${err.message}`;
  } finally {
    document.getElementById('loading').style.display = 'none';
  }
}

function setupDropdowns() {
  const options = {
    dim: { items: extractUnique('_dim'), labelMap: { FG: 'FG (SKU)', GB: 'GB' } },
    sku: { items: extractUnique('PN') },
    usage: { items: extractUnique('Usage').filter(Boolean) },
    style: { items: extractUnique('Style') },
    color: { items: extractUnique('Color') },
    type: { items: extractUnique('Version-Type') },
    detail: { items: extractUnique('Version-Detail').filter(Boolean) },
  };
  for (const [name, opt] of Object.entries(options))
    setupDropdown(name, opt.items, opt.labelMap);
}

function extractUnique(field) {
  const s = new Set();
  for (const r of allRows) {
    const v = r[field];
    if (v !== null && v !== undefined && v !== '') s.add(v);
  }
  return [...s].sort();
}

function setupDropdown(name, values, labelMap) {
  const btn = document.getElementById(`${name}-btn`);
  const menu = document.getElementById(`${name}-menu`);
  const countEl = document.getElementById(`${name}-count`);
  if (!btn || !menu) return;
  let checks = {};
  values.forEach(v => checks[v] = true);
  function lbl(v) { return labelMap && labelMap[v] ? labelMap[v] : v; }
  function render() {
    const ac = Object.values(checks).every(Boolean);
    const sc = Object.values(checks).filter(Boolean).length;
    countEl.textContent = sc < values.length ? `${sc}` : '';
    btn.textContent = sc === values.length ? `All (${values.length})` : sc === 0 ? '(none)' : `${sc} selected`;
    let html = `<div class="dropdown-all"><input type="checkbox" ${ac?'checked':''}> All (${values.length})</div>`;
    for (const v of values) html += `<label><input type="checkbox" data-val="${v}" ${checks[v]?'checked':''}> ${lbl(v)}</label>`;
    menu.innerHTML = html;
    menu.querySelector('.dropdown-all input').onchange = function(e) {
      values.forEach(v => checks[v] = e.target.checked); render(); onFilterChange();
    };
    menu.querySelectorAll('label input').forEach(cb => {
      cb.onchange = function() { checks[this.dataset.val] = this.checked; render(); onFilterChange(); };
    });
  }
  btn.onclick = (e) => { e.stopPropagation(); menu.classList.toggle('open'); };
  document.addEventListener('click', () => menu.classList.remove('open'));
  menu.onclick = (e) => e.stopPropagation();
  render();
}

function getDropdownVals(name) {
  const menu = document.getElementById(`${name}-menu`);
  if (!menu) return null;
  const checked = menu.querySelectorAll('input[data-val]:checked');
  if (checked.length === 0) return [];
  const all = menu.querySelectorAll('input[data-val]');
  if (checked.length === all.length) return null;
  return Array.from(checked).map(cb => cb.dataset.val);
}

function isColVisible(col) {
  if (!col.toggle) return true;
  const cb = document.getElementById(col.toggle);
  return !cb || cb.checked;
}

let _ft = null;
function onFilterChange() {
  clearTimeout(_ft);
  _ft = setTimeout(() => { applyFilters(); renderTable(); }, 80);
}

function applyFilters() {
  const fDim = getDropdownVals('dim'), fSku = getDropdownVals('sku'), fUsage = getDropdownVals('usage');
  const fStyle = getDropdownVals('style'), fColor = getDropdownVals('color');
  const fType = getDropdownVals('type'), fDetail = getDropdownVals('detail');
  filteredRows = allRows.filter(r => {
    if (fDim && !fDim.includes(r._dim)) return false;
    if (fSku && !fSku.includes(r.PN)) return false;
    if (fUsage && !fUsage.includes(r.Usage)) return false;
    if (fStyle && !fStyle.includes(r.Style)) return false;
    if (fColor && !fColor.includes(r.Color)) return false;
    if (fType && !fType.includes(r['Version-Type'])) return false;
    if (fDetail && !fDetail.includes(r['Version-Detail'])) return false;
    return true;
  });
  document.getElementById('row-count').textContent = `${filteredRows.length} 行`;
}

function fmtNum(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (isNaN(n)) return '';
  return n === 0 ? '0' : Math.round(n).toLocaleString();
}
function numClass(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (isNaN(n)) return '';
  return n > 0 ? 'num num-pos' : n < 0 ? 'num num-neg' : 'num num-zero';
}

function renderTable() {
  const thead = document.getElementById('table-head');
  const tbody = document.getElementById('table-body');
  const visibleCols = [...ALL_COLS.filter(c => isColVisible(c)), DIVIDER_COL];
  let left = 0;
  for (const c of visibleCols) { c._left = left; left += c.width; }

  let hHtml = '<tr>';
  for (let ci = 0; ci < visibleCols.length; ci++) {
    const col = visibleCols[ci];
    const isDiv = col.key === '_divider';
    const extra = isDiv ? ' divider-col' : (ci === visibleCols.length - 1 || !visibleCols[ci+1].frozen ? ' frozen-last' : '');
    const s = col.frozen ? ` style="left:${col._left}px;min-width:${col.width}px" class="frozen${extra}"` : ` style="min-width:${col.width}px"`;
    hHtml += `<th${s}>${col.label}</th>`;
  }
  for (const w of allWeeks) hHtml += `<th style="min-width:78px">${weekLabels[w]||w}</th>`;
  thead.innerHTML = hHtml + '</tr>';

  if (filteredRows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="999" style="text-align:center;padding:40px;color:#94a3b8">无匹配数据</td></tr>';
    return;
  }

  const groupBy = document.getElementById('group-by').value;
  let displayRows = filteredRows, groupHeaders = [];
  if (groupBy) {
    const groups = {};
    for (const r of filteredRows) {
      const gv = r[groupBy] || '(blank)';
      (groups[gv] = groups[gv] || []).push(r);
    }
    displayRows = [];
    for (const k of Object.keys(groups).sort()) {
      groupHeaders.push({label:`${groupBy}: ${k}`, count: groups[k].length});
      displayRows.push(...groups[k]);
    }
  }

  let html = '', grpIdx = 0, rowInGrp = 0, lastPN = null;
  for (let ri = 0; ri < displayRows.length; ri++) {
    const r = displayRows[ri], type = r['Version-Type'], dim = r._dim || 'FG';
    if (groupBy && groupHeaders.length > 0 && grpIdx < groupHeaders.length) {
      if (rowInGrp === 0) {
        html += '<tr class="row-group">';
        for (let ci = 0; ci < visibleCols.length; ci++) {
          const col = visibleCols[ci];
          const extra = col.key === '_divider' ? ' divider-col' : '';
          const s = col.frozen ? ` style="left:${col._left}px" class="frozen${extra}"` : '';
          html += `<td${s}>${ci === 0 ? `📁 ${groupHeaders[grpIdx].label} (${groupHeaders[grpIdx].count})` : ''}</td>`;
        }
        for (const w of allWeeks) html += '<td></td>';
        html += '</tr>';
      }
      if (++rowInGrp >= groupHeaders[grpIdx].count) { grpIdx++; rowInGrp = 0; }
    }

    const isNewPN = r.PN !== lastPN;
    if (isNewPN) lastPN = r.PN;
    html += `<tr class="row-${type}${isNewPN ? ' row-newpn' : ''}">`;

    for (let ci = 0; ci < visibleCols.length; ci++) {
      const col = visibleCols[ci];
      const isDiv = col.key === '_divider';
      const extra = isDiv ? ' divider-col' : (ci === visibleCols.length - 1 || !visibleCols[ci+1].frozen ? ' frozen-last' : '');
      const s = col.frozen ? ` style="left:${col._left}px" class="frozen data-cell${extra}"` : ' class="data-cell"';
      let inner = '';
      if (!isDiv) {
        const val = r[col.key];
        if (col.key === '_dim') inner = `<span class="dim-badge dim-${dim}">${dim}</span>`;
        else if (col.key === 'Version-Type') inner = `<span class="type-badge type-${type}">${type}</span>`;
        else if (col.key === 'PN') inner = esc(String(val ?? ''));
        else if (['Pallet_Qty','Cut Day','Usage'].includes(col.key)) inner = val != null ? String(val) : '';
        else inner = esc(String(val ?? ''));
      }
      html += `<td${s}>${inner}</td>`;
    }
    for (const w of allWeeks) {
      const v = r[w];
      html += `<td class="data-cell ${numClass(v)}">${fmtNum(v)}</td>`;
    }
    html += '</tr>';
  }
  tbody.innerHTML = html;
}

function esc(s) { return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') : ''; }

document.getElementById('btn-csv').onclick = async () => {
  if (filteredRows.length === 0) return;
  const btn = document.getElementById('btn-csv');
  btn.textContent = '⏳ 生成中...'; btn.disabled = true;
  try {
    const resp = await fetch('/api/download', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(CONFIG)
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'report.xlsx';
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    alert('下载失败: ' + e.message);
  } finally {
    btn.textContent = '📥 下载 Excel';
    btn.disabled = false;
  }
};

['col-pn','col-usage','col-style','col-color','col-cutday','col-pallet','group-by'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('change', renderTable);
});

loadData();
