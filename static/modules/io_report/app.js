let ioCache = null;
let ioCat = 'FG';
let ioDim = 'ITEM_NO';
let ioColMode = 'shift';
let ioReportType = 'INPUT';
let ioData = null;

// ===== DOM refs =====
const ioSection = document.getElementById('io-report-section');
const ioLoadBtn = document.getElementById('io-load');
const ioStatus = document.getElementById('io-status');
const ioDimSel = document.getElementById('io-dim');
const ioColSel = document.getElementById('io-col-mode');
const ioFilterSel = document.getElementById('io-filter');
const ioTh = document.getElementById('io-table-head');
const ioTb = document.getElementById('io-table-body');

// ===== Category tabs =====
ioSection.querySelectorAll('[data-io-cat]').forEach(tab => {
  tab.addEventListener('click', () => {
    ioSection.querySelectorAll('[data-io-cat]').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    ioCat = tab.dataset.ioCat;
    loadIOData();
  });
});

// ===== Report type tabs =====
ioSection.querySelectorAll('.io-report-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    ioSection.querySelectorAll('.io-report-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    ioReportType = tab.dataset.ioReport;
    renderIOTable();
  });
});

// ===== Dimension / Column mode changes =====
ioDimSel.addEventListener('change', () => { ioDim = ioDimSel.value; loadIOData(); });
ioColSel.addEventListener('change', () => { ioColMode = ioColSel.value; loadIOData(); });
ioLoadBtn.addEventListener('click', () => loadIOData());

// ===== Filter change =====
ioFilterSel.addEventListener('change', () => loadIOData());

// ===== Download =====
document.getElementById('io-dl-excel').addEventListener('click', downloadIOExcel);

// ===== Listen for module activation =====
document.addEventListener('module-change', (e) => {
  if (e.detail.module === 'io-report' && !ioData) {
    loadMeta();
  }
});
document.addEventListener('sidebar-resized', () => {
  // no-op for now
});

function loadMeta() {
  fetch('/api/io/meta')
    .then(r => r.json())
    .then(data => {
      ioCache = data;
      ioDimSel.value = ioDim;
      // Populate filter dropdown
      const items = ioCat === 'FG' ? data.items_fg : data.items_gb;
      const html = ['<option value="">All</option>', ...items.map(i => `<option value="${i}">${i}</option>`)].join('');
      ioFilterSel.innerHTML = html;
      loadIOData();
    })
    .catch(err => ioStatus.textContent = '❌ ' + err.message);
}

function loadIOData() {
  ioStatus.textContent = '⏳ Loading...';
  const filter = ioFilterSel.value || null;

  fetch('/api/io/load', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dim: ioDim, col_mode: ioColMode, cat: ioCat, dim_filter: filter ? [filter] : null })
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) throw new Error(data.error);
      ioData = data;
      renderIOTable();
      ioStatus.textContent = `✅ ${data.meta.fg_items ? data.meta.fg_items.length : data.meta.gb_items.length} items`;
    })
    .catch(err => ioStatus.textContent = '❌ ' + err.message);
}

function renderIOTable() {
  if (!ioData || !ioData.reports) { ioTb.innerHTML = '<tr><td colspan="999" style="text-align:center;padding:40px;color:#94a3b8">No data</td></tr>'; return; }
  const report = ioData.reports[ioReportType];
  if (!report || !report.rows) { ioTb.innerHTML = '<tr><td colspan="999" style="text-align:center;padding:40px;color:#94a3b8">No data</td></tr>'; return; }

  const cols = report.cols;
  const rows = report.rows;
  const rowKeys = Object.keys(rows).sort();

  // Header
  const dimLabel = ioDimSel.options[ioDimSel.selectedIndex].text;
  let h = `<tr><th class="frozen" style="left:0;min-width:140px;z-index:16">${dimLabel}</th>`;
  for (const c of cols) h += `<th style="min-width:80px">${c}</th>`;
  ioTh.innerHTML = h + '</tr>';

  // Body
  let html = '';
  for (const key of rowKeys) {
    const vals = rows[key];
    html += '<tr>';
    html += `<td class="frozen" style="left:0;font-weight:500;background:#fff;z-index:5">${esc(key)}</td>`;
    for (const c of cols) {
      const v = vals[c];
      const cls = v > 0 ? 'num num-pos' : v < 0 ? 'num num-neg' : 'num num-zero';
      html += `<td class="${cls}">${v != null ? Math.round(v).toLocaleString() : ''}</td>`;
    }
    html += '</tr>';
  }
  ioTb.innerHTML = html;
}

function downloadIOExcel() {
  if (!ioData) return;
  const report = ioData.reports[ioReportType];
  if (!report) return;
  const cols = report.cols;
  const rows = report.rows;
  const rowKeys = Object.keys(rows).sort();

  let csv = '\uFEFF' + dimLabel();
  for (const c of cols) csv += ',' + c;
  csv += '\n';
  for (const key of rowKeys) {
    csv += esc(key);
    for (const c of cols) {
      csv += ',' + (rows[key][c] ?? '');
    }
    csv += '\n';
  }

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `io_report_${ioReportType}_${ioCat}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function dimLabel() {
  return ioDimSel.options[ioDimSel.selectedIndex].text;
}

function esc(s) { return s ? String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') : ''; }
