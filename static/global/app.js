// ===== Global: Sidebar Toggle & Module Switching for all modules (plan-merge, v2v, io-report) =====
document.addEventListener('DOMContentLoaded', () => {
  function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.toggle('collapsed');
    setTimeout(() => {
      const evt = new CustomEvent('sidebar-resized');
      document.dispatchEvent(evt);
      if (typeof window.render === 'function') window.render();
    }, 220);
  }
  const toggle = document.getElementById('sidebar-toggle');
  if (toggle) toggle.addEventListener('click', toggleSidebar);
  const toggleAlt = document.getElementById('sidebar-toggle-alt');
  if (toggleAlt) toggleAlt.addEventListener('click', toggleSidebar);

  function switchModule(moduleName) {
    console.log('Switching to module:', moduleName);
    document.querySelectorAll('.module-section').forEach(el => {
      el.classList.remove('active');
    });
    const target = document.getElementById('module-' + moduleName);
    if (target) {
      target.classList.add('active');
    }
    document.querySelectorAll('.nav-item').forEach(item => {
      item.classList.remove('active');
      if (item.dataset.module === moduleName) {
        item.classList.add('active');
      }
    });
    const activeNav = document.querySelector('.nav-item.active');
    const headerTitle = document.getElementById('header-title');
    if (activeNav && headerTitle) {
      const text = activeNav.querySelector('.nav-text');
      if (text) headerTitle.textContent = text.textContent;
    }
    try {
      localStorage.setItem('active_module', moduleName);
    } catch(e) {}
    if (moduleName === 'v2v' && typeof window.v2vInit === 'function') {
      setTimeout(()=>window.v2vInit(), 100);
    }
    if (moduleName === 'io-report' && typeof window.ioReportInit === 'function') {
      setTimeout(()=>window.ioReportInit(), 100);
    }
    const evt = new CustomEvent('module-change', { detail: { module: moduleName } });
    document.dispatchEvent(evt);
  }

  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e)=>{
      e.preventDefault();
      const mod = item.dataset.module;
      if (mod) switchModule(mod);
    });
  });

  // Initial header title
  const activeNav = document.querySelector('.nav-item.active');
  const headerTitle = document.getElementById('header-title');
  if (activeNav && headerTitle) {
    const text = activeNav.querySelector('.nav-text');
    if (text) headerTitle.textContent = text.textContent;
  }

  // Restore last module
  try {
    const saved = localStorage.getItem('active_module');
    if (saved && document.getElementById('module-' + saved)) {
      switchModule(saved);
    }
  } catch(e) {}

  window.switchModule = switchModule;

  // For plan-merge report hasData tracking (keep compatibility)
  const reportSec = document.getElementById('report-section');
  if (reportSec) {
    const observer = new MutationObserver(()=>{
      if(reportSec && reportSec.style.display !== 'none'){
        reportSec.dataset.hasData = 'true';
      }
    });
    observer.observe(reportSec, { attributes: true, attributeFilter: ['style'] });
  }
});
