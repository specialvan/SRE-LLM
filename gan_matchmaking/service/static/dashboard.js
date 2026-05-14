const stateUrl = "/v1/dashboard/state";
let refreshTimer = null;

function formatTime(value) {
  if (!value) return "未知";
  return new Date(value * 1000).toLocaleString();
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function serviceCard(service) {
  const pct = Math.max(0, Math.min(100, Math.round(Number(service.mu || 0) * 100)));
  const streak = Number(service.win_streak || 0) >= Number(service.loss_streak || 0) ? "good" : "warn";
  return `
    <article class="service-card">
      <h3>${escapeHtml(service.id)}</h3>
      <p>${escapeHtml(service.tier || "standard")}</p>
      <div class="ring" style="--pct: ${pct}%" data-value="${pct}%" aria-label="reliability ${pct}%"></div>
      <div class="meta-row">
        <span class="badge good">mu ${Number(service.mu || 0).toFixed(3)}</span>
        <span class="badge">sigma ${Number(service.sigma || 0).toFixed(3)}</span>
        <span class="badge ${streak}">W${service.win_streak || 0} / L${service.loss_streak || 0}</span>
        <span class="badge">releases ${service.total_releases || 0}</span>
      </div>
    </article>`;
}

function renderServices(services) {
  const container = document.getElementById("services");
  if (!container) return;
  if (!services.length) {
    container.className = "service-grid empty-state";
    container.textContent = "暂无服务数据，先调用 /v1/decide 生成一条决策。";
    return;
  }
  container.className = "service-grid";
  container.innerHTML = services.map(serviceCard).join("");
}

function renderSynergy(edges) {
  renderSynergyGraph(edges);
  const list = document.getElementById("synergy-list");
  if (!list) return;
  if (!edges.length) {
    list.className = "edge-list empty-state";
    list.textContent = "暂无依赖边。";
    return;
  }
  list.className = "edge-list";
  list.innerHTML = edges.map((edge) => `
    <div class="edge-item">
      <span>${escapeHtml(edge.a)} ↔ ${escapeHtml(edge.b)}</span>
      <strong>${edge.wins}/${edge.games}</strong>
    </div>`).join("");
}

function renderSynergyGraph(edges) {
  const svg = document.getElementById("synergy-graph");
  if (!svg) return;
  const topEdges = edges.slice(0, 5);
  const nodes = Array.from(new Set(topEdges.flatMap((edge) => [edge.a, edge.b]))).slice(0, 8);
  const cx = 210;
  const cy = 130;
  const radius = 92;
  const positions = new Map(nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1) - Math.PI / 2;
    return [node, { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius }];
  }));
  const lines = topEdges.map((edge) => {
    const a = positions.get(edge.a);
    const b = positions.get(edge.b);
    if (!a || !b) return "";
    return `<line class="edge-line" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />`;
  }).join("");
  const circles = nodes.map((node) => {
    const pos = positions.get(node);
    return `<circle class="node" cx="${pos.x}" cy="${pos.y}" r="13" />
      <text class="node-label" x="${pos.x}" y="${pos.y + 30}">${escapeHtml(node)}</text>`;
  }).join("");
  svg.innerHTML = `
    <defs><linearGradient id="edgeGradient" x1="0" x2="1"><stop stop-color="#22d3ee"/><stop offset="1" stop-color="#fb7185"/></linearGradient></defs>
    ${lines}${circles}`;
}

function renderState(data) {
  setText("health", data.status.health);
  setText("ready", data.status.ready ? "ready" : data.status.reason || "not ready");
  setText("service-count", String(data.services.length));
  setText("edge-count", String(data.synergy.length));
  setText("generated-at", formatTime(data.generated_at));
  renderServices(data.services || []);
  renderSynergy(data.synergy || []);
  const error = document.getElementById("error");
  if (error) error.textContent = "";
}

async function fetchDashboardState() {
  try {
    const response = await fetch(stateUrl, { headers: { "Accept": "application/json" } });
    if (!response.ok) throw new Error(`state endpoint returned ${response.status}`);
    renderState(await response.json());
  } catch (error) {
    const node = document.getElementById("error");
    if (node) node.textContent = `Dashboard refresh failed: ${error.message}`;
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  }[char]));
}

function scheduleAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  const auto = document.getElementById("auto-refresh");
  if (auto && auto.checked) refreshTimer = setInterval(fetchDashboardState, 5000);
}

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refresh")?.addEventListener("click", fetchDashboardState);
  document.getElementById("auto-refresh")?.addEventListener("change", scheduleAutoRefresh);
  fetchDashboardState();
  scheduleAutoRefresh();
});
