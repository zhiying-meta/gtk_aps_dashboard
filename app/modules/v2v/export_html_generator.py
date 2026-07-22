"""
Export HTML Generator - Full Featured Standalone Export
Generates self-contained HTML with embedded data and full UI
"""
import json
import os

def generate_full_featured_html(embedded_data, table_defs, css_global, css_v2v, previous_name, latest_name, generated_at, job_id, summary_count, overall):
    """
    Generate full featured HTML export
    embedded_data: dict with meta, summary, matrices, vertical_diffs
    table_defs: dict
    css_global, css_v2v: strings
    previous_name, latest_name, generated_at, job_id: str
    summary_count: int
    overall: dict
    """
    embedded_json_str = json.dumps(embedded_data, ensure_ascii=False, default=str)
    embedded_json_str = embedded_json_str.replace("</", "<\/")

    # Generate static summary cards as fallback
    static_summary_html = ""
    try:
        for table_key, summ in embedded_data.get('summary', {}).items():
            def_info = table_defs.get(table_key, {})
            display_name = 'BOH' if table_key=='balance' else def_info.get('display_name', table_key)
            icon = def_info.get('icon','📄')
            cat = def_info.get('category','input')
            total_a = summ.get('total_a',0)
            total_b = summ.get('total_b',0)
            added = summ.get('added',0)
            deleted = summ.get('deleted',0)
            modified = summ.get('modified',0)
            has_diff = (total_a != total_b) or (added+deleted+modified>0)
            card_class = 'has-diff' if has_diff else 'no-diff'
            static_summary_html += '<div class="v2v-summary-card ' + card_class + '" data-table="' + str(table_key) + '"><div class="v2v-summary-card-header"><span class="v2v-summary-card-title"><span class="v2v-summary-card-icon">' + str(icon) + '</span> ' + str(display_name) + '</span><span class="v2v-summary-card-category ' + str(cat) + '">' + str(cat) + '</span></div><div class="v2v-summary-stats"><div class="v2v-stat-row"><span class="v2v-stat-label">Previous</span><span class="v2v-stat-value">' + str(total_a) + ' rows</span></div><div class="v2v-stat-row"><span class="v2v-stat-label">Latest</span><span class="v2v-stat-value">' + str(total_b) + ' rows</span></div><div style="height:1px;background:#f1f5f9;margin:4px 0"></div><div class="v2v-stat-row"><span class="v2v-stat-label">Added</span><span class="v2v-stat-value add">+' + str(added) + '</span></div><div class="v2v-stat-row"><span class="v2v-stat-label">Deleted</span><span class="v2v-stat-value del">-' + str(deleted) + '</span></div><div class="v2v-stat-row"><span class="v2v-stat-label">Modified</span><span class="v2v-stat-value mod">' + str(modified) + '</span></div></div></div>'
    except Exception as e:
        static_summary_html = '<div>Error generating static summary: ' + str(e) + '</div>'

    # Use a template with placeholders to avoid f-string escaping issues with JS


    table_defs_json = json.dumps(table_defs, ensure_ascii=False)

    overall_added = overall.get('total_added', 0) if isinstance(overall, dict) else 0
    overall_deleted = overall.get('total_deleted', 0) if isinstance(overall, dict) else 0
    overall_modified = overall.get('total_modified', 0) if isinstance(overall, dict) else 0

    # Use a template with placeholders to avoid f-string escaping issues with JS ${}
    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V2V Comparison - __PREV__ vs __LATEST__ (Full Featured Export)</title>
