// ===== Global: Sidebar Toggle & Header Title =====
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

  // Set header title from active nav item
  const activeNav = document.querySelector('.nav-item.active');
  const headerTitle = document.getElementById('header-title');
  if (activeNav && headerTitle) {
    const text = activeNav.querySelector('.nav-text');
    if (text) headerTitle.textContent = text.textContent;
  }
});