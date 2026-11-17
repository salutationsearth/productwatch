(() => {
  const refreshBtn = document.getElementById("refresh-dash");
  if (!refreshBtn) return;
  refreshBtn.addEventListener("click", () => window.location.reload());
})();
