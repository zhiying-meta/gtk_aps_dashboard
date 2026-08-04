/**
 * Inventory Dashboard - Balance Traceability Board (Standalone)
 * Uses shared renderer from renderer.js for table rendering
 * - Load from IO and BOH cache + auto BOM, or upload BOM/Balance/JSON
 */
(() => {
  let dashboardData = null;
  let expanded = new Set();
  let selectedSKUs = [];
  let searchText = "";
  let showOnlyNegative = false;
  let statusInfo = null;

  function esc(s) { return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }
  function getRoot() { return document.getElementById('inventory-dashboard-section'); }
  function getRenderer() { return window.InventoryRenderer; }

  async function fetchStatus() {
    try {
      const r = await fetch('/api/inventory-dashboard/status');
      const j = await r.json();
      statusInfo = j;
      return j;
    } catch (e) {
      console.error('status fetch failed', e);
      return { loaded: false, error: e.message };
    }
  }
  async function fetchData() {
    const r = await fetch('/api/inventory-dashboard/data');
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Failed to load dashboard data');
    return j;
  }
  async function buildFromAuto() {
    const r = await fetch('/api/inventory-dashboard/build', { method: 'POST' });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Build failed');
    return j.dashboard || j;
  }
  async function clearCache() {
    const r = await fetch('/api/inventory-dashboard/clear', { method: 'POST' });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Clear failed');
    return j;
  }

  function render() {
    const root = getRoot();
    if (!root) return;
    if (!dashboardData) {
      renderUploadPage();
    } else {
      renderDashboard();
    }
  }

  async function renderUploadPage() {
    const root = getRoot();
    const st = await fetchStatus();
    const hasIO = st.has_balance;
    const hasBOM = st.has_bom;
    const matCount = st.material_count || 0;

    root.innerHTML = `
      <div class="inv-section">
        <div class="inv-section-header">
          <span class="inv-section-title">📊 Inventory Balance Dashboard — Balance Traceability</span>
          <div class="inv-section-actions">
            <a href="/api/inventory-dashboard/templates/schema" target="_blank" class="btn btn-sm btn-outline">📋 Schema</a>
            <button id="inv-btn-build-auto" class="btn btn-sm ${hasIO ? '' : 'btn-outline'}" ${!hasIO ? 'disabled' : ''}>⚡ Build from IO and BOH Cache ${hasIO ? `(+${matCount} mats)` : ''}</button>
            <button id="inv-btn-clear" class="btn btn-sm btn-outline" style="border-color:#ef4444;color:#ef4444">🗑️ Clear</button>
          </div>
        </div>
        <div style="font-size:11px;color:#475569;line-height:1.6;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:8px 12px;margin-top:10px">
          <div>💡 <b>Balance already calculated, display only</b> — This module does not recalculate, it directly shows the hierarchical traceability table.</div>
          <div>• Preferred: First load balance table in <b>IO and BOH</b> module (already calculated), then click "Build from IO and BOH Cache" above to auto-build dashboard ${hasBOM ? `(Auto BOM found: <code>${esc(st.bom_source || '')}</code>)` : '(BOM not found, flat list will be shown unless you upload BOM)'}</div>
          <div>• Alternative: Directly upload <b>dashboard_data.json</b> (output from gtk-aps-inventory-analysis) or upload <b>BOM_Snapshot.xlsx + Balance.xlsx</b> combination</div>
          <div>• Fusion: <b>Inventory Dashboard</b> Tab is already integrated in IO and BOH — one button renders IO and BOH + Balance board together</div>
        </div>
        <div id="inv-status-bar" style="margin-top:10px"></div>
      </div>

      <div class="inv-section">
        <div class="inv-section-header">
          <span class="inv-section-title">📁 Upload — Supports JSON / BOM+Balance / Zip</span>
          <span class="tag ${st.loaded ? 'tag-green' : 'tag-orange'}">${st.loaded ? 'Ready — Buildable' : 'Not Ready — Please upload or load IO and BOH first'}</span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:10px">
          <div class="upload-card" id="inv-card-json" style="border-color:#8b5cf6;background:#faf5ff">
            <div class="upload-label">📄 dashboard_data.json <span style="font-size:9px;background:#8b5cf6;color:#fff;padding:1px 6px;border-radius:8px">Recommended · Direct Load</span></div>
            <div class="upload-hint">dashboard_data.json from gtk-aps-inventory-analysis — renders directly without parsing</div>
            <input type="file" id="inv-input-json" accept=".json" style="font-size:12px;margin-top:6px">
            <div class="fname" id="inv-fname-json"></div>
          </div>
          <div class="upload-card" id="inv-card-bom" style="border-color:#f59e0b">
            <div class="upload-label">📁 BOM_Snapshot.xlsx <span style="font-size:9px;background:#fef3c7;color:#92400e;padding:1px 4px;border-radius:4px">${hasBOM ? 'Auto found · Optional' : 'Optional · For tree'}</span></div>
            <div class="upload-hint">Contains PARENT_PN_CODE + ITEM_NO, used to build SK → GB tree</div>
            <input type="file" id="inv-input-bom" accept=".xlsx" style="font-size:12px;margin-top:6px">
            <div class="fname" id="inv-fname-bom">${hasBOM ? `✅ Auto: ${esc(st.bom_source || '')}` : ''}</div>
          </div>
          <div class="upload-card" id="inv-card-bal" style="border-color:#10b981">
            <div class="upload-label">📁 Balance.xlsx <span style="font-size:9px;background:#dcfce7;color:#065f46;padding:1px 4px;border-radius:4px">${hasIO ? 'IO and BOH Cache exists · Optional' : 'Optional'}</span></div>
            <div class="upload-hint">PLAN_DATE / SHIFT_NAME / ITEM_CODE / BALANCE_QTY</div>
            <input type="file" id="inv-input-bal" accept=".xlsx" style="font-size:12px;margin-top:6px">
            <div class="fname" id="inv-fname-bal">${hasIO ? `✅ IO and BOH Cache: ${st.balance_count} rows` : ''}</div>
          </div>
        </div>
        <div style="margin-top:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">
          <button id="inv-btn-upload" class="btn" style="background:#0f172a;border-color:#0f172a">▶ Generate Dashboard</button>
          <div class="generate-status-area" style="flex:1">
            <span id="inv-status-badge" class="tag ${st.loaded ? 'tag-green' : 'tag-orange'}">${st.loaded ? `Ready: ${st.balance_count} bal rows, BOM ${hasBOM ? 'found' : 'not found'}` : 'Not Ready'}</span>
            <span id="inv-inline-spinner" style="display:none;align-items:center;gap:6px;font-size:11px;color:#92400e;background:#fef3c7;border:1px solid #fde68a;padding:2px 8px;border-radius:12px"><span class="spinner"></span><span>Loading...</span></span>
            <span id="inv-upload-status" style="font-size:12px;color:#475569"></span>
          </div>
        </div>
        ${!dashboardData ? `
        <div class="welcome" style="margin-top:12px;padding:24px;background:#fff;border:1px dashed #e2e8f0;border-radius:8px;text-align:center;color:#94a3b8">
          <div style="font-size:40px">📊</div>
          <h2 style="font-size:16px;color:#475569;margin:8px 0">Balance Traceability Board — Balance pre-calculated, display only</h2>
          <p style="font-size:12px;line-height:1.6">Build from IO and BOH cache, or upload dashboard_data.json / BOM+Balance tables to render hierarchical traceability table.<br>Supports SK-Finished Goods multi-select filter, [+] expand, red negative inventory highlight, sticky header. Already fused in IO and BOH, one button renders both.</p>
        </div>` : ''}
      </div>
      ${dashboardData ? '<div id="inv-dashboard-content"></div>' : ''}
    `;

    bindUploadEvents(st);
  }

  function bindUploadEvents(st) {
    document.getElementById('inv-btn-build-auto')?.addEventListener('click', async () => {
      const btn = document.getElementById('inv-btn-build-auto');
      const spinner = document.getElementById('inv-inline-spinner');
      const statusEl = document.getElementById('inv-upload-status');
      const badge = document.getElementById('inv-status-badge');
      if (spinner) spinner.style.display = 'inline-flex';
      if (btn) { btn.disabled = true; btn.textContent = '⏳ Building...'; }
      if (badge) badge.textContent = '⏳ Building from IO and BOH cache...';
      try {
        const j = await buildFromAuto();
        dashboardData = j;
        expanded = new Set();
        renderDashboard();
      } catch (e) {
        if (statusEl) statusEl.textContent = '❌ ' + e.message;
        if (badge) badge.textContent = '❌ ' + e.message;
      } finally {
        if (spinner) spinner.style.display = 'none';
        if (btn) { btn.disabled = false; btn.textContent = '⚡ Build from IO and BOH Cache'; }
      }
    });

    document.getElementById('inv-btn-clear')?.addEventListener('click', async () => {
      if (!confirm('Clear inventory dashboard cache?')) return;
      try { await clearCache(); dashboardData = null; expanded = new Set(); selectedSKUs = []; renderUploadPage(); } catch(e) { alert('Clear failed: '+e.message); }
    });

    ['json','bom','bal'].forEach(k => {
      const input = document.getElementById('inv-input-'+k);
      const fnameEl = document.getElementById('inv-fname-'+k);
      if (input) {
        input.addEventListener('change', () => {
          if (input.files && input.files[0]) {
            if (fnameEl) fnameEl.textContent = '✓ ' + input.files[0].name + ' (' + (input.files[0].size/1024).toFixed(1) + 'KB)';
            document.getElementById('inv-card-'+k)?.classList.add('has-file');
          } else {
            if (fnameEl) fnameEl.textContent = '';
            document.getElementById('inv-card-'+k)?.classList.remove('has-file');
          }
        });
      }
    });

    document.getElementById('inv-btn-upload')?.addEventListener('click', async () => {
      const jsonInput = document.getElementById('inv-input-json');
      const bomInput = document.getElementById('inv-input-bom');
      const balInput = document.getElementById('inv-input-bal');
      const btn = document.getElementById('inv-btn-upload');
      const spinner = document.getElementById('inv-inline-spinner');
      const statusEl = document.getElementById('inv-upload-status');
      const badge = document.getElementById('inv-status-badge');

      const hasFiles = (jsonInput?.files?.length||0) + (bomInput?.files?.length||0) + (balInput?.files?.length||0);
      if (hasFiles === 0) {
        if (st.has_balance) {
          document.getElementById('inv-btn-build-auto')?.click();
          return;
        }
        if (statusEl) statusEl.textContent = '❌ Please select files or ensure IO and BOH Cache is loaded';
        return;
      }

      if (spinner) spinner.style.display = 'inline-flex';
      if (btn) { btn.disabled = true; btn.textContent = '⏳ Uploading...'; }
      if (badge) badge.textContent = '⏳ Uploading files...';
      if (statusEl) statusEl.textContent = '';

      const form = new FormData();
      if (jsonInput?.files?.[0]) form.append('json', jsonInput.files[0]);
      if (bomInput?.files?.[0]) form.append('bom', bomInput.files[0]);
      if (balInput?.files?.[0]) form.append('balance', balInput.files[0]);

      try {
        const resp = await fetch('/api/inventory-dashboard/upload', { method: 'POST', body: form });
        const text = await resp.text();
        let j;
        try { j = JSON.parse(text); } catch { throw new Error('Server returned non-JSON ('+resp.status+'): '+text.slice(0,500)); }
        if (!resp.ok) throw new Error(j.error || 'Upload failed');
        dashboardData = j.dashboard || j;
        expanded = new Set();
        selectedSKUs = [];
        if (statusEl) statusEl.textContent = '✅ ' + j.message;
        renderDashboard();
      } catch (e) {
        if (statusEl) statusEl.textContent = '❌ ' + e.message;
        if (badge) badge.textContent = '❌ Failed';
      } finally {
        if (spinner) spinner.style.display = 'none';
        if (btn) { btn.disabled = false; btn.textContent = '▶ Generate Dashboard'; }
      }
    });

    const bar = document.getElementById('inv-status-bar');
    if (bar) {
      if (st.error) {
        bar.innerHTML = `<div class="status-bar error">❌ ${esc(st.error)}</div>`;
      } else if (dashboardData) {
        bar.innerHTML = `<div class="status-bar success">✅ Dashboard loaded: ${Object.keys(dashboardData.inventory||{}).length} materials, ${(dashboardData.timeBuckets||[]).length} time buckets</div>`;
      } else if (st.has_balance) {
        bar.innerHTML = `<div class="status-bar info">ℹ️ IO and BOH cache has ${st.balance_count} balance rows — click "Build from IO and BOH Cache" to render. ${st.has_bom ? `BOM auto-found: <code>${esc(st.bom_source||'')}</code>` : 'BOM not auto-found, flat list will be shown unless you upload BOM.'}</div>`;
      } else {
        bar.innerHTML = `<div class="status-bar warn">⚠️ No balance data — please load IO and BOH first or upload files.</div>`;
      }
    }
  }

  function renderDashboard() {
    const root = getRoot();
    if (!dashboardData) { renderUploadPage(); return; }
    if (!document.getElementById('inv-dashboard-content')) {
      const savedData = dashboardData;
      renderUploadPage().then(() => {
        dashboardData = savedData;
        renderDashboardContent();
      });
      return;
    }
    renderDashboardContent();
  }

  function renderDashboardContent() {
    const container = document.getElementById('inv-dashboard-content') || getRoot();
    if (!container) return;
    const renderer = getRenderer();
    if (!renderer) {
      container.innerHTML = '<div class="status-bar error">❌ Renderer not loaded — missing renderer.js</div>';
      return;
    }
    const state = { expanded, selectedSKUs, searchText, showOnlyNegative };
    const callbacks = {
      onToggle: (pn) => { if (expanded.has(pn)) expanded.delete(pn); else expanded.add(pn); renderDashboardContent(); },
      onExpandAll: () => { Object.keys(dashboardData.bomChildren||{}).forEach(k=>expanded.add(k)); renderDashboardContent(); },
      onCollapseAll: () => { expanded = new Set(); renderDashboardContent(); },
      onSearch: (text) => { searchText = text; clearTimeout(window._invSearchTimer); window._invSearchTimer = setTimeout(()=>renderDashboardContent(), 250); },
      onSKUFilter: (selected) => { selectedSKUs = selected; renderDashboardContent(); },
      onClearFilter: () => { selectedSKUs=[]; searchText=""; showOnlyNegative=false; expanded=new Set(); renderDashboardContent(); },
      onOnlyNegToggle: (checked) => { showOnlyNegative = checked; renderDashboardContent(); },
      onExport: async () => {
        try {
          const resp = await fetch('/api/inventory-dashboard/export');
          if (!resp.ok) throw new Error('Export failed');
          const blob = await resp.blob();
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'dashboard_data.json';
          a.click();
          setTimeout(()=>URL.revokeObjectURL(a.href),1000);
        } catch(e){ alert('Export failed: '+e.message); }
      }
    };
    renderer.renderTable(container, dashboardData, state, callbacks, 'inv');
  }

  window.inventoryDashboardInit = async function() {
    const root = getRoot();
    if (!root) return;
    root.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8"><div class="spinner" style="width:20px;height:20px;border-width:3px;display:inline-block;margin-bottom:8px"></div><div>Loading Inventory Dashboard...</div></div>';
    try {
      const st = await fetchStatus();
      if (st.has_dashboard_data || st.loaded) {
        try { dashboardData = await fetchData(); } catch(e){ dashboardData = null; }
      }
      render();
    } catch(e){
      root.innerHTML = `<div class="inv-section"><div class="status-bar error">❌ Failed to init: ${esc(e.message)}</div></div>`;
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    try {
      const active = document.querySelector('.nav-item.active');
      if (active && active.dataset.module === 'inventory-dashboard') {
        setTimeout(()=>{ if(window.inventoryDashboardInit) window.inventoryDashboardInit(); },200);
      }
    } catch {}
  });
  document.addEventListener('module-change', (e) => {
    if (e.detail && e.detail.module === 'inventory-dashboard') {
      setTimeout(()=>{ if(window.inventoryDashboardInit) window.inventoryDashboardInit(); },100);
    }
  });

  console.log('✅ Inventory Dashboard module loaded (standalone, uses shared renderer)');
})();
