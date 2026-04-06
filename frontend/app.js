/* ── Keleur PWA ─────────────────────────────────────────────── */

const $ = (s) => document.querySelector(s);
const app = () => $("#app");

// ── API helper ────────────────────────────────────────────────

async function api(path) {
  const resp = await fetch(`/api${path}`);
  if (!resp.ok) throw new Error(`API ${resp.status}`);
  return resp.json();
}

// ── Router ────────────────────────────────────────────────────

function route() {
  const hash = (location.hash || "#/").split("?")[0];
  const parts = hash.slice(2).split("/");

  document.querySelectorAll(".nav-links a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("href") === hash.split("/").slice(0, 2).join("/") || (hash === "#/" && a.getAttribute("href") === "#/"));
  });

  // Bottom nav active state
  const navMap = { "": "home", "search": "search", "rankings": "rankings", "trips": "trips", "about": "about" };
  const activeNav = navMap[parts[0]] || "";
  document.querySelectorAll("#bottom-nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.nav === activeNav);
  });

  window.scrollTo(0, 0);

  if (parts[0] === "" || parts[0] === undefined) return viewOverview();
  if (parts[0] === "search") return viewSearch();
  if (parts[0] === "route-stats" && parts[1]) return viewRouteStats(decodeURIComponent(parts[1]));
  if (parts[0] === "route" && parts[1]) return viewRoute(decodeURIComponent(parts[1]));
  if (parts[0] === "rankings") return viewRankings();
  if (parts[0] === "trips") return viewTrips();
  if (parts[0] === "compare") return viewCompare();
  if (parts[0] === "about") return viewAbout();
  return viewOverview();
}

window.addEventListener("hashchange", route);

// ── Hash query params ────────────────────────────────────────

function hashParams() {
  const hash = location.hash || "";
  const qIdx = hash.indexOf("?");
  if (qIdx === -1) return {};
  const params = {};
  new URLSearchParams(hash.slice(qIdx + 1)).forEach((v, k) => { params[k] = v; });
  return params;
}

// ── Helpers ───────────────────────────────────────────────────

function loading() {
  return `<div class="loading"><div class="spinner"></div>Chargement...</div>`;
}

function skeleton(type = "page") {
  if (type === "stats") return `
    <div class="skeleton-cards">
      <div class="skeleton skeleton-card"></div>
      <div class="skeleton skeleton-card"></div>
      <div class="skeleton skeleton-card"></div>
      <div class="skeleton skeleton-card"></div>
    </div>
    <div class="skeleton skeleton-text medium"></div>
  `;
  if (type === "chart") return `
    <div class="card" style="padding:1rem">
      ${Array(5).fill('<div class="skeleton skeleton-bar"></div>').join("")}
    </div>
  `;
  if (type === "list") return `
    ${Array(4).fill('<div class="skeleton skeleton-route"></div>').join("")}
  `;
  return `
    <div class="skeleton skeleton-title"></div>
    <div class="skeleton-cards">
      <div class="skeleton skeleton-card"></div>
      <div class="skeleton skeleton-card"></div>
      <div class="skeleton skeleton-card"></div>
      <div class="skeleton skeleton-card"></div>
    </div>
    <div class="skeleton skeleton-text medium"></div>
    <div style="margin-top:1.5rem">
      ${Array(3).fill('<div class="skeleton skeleton-route"></div>').join("")}
    </div>
  `;
}

function reliabilityScore(onTimePct) {
  if (onTimePct == null) return { letter: "-", cls: "" };
  if (onTimePct >= 90) return { letter: "A", cls: "score-A" };
  if (onTimePct >= 75) return { letter: "B", cls: "score-B" };
  if (onTimePct >= 60) return { letter: "C", cls: "score-C" };
  if (onTimePct >= 40) return { letter: "D", cls: "score-D" };
  return { letter: "E", cls: "score-E" };
}

function scoreBadge(onTimePct) {
  const s = reliabilityScore(onTimePct);
  if (!s.cls) return "";
  return `<span class="score-badge ${s.cls}">${s.letter}</span>`;
}

function delayColor(seconds) {
  if (seconds === null || seconds === undefined) return "primary";
  const abs = Math.abs(seconds);
  if (abs < 60) return "green";
  if (abs < 180) return "orange";
  return "red";
}

function formatDelay(seconds, short = false) {
  if (seconds === null || seconds === undefined) return "\u00e0 l\u2019heure";
  const raw = Math.round(seconds);
  const abs = Math.abs(raw);
  if (abs < 60) return "\u00e0 l\u2019heure";
  const min = Math.floor(abs / 60);
  if (short) return raw > 0 ? `+${min} min` : `\u2212${min} min`;
  if (raw > 0) return `${min} min de retard`;
  return `${min} min d\u2019avance`;
}

function formatDelayExact(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const raw = Math.round(seconds);
  const abs = Math.abs(raw);
  const min = Math.floor(abs / 60);
  const sec = abs % 60;
  const sign = raw > 0 ? "+" : "\u2212";
  if (abs < 60) return "\u00e0 l\u2019heure";
  if (sec > 0) return `${sign}${min}m${sec.toString().padStart(2, "0")}s`;
  return `${sign}${min} min`;
}

function delayColorCSS(seconds) {
  const c = delayColor(seconds);
  return c === "green" ? "var(--green)" : c === "orange" ? "var(--orange)" : c === "red" ? "var(--red)" : "var(--primary)";
}

function routeBadge(shortName, color) {
  const bg = color && color !== "" ? `#${color}` : "#6b7280";
  const r = parseInt(color?.slice(0, 2) || "6b", 16);
  const g = parseInt(color?.slice(2, 4) || "72", 16);
  const b = parseInt(color?.slice(4, 6) || "80", 16);
  const textColor = (r * 0.299 + g * 0.587 + b * 0.114) > 150 ? "#000" : "#fff";
  return `<span class="route-badge" style="background:${bg};color:${textColor}">${shortName}</span>`;
}

function barChart(rows, labelKey, valueKey, maxValue, colorFn) {
  if (!rows.length) return `<div class="empty"><div class="empty-text">Pas assez de donn\u00e9es</div></div>`;
  const max = maxValue || Math.max(...rows.map((r) => Math.abs(r[valueKey])), 1);
  return `<div class="bar-chart">${rows
    .map((r) => {
      const val = r[valueKey];
      const pct = Math.min(100, (Math.abs(val) / max) * 100);
      const color = colorFn ? colorFn(val) : "var(--primary)";
      return `<div class="bar-row">
        <span class="bar-label">${r[labelKey]}</span>
        <div class="bar-track">
          <div class="bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <span class="bar-value" style="color:${color}">${formatDelay(val, true)}</span>
      </div>`;
    })
    .join("")}</div>`;
}

// ── Trend chart ─────────────────────────────────────────

