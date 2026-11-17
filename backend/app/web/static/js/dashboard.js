(() => {
  const kpiStrip = document.getElementById("kpi-strip");
  const interestBody = document.querySelector("#interest-table tbody");
  const funnelBody = document.querySelector("#funnel-table tbody");
  const bars = document.getElementById("interest-bars");
  const agentLine = document.getElementById("agent-line");
  const agentLog = document.getElementById("agent-log");
  const refreshBtn = document.getElementById("refresh-dash");
  const runBtn = document.getElementById("run-agent");
  if (!refreshBtn || !runBtn) return;

  function kpi(label, value) {
    return `<div class="kpi"><div class="label">${label}</div><div class="value">${value}</div></div>`;
  }

  async function loadAgent() {
    const res = await fetch("/agent/status");
    const data = await res.json();
    const when = data.last_run_at ? new Date(data.last_run_at).toLocaleString() : "not yet";
    agentLine.textContent = `Agent ${data.enabled ? "running" : "paused"} · poll ${data.poll_seconds}s · last run ${when} · ${data.last_summary || "waiting for first cycle"}`;
  }

  async function loadDashboard() {
    const res = await fetch("/analytics/dashboard");
    if (!res.ok) return;
    const data = await res.json();
    if (kpiStrip) {
      kpiStrip.innerHTML = [
        kpi("Rewards members", data.rewards_members),
        kpi("Face enrolled", data.face_enrolled_members),
        kpi("Interest events", data.interest_events_total),
        kpi("Email conv %", `${data.overall_conversion_rate}%`),
      ].join("");
    }

    if (interestBody) {
      interestBody.innerHTML = data.product_interest
        .map(
          (p) => `<tr>
          <td>${p.product_name}<div class="muted">${p.brand} · ${p.category}</div></td>
          <td>${p.interested_shopper_count}</td>
          <td>${p.total_interest_weight.toFixed(1)}</td>
          <td>${p.avg_interest_weight.toFixed(1)}</td>
          <td>${p.interest_event_count}</td>
        </tr>`
        )
        .join("");
    }

    if (bars) {
      const maxW = Math.max(...data.product_interest.map((p) => p.total_interest_weight), 1);
      bars.innerHTML = data.product_interest
        .slice(0, 6)
        .map((p) => {
          const pct = Math.round((p.total_interest_weight / maxW) * 100);
          return `<div class="bar-row"><span>${p.product_name}</span><div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div><span>${p.total_interest_weight.toFixed(0)}</span></div>`;
        })
        .join("");
    }

    if (funnelBody) {
      funnelBody.innerHTML = data.email_funnel
        .map(
          (p) => `<tr>
          <td>${p.product_name}</td>
          <td>${p.emails_sent}</td>
          <td>${p.open_rate}%</td>
          <td>${p.click_rate}%</td>
          <td>${p.conversion_rate}%</td>
        </tr>`
        )
        .join("");
    }

    if (agentLog) {
      agentLog.innerHTML = (data.recent_agent_runs || [])
        .map(
          (r) => `<li><strong>${r.created_at ? new Date(r.created_at).toLocaleString() : ""}</strong> — reviewed ${r.candidates_reviewed}, sent ${r.emails_sent}. ${r.summary}</li>`
        )
        .join("") || "<li>No agent runs yet.</li>";
    }
  }

  refreshBtn.addEventListener("click", async () => {
    await Promise.all([loadDashboard(), loadAgent()]);
    // Reload to refresh emails table from server
    window.location.reload();
  });

  runBtn.addEventListener("click", async () => {
    runBtn.disabled = true;
    try {
      await fetch("/agent/run-once", { method: "POST" });
      window.location.reload();
    } finally {
      runBtn.disabled = false;
    }
  });

  loadAgent();
  setInterval(loadAgent, 15000);
})();
