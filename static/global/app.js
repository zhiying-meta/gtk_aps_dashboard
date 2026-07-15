// ===== Global: Sidebar Toggle =====
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
});