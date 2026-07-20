// ===== Global: Sidebar Toggle & Header Title & Module Switching =====
document.addEventListener('DOMContentLoaded', () => {
  function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('collapsed');
    setTimeout(() => {
      if (typeof window.render === 'function') window.render();
    }, 220);
  }

  const toggle = document.getElementById('sidebar-toggle');
  if (toggle) toggle.addEventListener('click', toggleSidebar);

  const toggleAlt = document.getElementById('sidebar-toggle-alt');
  if (toggleAlt) toggleAlt.addEventListener('click', toggleSidebar);

  // Module switching
  function switchModule(moduleName) {
    console.log('Switching to module:', moduleName);
    // Hide all module sections
    document.querySelectorAll('.module-section').forEach(el => {
      el.classList.remove('active');
    });
    // Show target module
    const target = document.getElementById('module-' + moduleName);
    if (target) {
      target.classList.add('active');
    }
    // Update sidebar active
    document.querySelectorAll('.nav-item').forEach(item => {
      item.classList.remove('active');
      if (item.dataset.module === moduleName) {
        item.classList.add('active');
      }
    });
    // Update header title
    const activeNav = document.querySelector('.nav-item.active');
    const headerTitle = document.getElementById('header-title');
    if (activeNav && headerTitle) {
      const text = activeNav.querySelector('.nav-text');
      if (text) headerTitle.textContent = text.textContent;
    }
    // Save to localStorage
    try {
      localStorage.setItem('active_module', moduleName);
    } catch(e) {}

    // Trigger init if v2v
    if (moduleName === 'v2v' && typeof window.v2vInit === 'function') {
      setTimeout(()=>window.v2vInit(), 100);
    }
  }

  // Bind nav clicks
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e)=>{
      e.preventDefault();
      const mod = item.dataset.module;
      if (mod) switchModule(mod);
    });
  });

  // Set header title from active nav item (initial)
  const activeNav = document.querySelector('.nav-item.active');
  const headerTitle = document.getElementById('header-title');
  if (activeNav && headerTitle) {
    const text = activeNav.querySelector('.nav-text');
    if (text) headerTitle.textContent = text.textContent;
  }

  // Restore last active module
  try {
    const saved = localStorage.getItem('active_module');
    if (saved && saved !== 'plan-merge') {
      switchModule(saved);
    }
  } catch(e) {}

  // Expose globally
  window.switchModule = switchModule;
});