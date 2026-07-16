// ===== Global: Sidebar Toggle & Nav Switching =====
document.addEventListener('DOMContentLoaded', () => {
  // Sidebar toggle
  function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('collapsed');
    setTimeout(() => {
      const evt = new CustomEvent('sidebar-resized');
      document.dispatchEvent(evt);
    }, 220);
  }
  const toggle = document.getElementById('sidebar-toggle');
  if (toggle) toggle.addEventListener('click', toggleSidebar);
  const toggleAlt = document.getElementById('sidebar-toggle-alt');
  if (toggleAlt) toggleAlt.addEventListener('click', toggleSidebar);

  // Set header title from active nav item
  function updateHeaderTitle() {
    const activeNav = document.querySelector('.nav-item.active');
    const headerTitle = document.getElementById('header-title');
    if (activeNav && headerTitle) {
      const text = activeNav.querySelector('.nav-text');
      if (text) headerTitle.textContent = text.textContent;
    }
  }

  // Module switching - plan-merge shows upload+config(+report if generated), io-report shows only io
  const uploadSec = document.getElementById('upload-section');
  const configSec = document.getElementById('config-section');
  const reportSec = document.getElementById('report-section');
  const ioSec = document.getElementById('io-report-section');

  // Ensure initial state matches HTML: plan-merge visible, io hidden
  if(ioSec) ioSec.style.display = 'none';
  // reportSec already has inline display:none in HTML, keep it

  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      const mod = item.dataset.module;
      if(mod === 'plan-merge'){
        if(uploadSec) uploadSec.style.display = 'block';
        if(configSec) configSec.style.display = 'block';
        // report visibility controlled by plan_merge logic, but show if it has data
        if(reportSec && reportSec.dataset.hasData === 'true'){
          reportSec.style.display = 'block';
        }
        if(ioSec) ioSec.style.display = 'none';
      }else if(mod === 'io-report'){
        if(uploadSec) uploadSec.style.display = 'none';
        if(configSec) configSec.style.display = 'none';
        if(reportSec) reportSec.style.display = 'none';
        if(ioSec) ioSec.style.display = 'block';
      }
      updateHeaderTitle();

      const evt = new CustomEvent('module-change', { detail: { module: mod } });
      document.dispatchEvent(evt);
    });
  });

  // When plan_merge finishes processing, mark report as having data
  const observer = new MutationObserver(()=>{
    if(reportSec && reportSec.style.display !== 'none'){
      reportSec.dataset.hasData = 'true';
    }
  });
  if(reportSec) observer.observe(reportSec, { attributes: true, attributeFilter: ['style'] });

  updateHeaderTitle();
});