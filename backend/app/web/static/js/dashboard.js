(() => {
  const refreshBtn = document.getElementById("refresh-dash");
  const runBtn = document.getElementById("run-agent");
  const agentLine = document.getElementById("agent-line");
  if (!refreshBtn) return;

  async function loadAgent() {
    if (!agentLine) return;
    try {
      const res = await fetch("/agent/status");
      const data = await res.json();
      const when = data.last_run_at ? new Date(data.last_run_at).toLocaleString() : "not yet";
      agentLine.textContent =
        `Local agent ${data.enabled ? "running" : "paused"} · poll ${data.poll_seconds}s · ` +
        `last run ${when} · ${data.last_summary || "waiting"}`;
    } catch {
      agentLine.textContent = "Could not load agent status";
    }
  }

  refreshBtn.addEventListener("click", () => window.location.reload());
  if (runBtn) {
    runBtn.addEventListener("click", async () => {
      runBtn.disabled = true;
      try {
        await fetch("/agent/run-once", { method: "POST" });
        window.location.reload();
      } finally {
        runBtn.disabled = false;
      }
    });
  }
  loadAgent();
  setInterval(loadAgent, 15000);
})();
