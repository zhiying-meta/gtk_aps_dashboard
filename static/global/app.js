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

  // Module switching
  const sections = {
    'plan-merge': document.getElementById('report-section'),
    'io-report': document.getElementById('io-report-section'),
  };

  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      Object.values(sections).forEach(s => { if (s) s.style.display = 'none'; });
      const mod = item.dataset.module;
      if (sections[mod]) sections[mod].style.display = 'block';
      updateHeaderTitle();

      // Dispatch module-change event for modules to react
      const evt = new CustomEvent('module-change', { detail: { module: mod } });
      document.dispatchEvent(evt);
    });
  });

  updateHeaderTitle();
});