function trendChart(weeks) {
  if (!weeks || weeks.length < 2) return `<div style="text-align:center;color:var(--text-muted);font-size:0.82rem;padding:1rem">Pas assez de semaines de donn\u00e9es</div>`;
  const maxPct = 100;
  return `<div class="trend-chart">
    ${weeks.map((w, i) => {
      const h = Math.max(2, (w.on_time_percent / maxPct) * 100);
      const color = w.on_time_percent >= 75 ? "var(--green)" : w.on_time_percent >= 50 ? "var(--orange)" : "var(--red)";
      const label = w.week.slice(5);
      return `<div class="trend-bar-wrap" title="${w.week}: ${w.on_time_percent}% \u00e0 l\u2019heure (${w.total_observations} obs)">
        <div class="trend-bar" style="height:${h}%;background:${color}"></div>
        ${weeks.length <= 8 || i % Math.max(1, Math.floor(weeks.length / 6)) === 0 || i === weeks.length - 1 ? `<span class="trend-label">${label}</span>` : ""}
      </div>`;
    }).join("")}
  </div>`;
}

// ── Export helpers ───────────────────────────────────────

function exportCSV(data, filename) {
  if (!data.length) return;
  const keys = Object.keys(data[0]);
  const csv = [keys.join(","), ...data.map(r => keys.map(k => JSON.stringify(r[k] ?? "")).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function exportJSON(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderExportRow(data, name) {
  return `<div class="export-row">
    <button class="btn btn-outline btn-sm" onclick='exportCSV(${JSON.stringify(data).replace(/'/g, "\\u0027")}, "${name}.csv")'>CSV</button>
    <button class="btn btn-outline btn-sm" onclick='exportJSON(${JSON.stringify(data).replace(/'/g, "\\u0027")}, "${name}.json")'>JSON</button>
  </div>`;
}

// ── Share ────────────────────────────────────────────────

function shareStats(title, text) {
  if (navigator.share) {
    navigator.share({ title, text, url: location.href }).catch(() => {});
  } else {
    const overlay = document.createElement("div");
    overlay.className = "share-overlay";
    overlay.innerHTML = `<div class="share-modal">
      <h3>Partager</h3>
      <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:0.75rem">${text}</p>
      <div class="share-actions">
        <button class="btn" id="share-copy">Copier le lien</button>
        <button class="btn btn-outline" id="share-close">Fermer</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector("#share-copy").addEventListener("click", () => {
      navigator.clipboard.writeText(text + "\n" + location.href).then(() => {
        overlay.querySelector("#share-copy").textContent = "Copi\u00e9 !";
        setTimeout(() => overlay.remove(), 1000);
      });
    });
    overlay.querySelector("#share-close").addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  }
}

// ── Filter panel ─────────────────────────────────────────────

const _DAYS = [
  { val: 1, label: "Lun" },
  { val: 2, label: "Mar" },
  { val: 3, label: "Mer" },
  { val: 4, label: "Jeu" },
  { val: 5, label: "Ven" },
  { val: 6, label: "Sam" },
  { val: 0, label: "Dim" },
];

function renderFilterPanel(id) {
  return `
    <div class="filter-panel" id="${id}">
      <button class="filter-toggle" type="button">Filtres avanc\u00e9s</button>
      <div class="filter-body">
        <div class="filter-section">
          <div class="filter-section-label">Jours</div>
          <div class="pill-group" data-filter="days">
            ${_DAYS.map((d) => `<button class="pill active" data-val="${d.val}">${d.label}</button>`).join("")}
          </div>
        </div>
        <div class="filter-section">
          <div class="filter-section-label">Plage horaire</div>
          <div class="filter-row">
            <label>De</label>
            <input type="time" data-filter="time-from" value="">
            <label>\u00e0</label>
            <input type="time" data-filter="time-to" value="">
          </div>
        </div>
        <div class="filter-section">
          <div class="filter-section-label">P\u00e9riode</div>
          <div class="filter-row">
            <select data-filter="days-back">
              <option value="7">7 derniers jours</option>
              <option value="14">14 derniers jours</option>
              <option value="30" selected>30 derniers jours</option>
              <option value="60">60 derniers jours</option>
              <option value="90">90 derniers jours</option>
            </select>
          </div>
        </div>
        <div class="filter-section">
          <div class="filter-section-label">Vacances scolaires (Zone B)</div>
          <div class="pill-group" data-filter="holidays">
            <button class="pill active" data-val="all">Toutes p\u00e9riodes</button>
            <button class="pill" data-val="exclude">Hors vacances</button>
            <button class="pill" data-val="only">Vacances uniquement</button>
          </div>
        </div>
        <div class="filter-actions">
          <button class="btn" data-action="apply">Appliquer</button>
          <button class="btn btn-outline" data-action="reset">R\u00e9initialiser</button>
        </div>
      </div>
    </div>
  `;
}

function initFilterPanel(id, onApply) {
  const panel = document.getElementById(id);
  if (!panel) return;

  panel.querySelector(".filter-toggle").addEventListener("click", () => {
    panel.classList.toggle("open");
  });

  panel.querySelectorAll('[data-filter="days"] .pill').forEach((pill) => {
    pill.addEventListener("click", () => pill.classList.toggle("active"));
  });

  panel.querySelectorAll('[data-filter="holidays"] .pill').forEach((pill) => {
    pill.addEventListener("click", () => {
      panel.querySelectorAll('[data-filter="holidays"] .pill').forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
    });
  });

  panel.querySelector('[data-action="apply"]').addEventListener("click", () => {
    onApply(getFilterValues(id));
  });

  panel.querySelector('[data-action="reset"]').addEventListener("click", () => {
    panel.querySelectorAll('[data-filter="days"] .pill').forEach((p) => p.classList.add("active"));
    panel.querySelectorAll('[data-filter="holidays"] .pill').forEach((p) => p.classList.remove("active"));
    panel.querySelector('[data-filter="holidays"] .pill[data-val="all"]').classList.add("active");
    panel.querySelector('[data-filter="time-from"]').value = "";
    panel.querySelector('[data-filter="time-to"]').value = "";
    panel.querySelector('[data-filter="days-back"]').value = "30";
    onApply(getFilterValues(id));
  });
}

function getFilterValues(id) {
  const panel = document.getElementById(id);
  const activeDays = [...panel.querySelectorAll('[data-filter="days"] .pill.active')].map((p) => p.dataset.val);
  const allDaysSelected = activeDays.length === 7;
  const timeFrom = panel.querySelector('[data-filter="time-from"]').value || null;
  const timeTo = panel.querySelector('[data-filter="time-to"]').value || null;
  const daysBack = panel.querySelector('[data-filter="days-back"]').value;
  const holidays = panel.querySelector('[data-filter="holidays"] .pill.active')?.dataset.val || "all";

  return {
    days_of_week: allDaysSelected ? null : activeDays.join(","),
    time_from: timeFrom ? timeFrom.slice(0, 5) : null,
    time_to: timeTo ? timeTo.slice(0, 5) : null,
    days: daysBack,
    holidays,
  };
}

function buildFilterQS(filters, prefix = "&") {
  const parts = [];
  if (filters.days_of_week) parts.push(`days_of_week=${filters.days_of_week}`);
  if (filters.time_from) parts.push(`time_from=${filters.time_from}`);
  if (filters.time_to) parts.push(`time_to=${filters.time_to}`);
  if (filters.days) parts.push(`days=${filters.days}`);
  if (filters.holidays && filters.holidays !== "all") parts.push(`holidays=${filters.holidays}`);
  if (!parts.length) return "";
  return prefix + parts.join("&");
}

// ── Worst departures ─────────────────────────────────────────

function renderWorstDepartures(departures) {
  if (!departures || !departures.length) return `<div style="text-align:center;padding:0.75rem;color:var(--text-muted);font-size:0.85rem">Aucun d\u00e9part r\u00e9guli\u00e8rement en retard</div>`;
  return `<div class="worst-dep-list">${departures.map((d) => `
    <div class="worst-dep-item">
      <span class="worst-dep-time">${d.departure_time}</span>
      <span class="worst-dep-info">${d.total} passages</span>
      <span class="worst-dep-delay" style="color:${delayColorCSS(d.avg_delay_seconds)}">${formatDelayExact(d.avg_delay_seconds)}</span>
    </div>
  `).join("")}</div>`;
}

// ── Departure time list ──────────────────────────────────────

function renderDepartureList(departures, query) {
  const container = document.getElementById("dep-time-results");
  if (!container) return;

  let filtered = departures;
  if (query) {
    const q = query.trim();
    filtered = departures.filter((d) => d.departure_time.startsWith(q));
  }

  const shown = query ? filtered : filtered.slice(0, 15);
  const hasMore = !query && filtered.length > 15;

  if (!shown.length) {
    container.innerHTML = `<div style="text-align:center;color:var(--text-muted);padding:0.75rem;font-size:0.85rem">${query ? "Aucun horaire trouv\u00e9" : "Aucun horaire disponible"}</div>`;
    return;
  }

  container.innerHTML = `
    <div class="dep-time-list">
      ${shown.map((d) => `
        <div class="dep-time-item">
          <span class="dep-time-hour">${d.departure_time}</span>
          ${scoreBadge(d.on_time_percent)}
          <div class="dep-time-stats">
            <span class="dep-time-ontime" style="color:${d.on_time_percent >= 70 ? "var(--green)" : d.on_time_percent >= 50 ? "var(--orange)" : "var(--red)"}">${d.on_time_percent.toFixed(0)}%</span>
            <span class="dep-time-delay" style="color:${delayColorCSS(d.avg_delay_seconds)}">${formatDelayExact(d.avg_delay_seconds)}</span>
          </div>
          <span class="dep-time-count">${d.total_observations} pass.</span>
        </div>
      `).join("")}
    </div>
    ${hasMore ? `<div style="text-align:center;padding:0.5rem;font-size:0.78rem;color:var(--text-muted)">Recherchez votre horaire ci-dessus</div>` : ""}
  `;
}

// ── Stat cards block ─────────────────────────────────────────

function renderStatCards(stats) {
  return `
    <div class="card-grid">
      <div class="stat-card">
        <div class="value ${stats.on_time_percent >= 70 ? "green" : stats.on_time_percent >= 50 ? "orange" : "red"}">${stats.on_time_percent.toFixed(0)}%</div>
        <div class="label">\u00c0 l\u2019heure</div>
      </div>
      <div class="stat-card">
        <div class="value" style="color:${stats.avg_late_delay_seconds ? "var(--red)" : "var(--green)"}">${stats.avg_late_delay_seconds ? formatDelay(Math.round(stats.avg_late_delay_seconds), true) : "\u00e0 l\u2019heure"}</div>
        <div class="label">Quand en retard</div>
      </div>
      <div class="stat-card">
        <div class="value blue">${(stats.total_observations || 0).toLocaleString("fr")}</div>
        <div class="label">Passages</div>
      </div>
      <div class="stat-card">
        <div class="value ${(stats.late_5min_percent || 0) <= 10 ? "green" : (stats.late_5min_percent || 0) <= 25 ? "orange" : "red"}">${(stats.late_5min_percent || 0).toFixed(0)}%</div>
        <div class="label">&gt; 5 min retard</div>
      </div>
    </div>
    ${stats.first_observation ? `<div class="data-footnote">Depuis le ${new Date(stats.first_observation).toLocaleDateString("fr")}</div>` : ""}
    <div class="export-row">
      <button class="btn btn-outline btn-sm" onclick="shareStats('Keleur', '\u00c0 l\u2019heure: ${stats.on_time_percent?.toFixed(0) ?? "-"}% \u00b7 ${(stats.total_observations || 0).toLocaleString("fr")} passages')">Partager</button>
    </div>
  `;
}

// ── Trips (localStorage) ─────────────────────────────────────

function getTrips() {
  try { return JSON.parse(localStorage.getItem("keleur_trips") || "[]"); }
  catch { return []; }
}
function saveTrips(trips) { localStorage.setItem("keleur_trips", JSON.stringify(trips)); }

// ── View: Overview ───────────────────────────────────────────

async function viewOverview() {
  app().innerHTML = skeleton("page");

  try {
    const [overview, routes] = await Promise.all([api("/overview"), api("/routes")]);

    const routeTypes = { 0: "Tramway", 1: "M\u00e9tro", 3: "Bus" };
    const grouped = {};
    routes.forEach((r) => {
      const type = routeTypes[r.route_type] || "Autre";
      if (!grouped[type]) grouped[type] = [];
      grouped[type].push(r);
    });

    app().innerHTML = `
      <div class="search-bar">
        <span class="search-icon">\ud83d\udd0d</span>
        <input type="text" placeholder="Rechercher un arr\u00eat\u2026" id="home-search"
          onclick="location.hash='#/search';return false" readonly>
      </div>

      <div class="overview-stats">
        <div class="overview-stat">
          <div class="ov-value" style="color:var(--primary)">${overview.total_observations.toLocaleString("fr")}</div>
          <div class="ov-label">Passages</div>
        </div>
        <div class="overview-stat">
          <div class="ov-value" style="color:var(--primary)">${overview.routes_count}</div>
          <div class="ov-label">Lignes</div>
        </div>
        <div class="overview-stat">
          <div class="ov-value" style="color:${overview.on_time_percent >= 70 ? "var(--green)" : overview.on_time_percent >= 50 ? "var(--orange)" : "var(--red)"}">${overview.on_time_percent?.toFixed(0) ?? "\u2013"}%</div>
          <div class="ov-label">\u00c0 l\u2019heure</div>
        </div>
        <div class="overview-stat">
          <div class="ov-value" style="color:${delayColorCSS(overview.avg_delay_seconds)}">${formatDelay(Math.round(overview.avg_delay_seconds), true)}</div>
          <div class="ov-label">Retard moy.</div>
        </div>
      </div>

      ${Object.entries(grouped)
        .map(([type, list]) => `
          <h2 class="section-title">${type}</h2>
          <ul class="route-list">
            ${list.map((r) => `
              <a href="#/route/${encodeURIComponent(r.route_id)}" class="route-item">
                ${routeBadge(r.short_name, r.color)}
                <div class="route-info">
                  <div class="route-name">${r.long_name}</div>
                  <div class="route-meta">${r.total_observations} passages \u00b7 ${r.stops_observed} arr\u00eats</div>
                </div>
              </a>
            `).join("")}
          </ul>
        `).join("")}

      <a href="#/about" class="about-link-card">
        <span class="about-link-icon">&#x1F4D6;</span>
        <div class="about-link-text">
          <div class="about-link-title">Comment \u00e7a marche ?</div>
          <div class="about-link-sub">D\u00e9couvrez d\u2019o\u00f9 viennent nos donn\u00e9es et comment elles sont calcul\u00e9es</div>
        </div>
        <span class="about-link-arrow">\u203A</span>
      </a>
    `;
  } catch (err) {
    app().innerHTML = `<div class="empty"><div class="empty-text">Erreur de chargement : ${err.message}</div></div>`;
  }
}

// ── View: Route detail ───────────────────────────────────────

async function viewRoute(routeId) {
  app().innerHTML = skeleton("page");

  try {
    const [routes, directions] = await Promise.all([
      api("/routes"),
      api(`/routes/${encodeURIComponent(routeId)}/directions`),
    ]);

    const routeInfo = routes.find((r) => r.route_id === routeId) || {};

    const dirOptions = directions.length
      ? directions.map((d) => ({ dir: d.direction_id, headsign: d.headsign }))
      : [{ dir: 0, headsign: null }, { dir: 1, headsign: null }];

    const hp = hashParams();
    const preHeadsign = hp.headsign || null;
    const preStopName = hp.stop || null;

    let initialDirIdx = 0;
    if (preHeadsign) {
      const idx = dirOptions.findIndex((d) => d.headsign === preHeadsign);
      if (idx >= 0) initialDirIdx = idx;
    }

    const initOpt = dirOptions[initialDirIdx];
    const hsParam = initOpt.headsign ? `headsign=${encodeURIComponent(initOpt.headsign)}` : "";
    const initialStops = await api(`/routes/${encodeURIComponent(routeId)}/stops?${hsParam}`);

    app().innerHTML = `
      <a href="javascript:void(0)" onclick="history.back()" class="back-link">\u2190 Retour</a>

      <div class="page-header">
        ${routeBadge(routeInfo.short_name || routeId, routeInfo.color)}
        <div class="page-header-text">
          <h1>${routeInfo.long_name || routeId}</h1>
          <div class="subtitle">${(routeInfo.total_observations || 0).toLocaleString("fr")} passages mesur\u00e9s
            \u00b7 <a href="#/route-stats/${encodeURIComponent(routeId)}" style="color:var(--primary);text-decoration:none;font-weight:600">Stats globales</a>
          </div>
        </div>
      </div>

      <div class="select-group">
        <select id="sel-dir">
          ${dirOptions.map((d, i) => `<option value="${i}" ${i === initialDirIdx ? "selected" : ""}>${d.headsign ? "Vers " + d.headsign : "Direction " + (d.dir === 0 ? "A" : "B")}</option>`).join("")}
        </select>
        <select id="sel-stop">
          ${initialStops.map((s) => `<option value="${s.stop_id}" ${preStopName && s.stop_name === preStopName ? "selected" : ""}>${s.stop_name}</option>`).join("")}
        </select>
        <button class="btn btn-outline btn-sm" id="btn-save-trip">\u2606 Sauvegarder</button>
      </div>

      ${renderFilterPanel("stop-filters")}

      <div id="route-stats">${loading()}</div>
    `;

    const selDir = $("#sel-dir");
    const selStop = $("#sel-stop");
    const stopsCache = {};
    stopsCache[initialDirIdx] = initialStops;

    async function updateStopOptions() {
      const idx = parseInt(selDir.value);
      if (!stopsCache[idx]) {
        const opt = dirOptions[idx];
        const hs = opt.headsign ? `headsign=${encodeURIComponent(opt.headsign)}` : "";
        stopsCache[idx] = await api(`/routes/${encodeURIComponent(routeId)}/stops?${hs}`);
      }
      const stops = stopsCache[idx] || [];
      selStop.innerHTML = stops.map((s) => `<option value="${s.stop_id}">${s.stop_name}</option>`).join("");
      if (!stops.length) selStop.innerHTML = `<option>Aucun arr\u00eat</option>`;
    }

    async function loadStats(filters) {
      const stopId = selStop.value;
      if (!stopId) return;
      if (!filters) filters = getFilterValues("stop-filters");
      const fqs = buildFilterQS(filters);
      const idx = parseInt(selDir.value);
      const currentHeadsign = dirOptions[idx]?.headsign;

      $("#route-stats").innerHTML = skeleton("stats") + skeleton("chart");

      try {
        let base = `route_id=${encodeURIComponent(routeId)}&stop_id=${encodeURIComponent(stopId)}`;
        if (currentHeadsign) base += `&headsign=${encodeURIComponent(currentHeadsign)}`;
        const [stats, byDay, byHour, worst, trend] = await Promise.all([
          api(`/stats?${base}${fqs}`),
          api(`/stats/by-day?${base}${fqs}`),
          api(`/stats/by-hour?${base}${fqs}`),
          api(`/stats/worst-departures?${base}${fqs}`),
          api(`/stats/trend?${base}&days=90`),
        ]);

        if (stats.total_observations === 0) {
          $("#route-stats").innerHTML = `<div class="empty"><div class="empty-text">Pas de donn\u00e9es pour ces filtres</div></div>`;
          return;
        }

        $("#route-stats").innerHTML = `
          ${renderStatCards(stats)}

          <div class="charts-grid">
            <div>
              <h2 class="section-title">Par jour</h2>
              <div class="card">
                ${barChart(byDay, "day_name", "avg_delay_seconds", null, (v) => delayColorCSS(v))}
              </div>
            </div>
            <div>
              <h2 class="section-title">Par heure</h2>
              <div class="card">
                ${barChart(byHour.map((h) => ({ ...h, label: h.hour + "h" })), "label", "avg_delay_seconds", null, (v) => delayColorCSS(v))}
              </div>
            </div>
          </div>

          ${trend.length >= 2 ? `
            <h2 class="section-title">\u00c9volution hebdomadaire</h2>
            <div class="card">${trendChart(trend)}</div>
          ` : ""}

          <h2 class="section-title">Mon horaire</h2>
          <div class="card">
            <input type="text" id="dep-time-search" placeholder="Tapez une heure, ex : 07:30" class="input-search-time">
            <div id="dep-time-results">${loading()}</div>
          </div>

          ${worst.length ? `
            <h2 class="section-title">D\u00e9parts les plus en retard</h2>
            <div class="card">${renderWorstDepartures(worst)}</div>
          ` : ""}
        `;

        const depData = await api(`/stats/departures?${base}${fqs}`);
        renderDepartureList(depData, null);

        $("#dep-time-search").addEventListener("input", () => {
          renderDepartureList(depData, $("#dep-time-search").value);
        });

      } catch (err) {
        $("#route-stats").innerHTML = `<div class="empty">Erreur : ${err.message}</div>`;
      }
    }

    selDir.addEventListener("change", async () => { await updateStopOptions(); loadStats(); });
    selStop.addEventListener("change", () => loadStats());
    initFilterPanel("stop-filters", loadStats);

    $("#btn-save-trip").addEventListener("click", () => {
      const idx = parseInt(selDir.value);
      const opt = dirOptions[idx];
      const trips = getTrips();
      const trip = {
        route_id: routeId,
        short_name: routeInfo.short_name,
        long_name: routeInfo.long_name,
        color: routeInfo.color,
        stop_id: selStop.value,
        stop_name: selStop.options[selStop.selectedIndex]?.text,
        direction_id: opt.dir,
      };
      const exists = trips.some(
        (t) => t.route_id === trip.route_id && t.stop_id === trip.stop_id && t.direction_id === trip.direction_id
      );
      if (!exists) { trips.push(trip); saveTrips(trips); }
      $("#btn-save-trip").textContent = "\u2605 Sauvegard\u00e9 !";
      setTimeout(() => { $("#btn-save-trip").textContent = "\u2606 Sauvegarder"; }, 1500);
    });

    loadStats();
  } catch (err) {
    app().innerHTML = `<div class="empty"><div class="empty-text">Erreur : ${err.message}</div></div>`;
  }
}

// ── View: Route global stats ─────────────────────────────────

async function viewRouteStats(routeId) {
  app().innerHTML = skeleton("page");

  try {
    const routes = await api("/routes");
    const routeInfo = routes.find((r) => r.route_id === routeId) || {};

    app().innerHTML = `
      <a href="javascript:void(0)" onclick="history.back()" class="back-link">\u2190 Retour</a>

      <div class="page-header">
        ${routeBadge(routeInfo.short_name || routeId, routeInfo.color)}
        <div class="page-header-text">
          <h1>${routeInfo.long_name || routeId}</h1>
          <div class="subtitle">Statistiques globales</div>
        </div>
      </div>

      ${renderFilterPanel("route-filters")}

      <div id="route-stats-content">${loading()}</div>

      <div style="margin-top:1.25rem;text-align:center">
        <a href="#/route/${encodeURIComponent(routeId)}" class="btn btn-outline">D\u00e9tail par arr\u00eat</a>
      </div>
    `;

    async function loadRouteStats(filters) {
      if (!filters) filters = getFilterValues("route-filters");
      const rid = encodeURIComponent(routeId);

      $("#route-stats-content").innerHTML = skeleton("stats") + skeleton("chart");

      try {
        const qs = buildFilterQS(filters, "?");
        const [stats, byDay, byHour, trend] = await Promise.all([
          api(`/routes/${rid}/stats${qs}`),
          api(`/routes/${rid}/stats/by-day${qs}`),
          api(`/routes/${rid}/stats/by-hour${qs}`),
          api(`/routes/${rid}/stats/trend?days=90`),
        ]);

        if (stats.total_observations === 0) {
          $("#route-stats-content").innerHTML = `<div class="empty"><div class="empty-text">Pas de donn\u00e9es pour ces filtres</div></div>`;
          return;
        }

        $("#route-stats-content").innerHTML = `
          ${renderStatCards(stats)}

          <div class="charts-grid">
            <div>
              <h2 class="section-title">Par jour</h2>
              <div class="card">
                ${barChart(byDay, "day_name", "avg_delay_seconds", null, (v) => delayColorCSS(v))}
              </div>
            </div>
            <div>
              <h2 class="section-title">Par heure</h2>
              <div class="card">
                ${barChart(byHour.map((h) => ({ ...h, label: h.hour + "h" })), "label", "avg_delay_seconds", null, (v) => delayColorCSS(v))}
              </div>
            </div>
          </div>

          ${trend.length >= 2 ? `
            <h2 class="section-title">\u00c9volution hebdomadaire</h2>
            <div class="card">${trendChart(trend)}</div>
          ` : ""}
        `;
      } catch (err) {
        $("#route-stats-content").innerHTML = `<div class="empty">Erreur : ${err.message}</div>`;
      }
    }

    initFilterPanel("route-filters", loadRouteStats);
    loadRouteStats();
  } catch (err) {
    app().innerHTML = `<div class="empty"><div class="empty-text">Erreur : ${err.message}</div></div>`;
  }
}

// ── View: Search ─────────────────────────────────────────────

async function viewSearch() {
  app().innerHTML = `
    <div class="search-bar" style="margin-top:0.5rem">
      <span class="search-icon">\ud83d\udd0d</span>
      <input type="text" id="search-input" placeholder="Nom de l\u2019arr\u00eat\u2026" autofocus>
    </div>
    <div id="search-results">
      <div class="empty"><div class="empty-text">Tapez le nom d\u2019un arr\u00eat pour trouver ses lignes</div></div>
    </div>
  `;

  const input = $("#search-input");
  let debounce = null;

  input.addEventListener("input", () => {
    clearTimeout(debounce);
    const q = input.value.trim();
    if (q.length < 2) {
      $("#search-results").innerHTML = `<div class="empty"><div class="empty-text">Tapez au moins 2 caract\u00e8res</div></div>`;
      return;
    }
    debounce = setTimeout(async () => {
      try {
        const results = await api(`/search/stops?q=${encodeURIComponent(q)}`);
        if (!results.length) {
          $("#search-results").innerHTML = `<div class="empty"><div class="empty-text">Aucun r\u00e9sultat pour \u00ab\u202f${q}\u202f\u00bb</div></div>`;
          return;
        }
        const grouped = {};
        results.forEach((r) => {
          if (!grouped[r.stop_name]) grouped[r.stop_name] = [];
          grouped[r.stop_name].push(r);
        });

        $("#search-results").innerHTML = Object.entries(grouped).map(([stopName, items]) => `
          <div class="search-stop-group">
            <div class="search-stop-name">${stopName}</div>
            ${items.map((item) => `
              <a href="#/route/${encodeURIComponent(item.route_id)}?stop=${encodeURIComponent(item.stop_name)}&headsign=${encodeURIComponent(item.headsign)}" class="search-result-item">
                ${routeBadge(item.short_name, item.color)}
                <div class="search-result-info">
                  <span class="search-result-line">${item.long_name}</span>
                  <span class="search-result-dir">Vers ${item.headsign}</span>
                </div>
              </a>
            `).join("")}
          </div>
        `).join("");
      } catch (err) {
        $("#search-results").innerHTML = `<div class="empty">Erreur : ${err.message}</div>`;
      }
    }, 300);
  });
}

// ── View: Rankings ───────────────────────────────────────────

async function viewRankings() {
  app().innerHTML = skeleton("list");

  try {
    const [stops, routes] = await Promise.all([
      api("/rankings/stops"),
      api("/rankings/routes"),
    ]);

    function renderStopList(items) {
      if (!items.length) return `<div class="empty"><div class="empty-text">Pas assez de donn\u00e9es</div></div>`;
      return items.map((s, i) => `
        <a href="#/route/${encodeURIComponent(s.route_id)}?stop=${encodeURIComponent(s.stop_name)}&headsign=${encodeURIComponent(s.headsign)}" class="ranking-item">
          <span class="ranking-rank">#${i + 1}</span>
          ${scoreBadge(s.on_time_percent)}
          ${routeBadge(s.short_name, s.color)}
          <div class="ranking-info">
            <div class="ranking-name">${s.stop_name}</div>
            <div class="ranking-meta">Vers ${s.headsign} \u00b7 ${s.total_passages} passages</div>
          </div>
          <div class="ranking-delay">
            <div class="delay-value" style="color:${s.avg_late_delay_seconds ? "var(--red)" : "var(--green)"}">${s.avg_late_delay_seconds ? formatDelay(Math.round(s.avg_late_delay_seconds), true) : "\u00e0 l\u2019heure"}</div>
            <div class="ranking-ontime">${s.on_time_percent}% \u00e0 l\u2019heure</div>
          </div>
        </a>
      `).join("");
    }

    function renderRouteList(items) {
      if (!items.length) return `<div class="empty"><div class="empty-text">Pas assez de donn\u00e9es</div></div>`;
      return items.map((r, i) => `
        <a href="#/route-stats/${encodeURIComponent(r.route_id)}" class="ranking-item">
          <span class="ranking-rank">#${i + 1}</span>
          ${scoreBadge(r.on_time_percent)}
          ${routeBadge(r.short_name, r.color)}
          <div class="ranking-info">
            <div class="ranking-name">${r.long_name}</div>
            <div class="ranking-meta">${r.total_passages} passages</div>
          </div>
          <div class="ranking-delay">
            <div class="delay-value" style="color:${r.avg_late_delay_seconds ? "var(--red)" : "var(--green)"}">${r.avg_late_delay_seconds ? formatDelay(Math.round(r.avg_late_delay_seconds), true) : "\u00e0 l\u2019heure"}</div>
            <div class="ranking-ontime">${r.on_time_percent}% \u00e0 l\u2019heure</div>
          </div>
        </a>
      `).join("");
    }

    app().innerHTML = `
      <div class="pill-group" style="margin-bottom:1rem" id="ranking-tabs">
        <button class="pill active" data-tab="stops">Arr\u00eats</button>
        <button class="pill" data-tab="routes">Lignes</button>
      </div>

      <div id="ranking-content">
        <div id="tab-stops">
          <h2 class="section-title" style="margin-top:0">Pires arr\u00eats</h2>
          ${renderStopList(stops.worst)}
          <h2 class="section-title">Meilleurs arr\u00eats</h2>
          ${renderStopList(stops.best)}
        </div>
        <div id="tab-routes" style="display:none">
          <h2 class="section-title" style="margin-top:0">Pires lignes</h2>
          ${renderRouteList(routes.worst)}
          <h2 class="section-title">Meilleures lignes</h2>
          ${renderRouteList(routes.best)}
        </div>
      </div>

      <div style="margin-top:1.25rem;text-align:center">
        <a href="#/compare" class="btn btn-outline">Comparer des lignes</a>
      </div>
    `;

    document.querySelectorAll("#ranking-tabs .pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        document.querySelectorAll("#ranking-tabs .pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        const tab = pill.dataset.tab;
        document.getElementById("tab-stops").style.display = tab === "stops" ? "" : "none";
        document.getElementById("tab-routes").style.display = tab === "routes" ? "" : "none";
      });
    });
  } catch (err) {
    app().innerHTML = `<div class="empty"><div class="empty-text">Erreur de chargement : ${err.message}</div></div>`;
  }
}

// ── View: My trips ───────────────────────────────────────────

async function viewTrips() {
  const trips = getTrips();

  if (!trips.length) {
    app().innerHTML = `
      <h2 class="section-title" style="margin-top:0">Mes trajets</h2>
      <div class="empty">
        <div class="empty-icon">\ud83d\ude8f</div>
        <div class="empty-text">
          Aucun trajet sauvegard\u00e9.<br>
          Allez sur une ligne, choisissez un arr\u00eat et cliquez \u00ab\u202fSauvegarder\u202f\u00bb.
        </div>
      </div>
    `;
    return;
  }

  const statsPromises = trips.map((t) =>
    api(`/stats?route_id=${encodeURIComponent(t.route_id)}&stop_id=${encodeURIComponent(t.stop_id)}&days=30`)
      .catch(() => null)
  );
  const allStats = await Promise.all(statsPromises);

  app().innerHTML = `
    <h2 class="section-title" style="margin-top:0">Mes trajets</h2>
    ${trips
      .map((t, i) => {
        const s = allStats[i];
        const delayStr = s && s.total_observations > 0 ? formatDelay(Math.round(s.avg_delay_seconds), true) : "\u2013";
        const onTime = s && s.total_observations > 0 ? `${s.on_time_percent.toFixed(0)}%` : "\u2013";
        return `
          <div class="trip-card">
            ${routeBadge(t.short_name, t.color)}
            <div class="trip-info">
              <div style="font-weight:600;font-size:0.9rem">${t.stop_name}</div>
              <div style="font-size:0.78rem;color:var(--text-muted)">
                Moy. <span style="color:${delayColorCSS(s?.avg_delay_seconds)}">${delayStr}</span>
                \u00b7 \u00c0 l\u2019heure ${onTime}
              </div>
            </div>
            <div class="trip-actions">
              <a href="#/route/${encodeURIComponent(t.route_id)}" class="btn btn-sm btn-outline">Voir</a>
              <button class="btn btn-sm btn-danger" onclick="removeTrip(${i})">\u2715</button>
            </div>
          </div>
        `;
      })
      .join("")}
  `;
}

window.removeTrip = function (idx) {
  const trips = getTrips();
  trips.splice(idx, 1);
  saveTrips(trips);
  viewTrips();
};

// ── View: Compare ───────────────────────────────────────

async function viewCompare() {
  app().innerHTML = skeleton("page");

  try {
    const routes = await api("/routes");

    app().innerHTML = `
      <a href="javascript:void(0)" onclick="history.back()" class="back-link">\u2190 Retour</a>
      <h1 style="font-size:1.15rem;font-weight:700;margin-bottom:1rem">Comparer des lignes</h1>

      <div class="compare-select-group">
        <select id="cmp-1"><option value="">Ligne 1\u2026</option>${routes.map((r) => `<option value="${r.route_id}">${r.short_name} \u2014 ${r.long_name}</option>`).join("")}</select>
        <select id="cmp-2"><option value="">Ligne 2\u2026</option>${routes.map((r) => `<option value="${r.route_id}">${r.short_name} \u2014 ${r.long_name}</option>`).join("")}</select>
        <select id="cmp-3"><option value="">Ligne 3 (opt.)</option><option value="">Aucune</option>${routes.map((r) => `<option value="${r.route_id}">${r.short_name} \u2014 ${r.long_name}</option>`).join("")}</select>
      </div>
      <button class="btn" id="cmp-go" style="width:100%;margin-bottom:1rem">Comparer</button>
      <div id="cmp-results"></div>
    `;

    document.getElementById("cmp-go").addEventListener("click", async () => {
      const ids = [$("#cmp-1").value, $("#cmp-2").value, $("#cmp-3").value].filter(Boolean);
      if (ids.length < 2) {
        document.getElementById("cmp-results").innerHTML = `<div class="empty"><div class="empty-text">S\u00e9lectionnez au moins 2 lignes</div></div>`;
        return;
      }

      document.getElementById("cmp-results").innerHTML = skeleton("stats");

      try {
        const stats = await Promise.all(ids.map((id) => api(`/routes/${encodeURIComponent(id)}/stats?days=30`)));
        const infos = ids.map((id) => routes.find((r) => r.route_id === id) || {});

        document.getElementById("cmp-results").innerHTML = `
          <div class="card" style="overflow-x:auto">
            <table class="compare-table">
              <thead>
                <tr>
                  <th>Ligne</th>
                  <th>Score</th>
                  <th>\u00c0 l\u2019heure</th>
                  <th>Retard moy.</th>
                  <th>&gt; 5 min</th>
                  <th>Passages</th>
                </tr>
              </thead>
              <tbody>
                ${stats.map((s, i) => `
                  <tr>
                    <td>${routeBadge(infos[i].short_name, infos[i].color)}</td>
                    <td>${scoreBadge(s.on_time_percent)}</td>
                    <td style="font-weight:700;color:${s.on_time_percent >= 70 ? "var(--green)" : s.on_time_percent >= 50 ? "var(--orange)" : "var(--red)"}">${s.on_time_percent?.toFixed(0) ?? "-"}%</td>
                    <td style="color:${delayColorCSS(s.avg_delay_seconds)}">${formatDelay(Math.round(s.avg_delay_seconds || 0), true)}</td>
                    <td>${(s.late_5min_percent || 0).toFixed(0)}%</td>
                    <td>${(s.total_observations || 0).toLocaleString("fr")}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>

          <div class="export-row" style="margin-top:0.5rem">
            <button class="btn btn-outline btn-sm" onclick='exportCSV(${JSON.stringify(stats.map((s, i) => ({ ligne: infos[i].short_name, on_time_pct: s.on_time_percent, avg_delay: s.avg_delay_seconds, late_5min_pct: s.late_5min_percent, passages: s.total_observations }))).replace(/'/g, "\\u0027")}, "comparaison.csv")'>Exporter CSV</button>
          </div>
        `;
      } catch (err) {
        document.getElementById("cmp-results").innerHTML = `<div class="empty">Erreur : ${err.message}</div>`;
      }
    });
  } catch (err) {
    app().innerHTML = `<div class="empty"><div class="empty-text">Erreur : ${err.message}</div></div>`;
  }
}

// ── View: About ─────────────────────────────────────────

async function viewAbout() {
  let statsHtml = "";
  try {
    const ov = await api("/overview");
    statsHtml = `
      <div class="about-stats">
        <div class="about-stat">
          <div class="about-stat-value">${ov.total_observations.toLocaleString("fr")}</div>
          <div class="about-stat-label">mesures enregistr\u00e9es</div>
        </div>
        <div class="about-stat">
          <div class="about-stat-value">${ov.routes_count}</div>
          <div class="about-stat-label">lignes suivies</div>
        </div>
        <div class="about-stat">
          <div class="about-stat-value">${ov.stops_count}</div>
          <div class="about-stat-label">arr\u00eats couverts</div>
        </div>
        <div class="about-stat">
          <div class="about-stat-value">30s</div>
          <div class="about-stat-label">fr\u00e9quence de mesure</div>
        </div>
      </div>
    `;
  } catch {}

  app().innerHTML = `
    <a href="javascript:void(0)" onclick="history.back()" class="back-link">\u2190 Retour</a>

    <div class="about-hero">
      <h1>Comment fonctionne Keleur\u202f?</h1>
      <p class="about-hero-sub">Transparence totale sur nos donn\u00e9es et notre m\u00e9thode de calcul.</p>
    </div>

    ${statsHtml}

    <div class="about-section">
      <div class="about-step">
        <div class="about-step-num">1</div>
        <div class="about-step-content">
          <h2>On r\u00e9cup\u00e8re les horaires officiels</h2>
          <p>Il\u00e9via publie les horaires th\u00e9oriques de toutes ses lignes (bus, tram, m\u00e9tro) dans un format standardis\u00e9 appel\u00e9 <strong>GTFS</strong>. Ce fichier contient chaque arr\u00eat, chaque ligne, et chaque heure de passage pr\u00e9vue.</p>
          <p>Keleur t\u00e9l\u00e9charge ces horaires automatiquement chaque jour.</p>
          <details class="about-details">
            <summary>D\u00e9tails techniques</summary>
            <p>Le fichier GTFS statique est publi\u00e9 par Il\u00e9via sur <strong>transport.data.gouv.fr</strong> (licence ouverte). Il contient les tables <code>routes</code>, <code>stops</code>, <code>trips</code> et <code>stop_times</code>. Keleur v\u00e9rifie le hash SHA-256 pour ne r\u00e9importer que si le fichier a chang\u00e9.</p>
          </details>
        </div>
      </div>

      <div class="about-step">
        <div class="about-step-num">2</div>
        <div class="about-step-content">
          <h2>On capte la position en temps r\u00e9el</h2>
          <p>En parall\u00e8le, Il\u00e9via diffuse en continu l\u2019\u00e9tat de chaque v\u00e9hicule en circulation\u202f: est-il en avance\u202f? En retard\u202f? De combien\u202f?</p>
          <p>Keleur interroge ce flux <strong>toutes les 30 secondes</strong>, 24 heures sur 24, 7 jours sur 7.</p>
          <details class="about-details">
            <summary>D\u00e9tails techniques</summary>
            <p>Le flux temps r\u00e9el est au format <strong>GTFS-RT</strong> (Protocol Buffers). Keleur consomme les entit\u00e9s <code>TripUpdate</code> qui fournissent, pour chaque trip en cours, l\u2019heure de d\u00e9part estim\u00e9e \u00e0 chaque arr\u00eat (<code>StopTimeUpdate.departure</code>). Le flux est proxifi\u00e9 par transport.data.gouv.fr.</p>
          </details>
        </div>
      </div>

      <div class="about-step">
        <div class="about-step-num">3</div>
        <div class="about-step-content">
          <h2>On calcule le retard</h2>
          <p>Pour chaque passage \u00e0 chaque arr\u00eat, Keleur fait un calcul simple\u202f:</p>
          <div class="about-formula">
            <strong>Retard</strong> = heure r\u00e9elle \u2212 heure pr\u00e9vue
          </div>
          <div class="about-example">
            <div class="about-example-title">Exemple concret</div>
            <p>Le bus L1 est pr\u00e9vu \u00e0 l\u2019arr\u00eat R\u00e9publique \u00e0 <strong>08h15</strong>.<br>
            Il\u00e9via signale qu\u2019il passera en r\u00e9alit\u00e9 \u00e0 <strong>08h19</strong>.</p>
            <p>Keleur enregistre\u202f: <strong>08h19 \u2212 08h15 = +4 minutes de retard</strong>.</p>
            <p>Si le m\u00eame bus \u00e9tait pass\u00e9 \u00e0 08h14, Keleur aurait enregistr\u00e9 <strong>\u22121 minute</strong> (1 minute d\u2019avance).</p>
          </div>
          <p>Si l\u2019\u00e9cart est <strong>inf\u00e9rieur \u00e0 1 minute</strong> (en avance ou en retard), on consid\u00e8re que le bus est <strong>\u00e0 l\u2019heure</strong>. Au-del\u00e0, il est compt\u00e9 comme en retard.</p>
          <details class="about-details">
            <summary>D\u00e9tails techniques</summary>
            <p>Le calcul est : <code>delay = realtime_dep \u2212 scheduled_dep</code> (en secondes). Les observations avec un d\u00e9calage sup\u00e9rieur \u00e0 1 heure sont \u00e9cart\u00e9es (probable d\u00e9calage de date). La d\u00e9duplication est faite sur le tuple <code>(trip_id, stop_id, scheduled_dep)</code> pour \u00e9viter les doublons li\u00e9s au polling fr\u00e9quent.</p>
          </details>
        </div>
      </div>

      <div class="about-step">
        <div class="about-step-num">4</div>
        <div class="about-step-content">
          <h2>On agr\u00e8ge les statistiques</h2>
          <p>Toutes ces mesures individuelles sont stock\u00e9es et agr\u00e9g\u00e9es pour produire des statistiques fiables\u202f: taux de ponctualit\u00e9, retard moyen, pires horaires, comparaisons par jour ou par heure.</p>
          <p>Plus on accumule de mesures, plus les r\u00e9sultats sont repr\u00e9sentatifs.</p>
          <details class="about-details">
            <summary>D\u00e9tails techniques</summary>
            <p>Les donn\u00e9es sont stock\u00e9es dans <strong>DuckDB</strong>, une base de donn\u00e9es analytique colonnaire optimis\u00e9e pour les agr\u00e9gations. Les requ\u00eates utilisent <code>avg()</code>, <code>median()</code>, <code>stddev()</code> et des percentiles. Les filtres disponibles\u202f: p\u00e9riode, jours de la semaine, plage horaire, vacances scolaires (zone B).</p>
          </details>
        </div>
      </div>
    </div>

    <div class="about-section">
      <h2 class="about-section-title">Ce que \u00ab\u202f\u00e0 l\u2019heure\u202f\u00bb veut dire</h2>
      <div class="about-card-block">
        <p>Un bus ou tram est consid\u00e9r\u00e9 <strong>\u00ab\u202f\u00e0 l\u2019heure\u202f\u00bb</strong> si son \u00e9cart avec l\u2019horaire pr\u00e9vu est <strong>inf\u00e9rieur \u00e0 1 minute</strong> (en avance ou en retard).</p>
        <p>C\u2019est un seuil strict. Beaucoup d\u2019op\u00e9rateurs consid\u00e8rent un bus \u00ab\u202f\u00e0 l\u2019heure\u202f\u00bb jusqu\u2019\u00e0 5 minutes de retard. Keleur fait le choix d\u2019un crit\u00e8re exigeant, plus proche du ressenti des usagers.</p>
      </div>
    </div>

    <div class="about-section">
      <h2 class="about-section-title">Sources et transparence</h2>
      <div class="about-card-block">
        <p>Toutes les donn\u00e9es utilis\u00e9es sont <strong>publiques et ouvertes</strong>, publi\u00e9es par Il\u00e9via / la M\u00e9tropole Europ\u00e9enne de Lille sur <strong>transport.data.gouv.fr</strong> sous licence ouverte.</p>
        <p>Keleur n\u2019est pas affili\u00e9 \u00e0 Il\u00e9via ni \u00e0 Keolis. C\u2019est un projet ind\u00e9pendant qui collecte, compare et agr\u00e8ge ces donn\u00e9es publiques pour les rendre lisibles.</p>
      </div>
    </div>

    <div class="about-section">
      <h2 class="about-section-title">Limites</h2>
      <div class="about-card-block">
        <ul class="about-list">
          <li><strong>D\u00e9pendance au flux Il\u00e9via</strong> \u2014 si le flux temps r\u00e9el est interrompu ou erron\u00e9, les mesures sont impact\u00e9es.</li>
          <li><strong>Pas de donn\u00e9es avant le lancement</strong> \u2014 les statistiques d\u00e9marrent \u00e0 la date de mise en service de Keleur.</li>
          <li><strong>M\u00e9tro non couvert</strong> \u2014 le m\u00e9tro automatique de Lille n\u2019est g\u00e9n\u00e9ralement pas inclus dans le flux GTFS-RT.</li>
        </ul>
      </div>
    </div>
  `;
}

// ── Pull-to-refresh ─────────────────────────────────────────

(function initPullToRefresh() {
  let startY = 0;
  let pulling = false;
  const threshold = 80;
  let indicator = null;

  function getIndicator() {
    if (!indicator) {
      indicator = document.createElement("div");
      indicator.className = "ptr-indicator";
      indicator.textContent = "↻ Actualiser";
      document.body.prepend(indicator);
    }
    return indicator;
  }

  document.addEventListener("touchstart", (e) => {
    if (window.scrollY === 0 && e.touches.length === 1) {
      startY = e.touches[0].clientY;
      pulling = true;
    }
  }, { passive: true });

  document.addEventListener("touchmove", (e) => {
    if (!pulling) return;
    const dy = e.touches[0].clientY - startY;
    if (dy > 10 && window.scrollY === 0) {
      const el = getIndicator();
      const progress = Math.min(dy / threshold, 1);
      el.style.transform = `translateY(${Math.min(dy * 0.4, 50)}px)`;
      el.style.opacity = progress;
      el.classList.toggle("ready", dy >= threshold);
    }
  }, { passive: true });

  document.addEventListener("touchend", () => {
    if (!pulling) return;
    pulling = false;
    const el = getIndicator();
    if (el.classList.contains("ready")) {
      el.textContent = "Chargement…";
      el.style.transform = "translateY(40px)";
      route();
      setTimeout(() => {
        el.style.transform = "translateY(-50px)";
        el.style.opacity = "0";
        setTimeout(() => { el.textContent = "↻ Actualiser"; el.classList.remove("ready"); }, 300);
      }, 600);
    } else {
      el.style.transform = "translateY(-50px)";
      el.style.opacity = "0";
    }
  }, { passive: true });
})();

// ── Offline banner ──────────────────────────────────────────

(function initOfflineBanner() {
  const banner = document.createElement("div");
  banner.className = "offline-banner";
  banner.textContent = "Hors connexion — données en cache";
  document.body.prepend(banner);

  function update() {
    banner.classList.toggle("visible", !navigator.onLine);
  }
  window.addEventListener("online", update);
  window.addEventListener("offline", update);
  update();
})();

// ── Service worker ───────────────────────────────────────────

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// ── Init ─────────────────────────────────────────────────────

route();
