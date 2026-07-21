// ===== Global: Sidebar Toggle & Nav Switching — V3 =====
// IA:
// Current Week
//   Single: I/O, Idle (standalone, one version)
//   Compare: Packout, Utilization (Gated vs Ungated, fallback to single if only one uploaded)
// Cross Week
//   Version Compare: W29 Gated vs W30 Gated (true multi-version)
// Legacy: plan-merge -> packout
document.addEventListener('DOMContentLoaded', () => {
  function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('collapsed');
    setTimeout(() => {
      document.dispatchEvent(new CustomEvent('sidebar-resized'));
    }, 220);
  }
  const toggle = document.getElementById('sidebar-toggle');
  if (toggle) toggle.addEventListener('click', toggleSidebar);
  const toggleAlt = document.getElementById('sidebar-toggle-alt');
  if (toggleAlt) toggleAlt.addEventListener('click', toggleSidebar);

  // Section registry
  const S = {
    upload: document.getElementById('upload-section'),
    config: document.getElementById('config-section'),
    report: document.getElementById('report-section'),
    io: document.getElementById('io-report-section'),
    utilization: document.getElementById('utilization-section'),
    idle: document.getElementById('idle-section'),
    versionCompare: document.getElementById('version-compare-section'),
  };

  function hideAll() {
    Object.values(S).forEach(el => { if (el) el.style.display = 'none'; });
  }

  function showPackout() {
    // Packout view = upload + config + report (if data exists)
    if (S.upload) S.upload.style.display = 'block';
    if (S.config) S.config.style.display = 'block';
    if (S.report && S.report.dataset.hasData === 'true') S.report.style.display = 'block';
    // keep report hidden until data if no data yet? legacy shows upload/config anyway
  }

  function updateHeaderTitle() {
    const activeNav = document.querySelector('.nav-item.active');
    const headerTitle = document.getElementById('header-title');
    if (!activeNav || !headerTitle) return;
    const text = activeNav.querySelector('.nav-text');
    const findInfo = (() => {
      let cat = '', sub = '';
      let el = activeNav.previousElementSibling;
      while (el) {
        if (!sub && el.classList.contains('nav-subcategory')) sub = el.textContent.trim();
        if (el.classList.contains('nav-category')) { cat = el.textContent.trim(); break; }
        el = el.previousElementSibling;
      }
      return { cat, sub };
    })();
    if (text) {
      const parts = [];
      if (findInfo.cat) parts.push(findInfo.cat);
      if (findInfo.sub) parts.push(findInfo.sub);
      parts.push(text.textContent.trim());
      headerTitle.textContent = parts.join(' · ');
    }
  }

  // Module -> visibility map
  function switchModule(mod) {
    // Normalize legacy
    if (mod === 'plan-merge') mod = 'packout';
    hideAll();
    if (mod === 'packout') {
      showPackout();
    } else if (mod === 'io-report') {
      if (S.io) S.io.style.display = 'block';
    } else if (mod === 'utilization') {
      if (S.utilization) S.utilization.style.display = 'block';
    } else if (mod === 'idle') {
      if (S.idle) S.idle.style.display = 'block';
    } else if (mod === 'version-compare') {
      if (S.versionCompare) S.versionCompare.style.display = 'block';
      // If in static mode with versions, show hint about existing compare
      try {
        const db = window.STATIC_DB || window.PLAN_MERGE_STATIC_DB;
        const hint = document.getElementById('version-compare-hint');
        if (db && db.versions && hint) {
          hint.innerHTML = `📦 Detected ${db.versions.length} offline versions: ${db.versions.map(v=>'<code>'+ (v.name||'V') +'</code>').join(', ')}<br><span style="font-size:11px">Go to Packout page and check "Compare multi" for early Version vs Version preview, or use Base/Compare selector + diff table here later</span>`;
        }
      } catch {}
    }
    updateHeaderTitle();
    document.dispatchEvent(new CustomEvent('module-change', { detail: { module: mod } }));
  }

  // Bind clicks
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const mod = item.dataset.module;
      // Hidden legacy item should still be clickable but not visible in collapsed
      if (item.style.display === 'none' && mod === 'plan-merge') return;
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      switchModule(mod);
    });
  });

  // Preserve active state on reload + map old 'plan-merge' to 'packout'
  (() => {
    const active = document.querySelector('.nav-item.active');
    if (active) {
      let mod = active.dataset.module;
      if (mod === 'plan-merge') {
        // Migrate active to packout
        const packoutItem = document.querySelector('.nav-item[data-module="packout"]');
        if (packoutItem) {
          document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
          packoutItem.classList.add('active');
          mod = 'packout';
        }
      }
      switchModule(mod);
    }
  })();

  // Watch report section to mark hasData
  if (S.report) {
    const observer = new MutationObserver(() => {
      if (S.report && S.report.style.display !== 'none') {
        S.report.dataset.hasData = 'true';
      }
    });
    observer.observe(S.report, { attributes: true, attributeFilter: ['style'] });
  }

  updateHeaderTitle();
});
