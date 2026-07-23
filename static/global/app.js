// ===== Global: Sidebar Toggle & Nav Switching — V4 Integrated 5 Modules (io-report, idle, packout, utilization, v2v) =====
// IA:
// Current Week
//   Single: I/O, Idle (standalone, one version)
//   Compare: Packout, Utilization (Gated vs Ungated, fallback to single if only one uploaded)
// Cross Week
//   V2V Comparison: W29 Gated vs W30 Gated (true multi-version, from feat/io-report + feat/v2v)
// Legacy: plan-merge -> packout, version-compare -> v2v
document.addEventListener('DOMContentLoaded', () => {
  function toggleSidebar() {
    const sb = document.getElementById('sidebar');
    if (sb) sb.classList.toggle('collapsed');
    setTimeout(() => {
      document.dispatchEvent(new CustomEvent('sidebar-resized'));
    }, 220);
  }
  const toggle = document.getElementById('sidebar-toggle');
  if (toggle) toggle.addEventListener('click', toggleSidebar);
  const toggleAlt = document.getElementById('sidebar-toggle-alt');
  if (toggleAlt) toggleAlt.addEventListener('click', toggleSidebar);

  // Section registry - 5 modules integrated
  const S = {
    upload: document.getElementById('upload-section'),
    config: document.getElementById('config-section'),
    report: document.getElementById('report-section'),
    io: document.getElementById('io-report-section'),
    utilization: document.getElementById('utilization-section'),
    idle: document.getElementById('idle-section'),
    versionCompare: document.getElementById('version-compare-section'),
    v2v: document.getElementById('v2v-section'),
  };

  function hideAll() {
    Object.values(S).forEach(el => { if (el) el.style.display = 'none'; });
  }

  function showPackout() {
    if (S.upload) S.upload.style.display = 'block';
    if (S.config) S.config.style.display = 'block';
    if (S.report && S.report.dataset.hasData === 'true') S.report.style.display = 'block';
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

  // Module -> visibility map (5 modules)
  function switchModule(mod) {
    // Normalize legacy
    if (mod === 'plan-merge') mod = 'packout';
    if (mod === 'version-compare') mod = 'v2v'; // alias to v2v

    hideAll();
    if (mod === 'packout') {
      showPackout();
    } else if (mod === 'io-report') {
      if (S.io) S.io.style.display = 'block';
      if (typeof window.ioReportInit === 'function') {
        try { setTimeout(() => window.ioReportInit(), 100); } catch(e) {}
      }
    } else if (mod === 'utilization') {
      if (S.utilization) S.utilization.style.display = 'block';
    } else if (mod === 'idle') {
      if (S.idle) S.idle.style.display = 'block';
    } else if (mod === 'v2v') {
      if (S.v2v) S.v2v.style.display = 'block';
      if (typeof window.v2vInit === 'function') {
        try { setTimeout(() => window.v2vInit(), 100); } catch(e) {}
      }
      // Also try to show restore banner
      try {
        if (typeof window.updateRestoreBanner === 'function') window.updateRestoreBanner();
      } catch(e) {}
    } else if (mod === 'version-compare') {
      // Should have been mapped to v2v, but fallback
      if (S.versionCompare) S.versionCompare.style.display = 'block';
      try {
        const db = window.STATIC_DB || window.PLAN_MERGE_STATIC_DB;
        const hint = document.getElementById('version-compare-hint');
        if (db && db.versions && hint) {
          hint.innerHTML = `📦 Detected ${db.versions.length} offline versions: ${db.versions.map(v=>'<code>'+ (v.name||'V') +'</code>').join(', ')}<br><span style="font-size:11px">Go to Packout page and check "Compare multi" for early Version vs Version preview, or use V2V Comparison module</span>`;
        }
      } catch {}
    }
    // Update header and fire event
    updateHeaderTitle();
    try {
      localStorage.setItem('active_module', mod);
    } catch(e) {}
    document.dispatchEvent(new CustomEvent('module-change', { detail: { module: mod } }));
  }

  // Bind clicks
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const modRaw = item.dataset.module;
      if (!modRaw) return;
      // Hidden legacy item should still be clickable but not visible in collapsed
      let mod = modRaw;
      if (mod === 'plan-merge') mod = 'packout';
      if (mod === 'version-compare') mod = 'v2v';
      // Update active states: remove active from all, then activate the clicked visible one or its v2v alias
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      // If clicked was version-compare hidden, activate v2v nav instead
      if (modRaw === 'version-compare') {
        const v2vNav = document.querySelector('.nav-item[data-module="v2v"]');
        if (v2vNav) v2vNav.classList.add('active');
        else item.classList.add('active');
      } else {
        item.classList.add('active');
      }
      switchModule(mod);
    });
  });

  // Preserve active state on reload + map old 'plan-merge' / 'version-compare' to new
  (() => {
    try {
      const saved = localStorage.getItem('active_module');
      if (saved) {
        let mod = saved;
        if (mod === 'plan-merge') mod = 'packout';
        if (mod === 'version-compare') mod = 'v2v';
        const navItem = document.querySelector(`.nav-item[data-module="${mod}"]`) || document.querySelector(`.nav-item[data-module="${saved}"]`);
        if (navItem) {
          document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
          // If saved was version-compare, activate v2v nav
          if (saved === 'version-compare') {
            const v2vNav = document.querySelector('.nav-item[data-module="v2v"]');
            if (v2vNav) v2vNav.classList.add('active');
          } else {
            navItem.classList.add('active');
          }
          switchModule(mod);
          return;
        }
      }
    } catch(e) {}

    const active = document.querySelector('.nav-item.active');
    if (active) {
      let mod = active.dataset.module;
      if (mod === 'plan-merge') {
        const packoutItem = document.querySelector('.nav-item[data-module="packout"]');
        if (packoutItem) {
          document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
          packoutItem.classList.add('active');
          mod = 'packout';
        }
      }
      if (mod === 'version-compare') {
        const v2vItem = document.querySelector('.nav-item[data-module="v2v"]');
        if (v2vItem) {
          document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
          v2vItem.classList.add('active');
          mod = 'v2v';
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
  window.switchModule = switchModule;
  console.log('✅ Global app.js V4 loaded: 5 modules (io-report, idle, packout, utilization, v2v) integrated');
});
