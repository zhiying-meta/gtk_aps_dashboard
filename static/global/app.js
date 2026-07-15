// ===== Global: Sidebar Toggle =====
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('sidebar-toggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      document.getElementById('sidebar').classList.toggle('collapsed');
      // Re-render table after sidebar animation completes (200ms)
      setTimeout(() => {
        if (typeof renderTable === 'function') renderTable();
      }, 220);
    });
  }
});