<style>
__CSS_GLOBAL__
__CSS_V2V__
/* Export specific styles */
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin:0; padding:0; background:#f8fafc; color:#0f172a; }
.export-header { background:#0f172a; color:white; padding:16px 24px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; }
.export-header h1 { margin:0; font-size:18px; }
.export-header .meta { font-size:12px; color:#94a3b8; }
.export-header .meta b { color:#e2e8f0; }
.export-container { max-width: 1600px; margin:0 auto; padding:16px; }
.export-banner { background:#eff6ff; border:1px solid #bfdbfe; padding:10px 14px; border-radius:8px; margin-bottom:16px; font-size:12px; color:#1e40af; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
.export-section { background:white; border-radius:8px; border:1px solid #e2e8f0; padding:16px; margin-bottom:16px; box-shadow:0 1px 2px rgba(0,0,0,0.04); }
.export-section h2 { margin:0 0 12px 0; font-size:15px; font-weight:600; }
.import-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media(max-width:900px){ .import-grid { grid-template-columns:1fr; } }
.file-drop { border:2px dashed #cbd5e1; border-radius:8px; padding:16px; background:#f8fafc; text-align:center; }
.file-drop.dragover { border-color:#0f172a; background:#eff6ff; }
.file-drop input { display:none; }
.file-list { margin-top:8px; font-size:11px; text-align:left; max-height:120px; overflow:auto; }
.v2v-table-wrapper { max-height:600px; overflow:auto; border:1px solid #e2e8f0; border-radius:6px; }
.v2v-table th { position:sticky; top:0; background:#1e293b; color:white; z-index:5; }
.cell-has-change { background:#fef08a !important; border:1px solid #facc15; text-align:center; }
.badge-has-change { background:#fef08a; color:#854d0e; border:1px solid #facc15; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }
.footer { text-align:center; font-size:11px; color:#94a3b8; padding:20px; }
</style>
<script id="v2v-embedded-data" type="application/json">__EMBEDDED_JSON__</script>
<script id="v2v-table-defs" type="application/json">__TABLE_DEFS_JSON__</script>
</head>
<body>
<div class="export-header">
  <div>
    <h1>🔍 V2V Comparison - Full Featured Export</h1>
    <div class="meta">
      <span><b>Previous:</b> __PREV__</span> &nbsp; vs &nbsp; <span><b>Latest:</b> __LATEST__</span> |
      <span><b>Generated:</b> __GEN_AT__</span> | <span><b>Job:</b> __JOB_ID_SHORT__</span> |
      <span>Tables: __SUMMARY_COUNT__ | Added __OVERALL_ADDED__ Del __OVERALL_DELETED__ Mod __OVERALL_MODIFIED__</span>
    </div>
  </div>
  <div style="display:flex; gap:8px;">
    <button onclick="window.print()" style="padding:6px 12px; border:1px solid #334155; border-radius:6px; background:#1e293b; color:white; cursor:pointer; font-size:12px;">🖨️ Print</button>
    <button onclick="downloadEmbeddedJson()" style="padding:6px 12px; border:1px solid #334155; border-radius:6px; background:#1e293b; color:white; cursor:pointer; font-size:12px;">📥 Download JSON</button>
  </div>
</div>

<div class="export-container">
  <div class="export-banner">
    <div>💡 This is a <b>standalone HTML export</b> with embedded comparison data. You can view offline, and also <b>import new Excel files</b> to re-compare (like BTO-Dashboard). No server needed for viewing; SheetJS CDN required for import.</div>
    <div style="font-size:11px; color:#64748b;">Export Version: Full Featured | Week/Month = Yellow-only indicator | Day/Shift = Detailed</div>
  </div>

  <div class="export-section" id="import-section">
    <h2>📁 Import New Versions for V2V (Client-Side, No Server)</h2>
    <p style="font-size:11px; color:#64748b; margin-bottom:12px;">Select Previous and Latest version Excel files (multiple .xlsx). Auto-detect tables by filename keywords and re-compare client-side.</p>
    <div class="import-grid">
      <div class="file-drop" id="drop-a">
        <div style="font-weight:600; margin-bottom:8px;">Previous Version (A)</div>
        <div style="font-size:11px; color:#64748b; margin-bottom:8px;">Drop .xlsx files here or click to select</div>
        <input type="file" id="files-a" multiple accept=".xlsx" />
        <button onclick="document.getElementById('files-a').click()" style="padding:6px 12px; background:#0f172a; color:white; border:none; border-radius:6px; cursor:pointer; font-size:12px;">📂 Choose Previous Files</button>
        <div class="file-list" id="list-a"></div>
      </div>
      <div class="file-drop" id="drop-b">
        <div style="font-weight:600; margin-bottom:8px;">Latest Version (B)</div>
        <div style="font-size:11px; color:#64748b; margin-bottom:8px;">Drop .xlsx files here or click to select</div>
        <input type="file" id="files-b" multiple accept=".xlsx" />
        <button onclick="document.getElementById('files-b').click()" style="padding:6px 12px; background:#2563eb; color:white; border:none; border-radius:6px; cursor:pointer; font-size:12px;">📂 Choose Latest Files</button>
        <div class="file-list" id="list-b"></div>
      </div>
    </div>
    <div style="margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;">
      <button id="btn-recompare" style="padding:8px 18px; background:#0f172a; color:white; border:none; border-radius:6px; cursor:pointer; font-weight:600;">▶ Re-Compare Client-Side</button>
      <button id="btn-reset" style="padding:8px 14px; background:#f1f5f9; border:1px solid #cbd5e1; border-radius:6px; cursor:pointer;">↺ Reset to Embedded Data</button>
      <span id="import-status" style="font-size:12px; color:#64748b; padding:8px;"></span>
    </div>
  </div>

  <div class="export-section">
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
      <h2 style="margin:0;">📊 Summary Dashboard</h2>
      <div class="v2v-granularity-toggle" id="granularity-toggle">
        <button data-granularity="monthly">Month</button>
        <button data-granularity="week" class="active">Week</button>
        <button data-granularity="day">Day</button>

      </div>
    </div>
    <div class="v2v-summary-grid" id="summary-grid">__STATIC_SUMMARY__</div>
  </div>

  <div class="export-section" id="detail-section">
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px;">
      <h2 style="margin:0;">🔍 Detail Comparison</h2>
      <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
        <label style="font-size:12px;">Change Type:
          <select id="filter-changetype" style="padding:4px 8px; border:1px solid #cbd5e1; border-radius:4px; font-size:12px;">
            <option value="ALL">All</option>
            <option value="ADDED">Added</option>
            <option value="DELETED">Deleted</option>
            <option value="MODIFY">Modified</option>
            <option value="HAS_CHANGE">Has Change (Week/Month)</option>
          </select>
        </label>
        <label style="font-size:12px;">SKU Category:
          <select id="filter-sku" style="padding:4px 8px; border:1px solid #cbd5e1; border-radius:4px; font-size:12px;">
            <option value="ALL">All SKU</option>
            <option value="MATERIAL">Material 3010*</option>
            <option value="FRAME">Frame FR-*</option>
            <option value="GB">GB</option>
            <option value="LT">LT</option>
            <option value="RT">RT</option>
            <option value="FG">FG SK-*</option>
          </select>
        </label>
        <label style="font-size:12px;">Line Category:
          <select id="filter-line" style="padding:4px 8px; border:1px solid #cbd5e1; border-radius:4px; font-size:12px;">
            <option value="ALL">All Lines</option>
            <option value="AL1">AL1</option><option value="AL2">AL2</option><option value="AL3">AL3</option><option value="AL4">AL4</option>
            <option value="AL5">AL5</option><option value="AL6">AL6</option><option value="AL7">AL7</option><option value="AL8">AL8</option>
            <option value="AL9">AL9</option><option value="AL10">AL10</option><option value="ML2">ML2</option><option value="ML5">ML5</option>
          </select>
        </label>
      </div>
    </div>
    <div class="v2v-detail-tabs" id="detail-tabs"></div>
    <div id="detail-content" style="margin-top:12px;"></div>
  </div>

  <div class="footer">
    Generated by V2V Comparison Tool | Job __JOB_ID__ | __GEN_AT__ | __PREV__ vs __LATEST__<br>
    This HTML is self-contained with embedded data and full UI. Import new files to re-compare client-side (like BTO-Dashboard).<br>
    Weekly/Monthly for BOH/Plan Input/Plan Output shows <span style="background:#fef08a; padding:1px 6px; border-radius:4px; border:1px solid #facc15;">Yellow</span> if any change inside period, daily/shift shows detailed numbers.
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
<script>
const EMBEDDED_DATA = JSON.parse(document.getElementById('v2v-embedded-data').textContent);
const TABLE_DEFS = JSON.parse(document.getElementById('v2v-table-defs').textContent);
let currentState = {
  granularity: 'week',
  activeTable: Object.keys(EMBEDDED_DATA.summary)[0] || 'bom',
  filters: { changeType: 'ALL', skuCategory: 'ALL', lineCategory: 'ALL' },
  isClientSide: false,
  clientData: null
};

function esc(s) {
  if (s==null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function downloadEmbeddedJson() {
  const blob = new Blob([JSON.stringify(EMBEDDED_DATA, null, 2)], {type:'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  const meta = EMBEDDED_DATA.meta || {};
  a.download = 'V2V_' + (meta.previous_name||'prev') + '_vs_' + (meta.latest_name||'latest') + '_' + new Date().toISOString().slice(0,10) + '.json';
  a.click(); URL.revokeObjectURL(a.href);
}

function renderSummary() {
  const summary = EMBEDDED_DATA.summary;
  const grid = document.getElementById('summary-grid');
  if (!grid) return;
  const sortedKeys = Object.keys(summary).sort((a,b)=>{
    const catA = (TABLE_DEFS[a]?.category||'input');
    const catB = (TABLE_DEFS[b]?.category||'input');
    if (catA!==catB) return catA==='input'?-1:1;
    return 0;
  });
  let html='';
  for (const key of sortedKeys) {
    const s = summary[key];
    const def = TABLE_DEFS[key] || {display_name:key, icon:'📄', category:'input'};
    const displayName = key==='balance' ? 'BOH' : def.display_name;
    let hasDiff = (s.total_a !== s.total_b) || ((s.added||0)+(s.deleted||0)+(s.modified||0)>0);
    const cardClass = hasDiff ? 'has-diff' : 'no-diff';
    html += '<div class="v2v-summary-card ' + (currentState.activeTable===key?'active':'') + ' ' + cardClass + '" data-table="' + key + '" onclick="selectTable(\'' + key + '\')">' +
      '<div class="v2v-summary-card-header"><span class="v2v-summary-card-title"><span class="v2v-summary-card-icon">' + (def.icon||'📄') + '</span> ' + displayName + '</span><span class="v2v-summary-card-category ' + def.category + '">' + def.category + '</span></div>' +
      '<div class="v2v-summary-stats">' +
        '<div class="v2v-stat-row"><span class="v2v-stat-label">Previous</span><span class="v2v-stat-value">' + (s.total_a||0) + ' rows</span></div>' +
        '<div class="v2v-stat-row"><span class="v2v-stat-label">Latest</span><span class="v2v-stat-value">' + (s.total_b||0) + ' rows</span></div>' +
        '<div style="height:1px;background:#f1f5f9;margin:4px 0"></div>' +
        '<div class="v2v-stat-row"><span class="v2v-stat-label">Added</span><span class="v2v-stat-value add">+' + (s.added||0) + '</span></div>' +
        '<div class="v2v-stat-row"><span class="v2v-stat-label">Deleted</span><span class="v2v-stat-value del">-' + (s.deleted||0) + '</span></div>' +
        '<div class="v2v-stat-row"><span class="v2v-stat-label">Modified</span><span class="v2v-stat-value mod">' + (s.modified||0) + '</span></div>' +
      '</div>' +
      '<div class="v2v-progress"><div class="v2v-progress-bar ' + (hasDiff?'has-diff':'') + '" style="width:' + (hasDiff?'100%':'0%') + '"></div></div>' +
    '</div>';
  }
  grid.innerHTML = html;
}

function renderTabs() {
  const summary = EMBEDDED_DATA.summary;
  const tabsEl = document.getElementById('detail-tabs');
  if (!tabsEl) return;
  const groups = {input:[], output:[]};
  for (const [key,s] of Object.entries(summary)) {
    const def = TABLE_DEFS[key] || {display_name:key, category:'input'};
    const cat = def.category || 'input';
    if (!groups[cat]) groups[cat]=[];
    groups[cat].push([key,s]);
  }
  let html='';
  if (groups.input.length>0) {
    html += '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-bottom:8px"><span style="font-size:12px;font-weight:600;margin-right:8px;min-width:50px">Input:</span>';
    for (const [key,s] of groups.input) {
      const def = TABLE_DEFS[key] || {display_name:key};
      const displayName = key==='balance'?'BOH':def.display_name;
      let hasDiff = (s.total_a!==s.total_b) || ((s.added||0)+(s.deleted||0)+(s.modified||0)>0);
      const cls = hasDiff ? 'has-diff' : 'no-diff';
      html += '<button class="v2v-detail-tab ' + (currentState.activeTable===key?'active':'') + ' ' + cls + '" onclick="selectTable(\'' + key + '\')">' + displayName + '</button>';
    }
    html += '</div>';
  }
  if (groups.output.length>0) {
    html += '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px"><span style="font-size:12px;font-weight:600;margin-right:8px;min-width:50px">Output:</span>';
    for (const [key,s] of groups.output) {
      const def = TABLE_DEFS[key] || {display_name:key};
      const displayName = key==='balance'?'BOH':def.display_name;
      let hasDiff = (s.total_a!==s.total_b) || ((s.added||0)+(s.deleted||0)+(s.modified||0)>0);
      const cls = hasDiff ? 'has-diff' : 'no-diff';
      html += '<button class="v2v-detail-tab ' + (currentState.activeTable===key?'active':'') + ' ' + cls + '" onclick="selectTable(\'' + key + '\')">' + displayName + '</button>';
    }
    html += '</div>';
  }
  tabsEl.innerHTML = html;
}

function selectTable(tableName) {
  currentState.activeTable = tableName;
  document.querySelectorAll('.v2v-summary-card').forEach(c=>c.classList.toggle('active', c.dataset.table===tableName));
  renderTabs();
  renderSummary();
  loadDetail(tableName);
}
window.selectTable = selectTable;

function isHorizontalTable(t) {
  return ['balance','boh','plan_output','plan_input','fcst'].includes(t);
}

function loadDetail(tableName) {
  if (isHorizontalTable(tableName)) {
    renderHorizontal(tableName);
  } else {
    renderVertical(tableName);
  }
}

function matchesSkuCategory(sku, category) {
  if (!category || category==='ALL') return true;
  const cats = category.split(',').map(s=>s.trim()).filter(Boolean);
  if (cats.includes('ALL')) return true;
  const v = String(sku);
  for (const c of cats) {
    const cu = c.toUpperCase();
    if (cu==='MATERIAL' && v.startsWith('3010')) return true;
    if (cu==='FRAME' && v.startsWith('FR-')) return true;
    if (cu==='GB' && v.startsWith('GB-')) return true;
    if (cu==='LT' && v.startsWith('LT-')) return true;
    if (cu==='RT' && v.startsWith('RT-')) return true;
    if (cu==='FG' && v.startsWith('SK-')) return true;
    if (v.startsWith(c)) return true;
  }
  return false;
}

function renderHorizontal(tableName) {
  const wrapper = document.getElementById('detail-content');
  if (!wrapper) return;
  const gran = currentState.granularity;
  const dataSource = currentState.isClientSide && currentState.clientData && currentState.clientData.matrices && currentState.clientData.matrices[tableName] && currentState.clientData.matrices[tableName][gran] ? currentState.clientData.matrices[tableName][gran] : (EMBEDDED_DATA.matrices[tableName] && EMBEDDED_DATA.matrices[tableName][gran] ? EMBEDDED_DATA.matrices[tableName][gran] : (EMBEDDED_DATA.matrices[tableName] && EMBEDDED_DATA.matrices[tableName]['week'] ? EMBEDDED_DATA.matrices[tableName]['week'] : (EMBEDDED_DATA.matrices[tableName] && EMBEDDED_DATA.matrices[tableName]['day'] ? EMBEDDED_DATA.matrices[tableName]['day'] : null)));
  if (!dataSource || dataSource.error) {
    wrapper.innerHTML = '<div class="v2v-status ' + (dataSource && dataSource.error ? 'error' : 'info') + '">' + (dataSource && dataSource.error ? 'Error: ' + esc(dataSource.error) : 'No data for ' + esc(tableName) + ' ' + esc(gran)) + '</div>';
    return;
  }
  const timeBuckets = dataSource.time_buckets || [];
  const bucketLabels = dataSource.bucket_labels || timeBuckets;
  const skuListRaw = dataSource.sku_list || [];
  const matrix = dataSource.matrix || {};
  const summary = dataSource.summary || {};
  const displayMode = dataSource.display_mode || (['week','month','monthly'].indexOf(gran)>=0 && ['balance','plan_output','plan_input'].indexOf(tableName)>=0 ? 'has_change' : 'detailed');
  const isHasChange = displayMode === 'has_change';

  const skuFilter = currentState.filters.skuCategory || 'ALL';
  const skuList = skuListRaw.filter(sku => matchesSkuCategory(sku, skuFilter));

  if (skuList.length===0) {
    wrapper.innerHTML = '<div class="v2v-status success">No diff for ' + esc(tableName) + ' with filters SKU:' + esc(skuFilter) + ' Granularity:' + esc(gran) + '</div><div style="font-size:11px;color:#64748b;padding:8px;">Total after filter: 0 / Original ' + (summary.total_original_skus||skuListRaw.length) + '</div>';
    return;
  }

  let html = '';
  if (isHasChange) {
    html += '<div class="v2v-legend"><div class="v2v-legend-item"><div class="v2v-legend-color" style="background:#fef08a;border-color:#facc15;width:18px;height:18px"></div><span style="font-weight:600">Yellow = Has Change in this ' + (gran==='week'?'Week':'Month') + ' (any ADD/DEL/MOD inside period - no numbers)</span></div><div style="margin-left:auto;font-size:11px;color:#64748b">' + esc(tableName) + ' | Granularity: <b>' + esc(gran) + '</b> | Display: <b>Yellow-only</b> | Buckets: ' + bucketLabels.length + ' | SKUs: ' + skuList.length + '/' + (summary.total_original_skus||skuListRaw.length) + '</div></div>';
  } else {
    html += '<div class="v2v-legend"><div class="v2v-legend-item"><div class="v2v-legend-color added"></div><span>ADDED</span></div><div class="v2v-legend-item"><div class="v2v-legend-color deleted"></div><span>DELETED</span></div><div class="v2v-legend-item"><div class="v2v-legend-color modify"></div><span>MODIFY</span></div><div style="margin-left:auto;font-size:11px;color:#64748b">' + esc(tableName) + ' | Granularity: <b>' + esc(gran) + '</b> | Buckets: ' + bucketLabels.length + ' | SKUs: ' + skuList.length + '</div></div>';
  }

  const maxCols = 200;
  let displayBuckets = bucketLabels;
  let truncated = false;
  if (bucketLabels.length > maxCols) {
    displayBuckets = bucketLabels.slice(0, maxCols);
    truncated = true;
  }

  html += '<div class="v2v-table-wrapper" style="max-height:650px"><table class="v2v-table"><thead><tr><th style="min-width:180px;position:sticky;left:0;z-index:20;background:#1e293b">SKU / Time →<br><small style="font-weight:400">Vertical SKU, Horizontal Time</small></th>';
  for (const lb of displayBuckets) {
    let shortLb = lb;
    if (typeof lb==='string' && lb.length>10) shortLb = lb.slice(0,10);
    if (gran==='day' && typeof shortLb==='string' && shortLb.indexOf('-')>=0) shortLb = shortLb.slice(5);
    else if (gran==='week' && typeof shortLb==='string') shortLb = shortLb.slice(5);
    html += '<th class="col-center" style="min-width:85px;font-size:11px" title="' + esc(lb) + '">' + esc(shortLb) + '</th>';
  }
  if (truncated) html += '<th style="min-width:100px;background:#fef3c7;color:#92400e">+' + (bucketLabels.length-maxCols) + ' more</th>';
  html += '</tr></thead><tbody>';

  const displaySkus = skuList.slice(0,200);
  for (const sku of displaySkus) {
    const row = matrix[sku] || {};
    html += '<tr><td style="position:sticky;left:0;background:white;z-index:10;font-weight:600;min-width:180px">' + esc(sku) + '</td>';
    for (const tb of displayBuckets) {
      const cell = row[tb];
      if (!cell) {
        html += '<td class="col-center" style="background:#f8fafc"></td>';
      } else {
        const isHC = cell.has_change || cell.tag==='HAS_CHANGE' || isHasChange;
        if (isHC) {
          const changedCount = cell.changed_count || (cell.changed_days?cell.changed_days.length:0) || (cell.changed_weeks?cell.changed_weeks.length:0) || 0;
          const days = (cell.changed_days||cell.changed_weeks||[]).slice(0,5).join(', ');
          const tip = 'Has change in this ' + gran + ' - ' + changedCount + ' days/weeks changed' + (days?' - e.g. '+days:'');
          html += '<td class="cell-has-change" title="' + esc(tip) + '"><span style="font-weight:700;color:#854d0e">●</span></td>';
        } else {
          const diff = cell.diff||0; const prev = cell.prev||0; const latest = cell.latest||0; const tag = cell.tag||'MODIFY';
          let cls=''; let txt='';
          if (tag==='ADDED') { cls='cell-added'; txt='+' + Number(latest).toLocaleString(); }
          else if (tag==='DELETED') { cls='cell-deleted'; txt='' + Number(diff).toLocaleString(); }
          else { cls='cell-modify'; txt='' + Number(prev).toLocaleString() + '→' + Number(latest).toLocaleString(); }
          html += '<td class="col-center ' + cls + '" title="' + esc(tag) + ' ' + esc(diff) + '"><div style="font-size:11px;font-weight:600">' + esc(txt) + '</div>' + (tag==='MODIFY'?'<div style="font-size:10px;color:' + (diff>0?'#16a34a':'#dc2626') + '">' + (diff>0?'+':'') + Number(diff).toLocaleString() + '</div>':'') + '</td>';
        }
      }
    }
    if (truncated) html += '<td></td>';
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  if (skuList.length>200) html += '<div style="font-size:11px;color:#64748b;margin-top:8px;">Showing first 200 of ' + skuList.length + ' SKUs</div>';
  if (truncated) html += '<div style="font-size:11px;color:#92400e;background:#fffbeb;padding:6px;border-radius:4px;margin-top:8px;">Too many buckets (' + bucketLabels.length + '), showing first ' + maxCols + '</div>';
  html += '<div style="font-size:11px;color:#64748b;margin-top:8px;">Total SKUs (only diff): ' + skuList.length + ' / Original ' + (summary.total_original_skus||skuListRaw.length) + ' | Time range: ' + esc(summary.time_range||'') + ' | ' + esc(summary.note||'') + '</div>';

  wrapper.innerHTML = html;
}

function renderVertical(tableName) {
  const wrapper = document.getElementById('detail-content');
  if (!wrapper) return;
  const data = currentState.isClientSide && currentState.clientData && currentState.clientData.vertical_diffs && currentState.clientData.vertical_diffs[tableName] ? currentState.clientData.vertical_diffs[tableName] : EMBEDDED_DATA.vertical_diffs[tableName];
  if (!data || data.error) {
    wrapper.innerHTML = '<div class="v2v-status ' + (data && data.error ? 'error' : 'info') + '">' + (data && data.error ? 'Error: ' + esc(data.error) : 'No diff for ' + esc(tableName)) + '</div>';
    return;
  }
  const records = data.records || [];
  const pagination = data.pagination || {};
  if (records.length===0) {
    wrapper.innerHTML = '<div class="v2v-status success">No differences for ' + esc(tableName) + '</div>';
    return;
  }
  let html = '<div style="font-size:12px;color:#64748b;margin-bottom:8px;">Showing ' + records.length + ' of ' + (pagination.total||records.length) + ' | ' + esc(tableName) + '</div>';
  html += '<div class="v2v-table-wrapper" style="max-height:600px"><table class="v2v-table"><thead><tr>';
  const first = records[0];
  let headers = [];
  if (first.key && typeof first.key==='object') {
    for (const k in first.key) headers.push('key_'+k);
  }
  for (const k in first) {
    if (['key','_group_values','_drill','raw'].indexOf(k)<0) headers.push(k);
  }
  headers = headers.slice(0,12);
  for (const h of headers) html += '<th>' + esc(h) + '</th>';
  html += '</tr></thead><tbody>';
  for (const rec of records) {
    const ctRaw = rec.change_type||rec.change_tag||rec.TAG||'MODIFY';
    const ct = String(ctRaw).toUpperCase();
    const ctLower = ct.indexOf('ADD')>=0?'add':ct.indexOf('DEL')>=0?'del':'mod';
    html += '<tr class="diff-' + ctLower + '">';
    const flat={};
    if (rec.key && typeof rec.key==='object') {
      for (const k in rec.key) flat['key_'+k]=rec.key[k];
    }
    for (const k in rec) {
      if (['key','_group_values','_drill','raw'].indexOf(k)<0 && !(k in flat)) flat[k]=rec[k];
    }
    for (const h of headers) {
      let v = flat[h];
      if (v==null) v='';
      if (typeof v==='number') v = Number(v).toLocaleString();
      html += '<td>' + esc(String(v).slice(0,100)) + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  wrapper.innerHTML = html;
}

document.querySelectorAll('#granularity-toggle button').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('#granularity-toggle button').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    currentState.granularity = btn.dataset.granularity;
    loadDetail(currentState.activeTable);
  });
});

document.getElementById('filter-changetype') && document.getElementById('filter-changetype').addEventListener('change', e=>{
  currentState.filters.changeType = e.target.value;
  loadDetail(currentState.activeTable);
});
document.getElementById('filter-sku') && document.getElementById('filter-sku').addEventListener('change', e=>{
  currentState.filters.skuCategory = e.target.value;
  loadDetail(currentState.activeTable);
});
document.getElementById('filter-line') && document.getElementById('filter-line').addEventListener('change', e=>{
  currentState.filters.lineCategory = e.target.value;
  loadDetail(currentState.activeTable);
});

let selectedFilesA = [];
let selectedFilesB = [];
function updateFileList(id, files) {
  const listEl = document.getElementById(id==='a'?'list-a':'list-b');
  if (!listEl) return;
  let html='';
  for (const f of files) {
    html += '<div>📄 ' + esc(f.name) + ' (' + (f.size/1024).toFixed(1) + ' KB)</div>';
  }
  listEl.innerHTML = html;
}
document.getElementById('files-a') && document.getElementById('files-a').addEventListener('change', e=>{
  selectedFilesA = Array.from(e.target.files);
  updateFileList('a', selectedFilesA);
});
document.getElementById('files-b') && document.getElementById('files-b').addEventListener('change', e=>{
  selectedFilesB = Array.from(e.target.files);
  updateFileList('b', selectedFilesB);
});
[['drop-a','a'],['drop-b','b']].forEach(pair=>{
  const dropId = pair[0]; const which = pair[1];
  const el = document.getElementById(dropId);
  if (!el) return;
  el.addEventListener('dragover', e=>{ e.preventDefault(); el.classList.add('dragover'); });
  el.addEventListener('dragleave', e=>{ el.classList.remove('dragover'); });
  el.addEventListener('drop', e=>{
    e.preventDefault(); el.classList.remove('dragover');
    const files = Array.from(e.dataTransfer.files).filter(f=>f.name.endsWith('.xlsx'));
    if (which==='a') { selectedFilesA = files; updateFileList('a', files); }
    else { selectedFilesB = files; updateFileList('b', files); }
  });
});

function identifyTableByFilename(name) {
  const lower = name.toLowerCase();
  const defs = TABLE_DEFS;
  for (const [key, def] of Object.entries(defs)) {
    const kws = def.keywords||[];
    for (const kw of kws) {
      if (lower.indexOf(kw.toLowerCase())>=0) return key;
    }
  }
  if (lower.indexOf('bom')>=0) return 'bom';
  if (lower.indexOf('balance')>=0 || lower.indexOf('boh')>=0) return 'balance';
  if (lower.indexOf('plan_output')>=0) return 'plan_output';
  if (lower.indexOf('fcst_detail')>=0) return 'fcst_detail';
  if (lower.indexOf('fcst')>=0 || lower.indexOf('forecast')>=0) return 'fcst';
  if (lower.indexOf('supply')>=0 || lower.indexOf('kitting')>=0) return 'supply';
  if (lower.indexOf('switch')>=0) return 'switch';
  if (lower.indexOf('item')>=0) return 'item';
  if (lower.indexOf('line')>=0) return 'line';
  if (lower.indexOf('calendar')>=0) return 'calendar';
  if (lower.indexOf('plan_config')>=0) return 'plan_config';
  return 'unknown';
}

function parseXlsxFile(file) {
  return new Promise((resolve, reject)=>{
    const reader = new FileReader();
    reader.onload = e=>{
      try {
        const data = new Uint8Array(e.target.result);
        const wb = XLSX.read(data, {type:'array'});
        const firstSheet = wb.Sheets[wb.SheetNames[0]];
        const json = XLSX.utils.sheet_to_json(firstSheet, {defval:null});
        resolve(json);
      } catch(err) { reject(err); }
    };
    reader.onerror = reject;
    reader.readAsArrayBuffer(file);
  });
}

function normalizeDateToYMD(val) {
  if (!val) return null;
  try {
    const d = new Date(val);
    if (isNaN(d.getTime())) return null;
    return d.toISOString().slice(0,10);
  } catch(e) { return null; }
}

function toSaturdayStr(dateStr) {
  try {
    const d = new Date(dateStr);
    const dow = d.getDay();
    const diff = (6 - dow + 7) % 7;
    d.setDate(d.getDate()+diff);
    return d.toISOString().slice(0,10);
  } catch(e) { return dateStr; }
}

async function clientSideCompare() {
  const status = document.getElementById('import-status');
  if (!selectedFilesA.length || !selectedFilesB.length) {
    if (status) status.textContent = 'Please select both Previous and Latest .xlsx files';
    return;
  }
  if (status) status.textContent = 'Parsing and comparing...';
  try {
    async function parseSide(files) {
      const tables = {};
      for (const f of files) {
        const tkey = identifyTableByFilename(f.name);
        if (tkey==='unknown') continue;
        try {
          const rows = await parseXlsxFile(f);
          tables[tkey] = rows;
        } catch(e) {
          console.log('Parse failed', f.name, e);
        }
      }
      return tables;
    }
    const sideA = await parseSide(selectedFilesA);
    const sideB = await parseSide(selectedFilesB);

    function buildBOHMatrix(aRows, bRows, gran) {
      function normalize(rows) {
        const map = new Map();
        for (const r of rows) {
          const item = r.ITEM_CODE || r.ITEM || r.SKU || r.PN_CODE;
          const dateRaw = r.PLAN_DATE || r.DATE;
          const date = normalizeDateToYMD(dateRaw) || String(dateRaw||'').slice(0,10);
          if (!item || !date) continue;
          const key = item+'|'+date;
          map.set(key, {ITEM_CODE:item, _DATE:date, BALANCE_QTY: Number(r.BALANCE_QTY||r.QTY||0), SHIFT_NAME:r.SHIFT_NAME||'白班'});
        }
        return Array.from(map.values());
      }
      const normA = normalize(aRows);
      const normB = normalize(bRows);
      const lookupA = new Map(); const lookupB = new Map();
      for (const r of normA) lookupA.set(r.ITEM_CODE+'|'+r._DATE, r.BALANCE_QTY);
      for (const r of normB) lookupB.set(r.ITEM_CODE+'|'+r._DATE, r.BALANCE_QTY);
      const allDatesSet = new Set([...Array.from(lookupA.keys()).map(k=>k.split('|')[1]), ...Array.from(lookupB.keys()).map(k=>k.split('|')[1])]);
      const allDates = Array.from(allDatesSet).sort();
      const allSkusSet = new Set([...Array.from(lookupA.keys()).map(k=>k.split('|')[0]), ...Array.from(lookupB.keys()).map(k=>k.split('|')[0])]);
      const allSkus = Array.from(allSkusSet);

      const dailyChange = new Map();
      for (const sku of allSkus) {
        const s = new Set();
        for (const d of allDates) {
          const prev = lookupA.get(sku+'|'+d);
          const latest = lookupB.get(sku+'|'+d);
          if (prev==null && latest==null) continue;
          const p = prev==null?0:Number(prev); const l = latest==null?0:Number(latest);
          if (p!==l) s.add(d);
        }
        if (s.size>0) dailyChange.set(sku, s);
      }

      if (gran==='day') {
        const bucketLabels = allDates;
        const matrix={};
        for (const sku of allSkus) {
          const row={};
          let has=false;
          for (const d of bucketLabels) {
            const prev = lookupA.get(sku+'|'+d);
            const latest = lookupB.get(sku+'|'+d);
            if (prev==null && latest==null) { row[d]=null; continue; }
            const p = prev==null?0:Number(prev); const l = latest==null?0:Number(latest); const diff=l-p;
            if (diff===0) { row[d]=null; continue; }
            has=true;
            const tag = prev==null?'ADDED': latest==null?'DELETED':'MODIFY';
            row[d] = {prev:p, latest:l, diff, tag};
          }
          if (has) matrix[sku]=row;
        }
        return {
          time_buckets: bucketLabels,
          bucket_labels: bucketLabels,
          sku_list: Object.keys(matrix),
          matrix,
          granularity: gran,
          display_mode: 'detailed',
          summary: {total_skus:Object.keys(matrix).length, total_times:bucketLabels.length, total_original_skus:allSkus.length}
        };
      } else if (gran==='week' || gran==='month') {
        let targetBuckets;
        if (gran==='week') {
          const weeks=new Set();
          for (const d of allDates) weeks.add(toSaturdayStr(d));
          targetBuckets = Array.from(weeks).sort();
        } else {
          const months = new Set();
          for (const d of allDates) months.add(d.slice(0,7));
          targetBuckets = Array.from(months).sort();
        }
        const matrix={};
        for (const sku of dailyChange.keys()) {
          const changedDates = dailyChange.get(sku);
          const row={};
          let has=false;
          for (const bucket of targetBuckets) {
            let changedInBucket=[];
            if (gran==='week') {
              const sat = new Date(bucket);
              const sun = new Date(sat); sun.setDate(sat.getDate()-6);
              for (let dt=new Date(sun); dt<=sat; dt.setDate(dt.getDate()+1)) {
                const ds = dt.toISOString().slice(0,10);
                if (changedDates.has(ds)) changedInBucket.push(ds);
              }
            } else {
              for (const d of changedDates) if (d.slice(0,7)===bucket) changedInBucket.push(d);
            }
            if (changedInBucket.length>0) {
              has=true;
              row[bucket] = {has_change:true, tag:'HAS_CHANGE', changed_days:changedInBucket, changed_count:changedInBucket.length, display_mode:'has_change'};
            } else {
              row[bucket]=null;
            }
          }
          if (has) matrix[sku]=row;
        }
        return {
          time_buckets: targetBuckets,
          bucket_labels: targetBuckets,
          sku_list: Object.keys(matrix),
          matrix,
          granularity: gran,
          display_mode: 'has_change',
          summary: {total_skus:Object.keys(matrix).length, total_times:targetBuckets.length, total_original_skus:allSkus.length, note: 'Yellow-only for week/month'}
        };
      } else {
        return {time_buckets:[], bucket_labels:[], sku_list:[], matrix:{}, granularity:gran, display_mode:'detailed', summary:{}};
      }
    }

    const clientMatrices = {};
    const clientVertical = {};

    if (sideA.balance && sideB.balance) {
      if (!clientMatrices.balance) clientMatrices.balance={};
      for (const g of ['day','week','month']) {
        clientMatrices.balance[g] = buildBOHMatrix(sideA.balance, sideB.balance, g);
      }
    }

    const summary = {};
    for (const k of Object.keys(TABLE_DEFS)) {
      const aCount = sideA[k] ? sideA[k].length : 0;
      const bCount = sideB[k] ? sideB[k].length : 0;
      const has = aCount>0 || bCount>0;
      if (has) {
        summary[k] = {total_a:aCount, total_b:bCount, added:0, deleted:0, modified:0, note:'Client-side file count'};
      }
    }

    const finalData = {
      meta: Object.assign({}, EMBEDDED_DATA.meta, {isClientSide:true, recompare_at: new Date().toISOString()}),
      summary: Object.keys(summary).length>0 ? summary : EMBEDDED_DATA.summary,
      matrices: Object.keys(clientMatrices).length>0 ? Object.assign({}, EMBEDDED_DATA.matrices, clientMatrices) : EMBEDDED_DATA.matrices,
      vertical_diffs: EMBEDDED_DATA.vertical_diffs
    };

    EMBEDDED_DATA.summary = finalData.summary;
    EMBEDDED_DATA.matrices = finalData.matrices;
    currentState.isClientSide = true;
    currentState.clientData = finalData;

    renderSummary();
    renderTabs();
    loadDetail(currentState.activeTable);

    if (status) status.textContent = 'Client-side re-compare done: ' + Object.keys(summary).length + ' tables parsed, BOH matrices built';
  } catch(err) {
    console.error(err);
    if (status) status.textContent = 'Failed: ' + err.message;
  }
}

document.getElementById('btn-recompare') && document.getElementById('btn-recompare').addEventListener('click', clientSideCompare);
document.getElementById('btn-reset') && document.getElementById('btn-reset').addEventListener('click', ()=>{
  currentState.isClientSide = false;
  currentState.clientData = null;
  const original = JSON.parse(document.getElementById('v2v-embedded-data').textContent);
  EMBEDDED_DATA.summary = original.summary;
  EMBEDDED_DATA.matrices = original.matrices;
  EMBEDDED_DATA.vertical_diffs = original.vertical_diffs;
  renderSummary();
  renderTabs();
  loadDetail(currentState.activeTable);
  document.getElementById('import-status').textContent = 'Reset to embedded data';
});

renderSummary();
renderTabs();
loadDetail(currentState.activeTable);
</script>
</body>
</html>
"""

    # Replace placeholders
    replacements = {
        "__STATIC_SUMMARY__": static_summary_html,
        "__CSS_GLOBAL__": css_global,
        "__CSS_V2V__": css_v2v,
        "__EMBEDDED_JSON__": embedded_json_str,
        "__TABLE_DEFS_JSON__": table_defs_json,
        "__PREV__": previous_name,
        "__LATEST__": latest_name,
        "__GEN_AT__": generated_at,
        "__JOB_ID__": job_id,
        "__JOB_ID_SHORT__": job_id[:8],
        "__SUMMARY_COUNT__": str(summary_count),
        "__OVERALL_ADDED__": str(overall_added),
        "__OVERALL_DELETED__": str(overall_deleted),
        "__OVERALL_MODIFIED__": str(overall_modified),
    }

    html = html_template
    for k, v in replacements.items():
        html = html.replace(k, str(v))

    return html
