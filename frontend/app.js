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

  if (parts[0] === "" || parts[0] === undefined) return viewOverview();
  if (parts[0] === "search") return viewSearch();
  if (parts[0] === "route-stats" && parts[1]) return viewRouteStats(decodeURIComponent(parts[1]));
  if (parts[0] === "route" && parts[1]) return viewRoute(decodeURIComponent(parts[1]));
  if (parts[0] === "rankings") return viewRankings();
  if (parts[0] === "trips") return viewTrips();
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
    const q = query.replace(":", "");
    filtered = departures.filter((d) => d.departure_time.replace(":", "").includes(q));
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
  app().innerHTML = loading();

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

      <div class="about-card">
        <h3 class="about-title">D\u2019o\u00f9 viennent ces donn\u00e9es ?</h3>
        <p>Keleur mesure la ponctualit\u00e9 r\u00e9elle des bus et tramways Il\u00e9via \u00e0 Lille.</p>
        <p>Toutes les 30 secondes, nous comparons la <strong>position en temps r\u00e9el</strong> de chaque v\u00e9hicule (fournie par Il\u00e9via via les donn\u00e9es GTFS-RT) avec l\u2019<strong>heure de passage pr\u00e9vue</strong> dans les horaires officiels.</p>
        <p>La diff\u00e9rence donne le retard ou l\u2019avance \u00e0 chaque arr\u00eat. Ces mesures, enregistr\u00e9es 24h/24, permettent de calculer des statistiques fiables.</p>
        <p class="about-muted">Donn\u00e9es publiques issues de <strong>transport.data.gouv.fr</strong>. Keleur les collecte, les compare et les agr\u00e8ge.</p>
      </div>
    `;
  } catch (err) {
    app().innerHTML = `<div class="empty"><div class="empty-text">Erreur de chargement : ${err.message}</div></div>`;
  }
}

// ── View: Route detail ───────────────────────────────────────

async function viewRoute(routeId) {
  app().innerHTML = loading();

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

      $("#route-stats").innerHTML = loading();

      try {
        let base = `route_id=${encodeURIComponent(routeId)}&stop_id=${encodeURIComponent(stopId)}`;
        if (currentHeadsign) base += `&headsign=${encodeURIComponent(currentHeadsign)}`;
        const [stats, byDay, byHour, worst] = await Promise.all([
          api(`/stats?${base}${fqs}`),
          api(`/stats/by-day?${base}${fqs}`),
          api(`/stats/by-hour?${base}${fqs}`),
          api(`/stats/worst-departures?${base}${fqs}`),
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

          <h2 class="section-title">Mon horaire</h2>
          <div class="card">
            <input type="text" id="dep-time-search" placeholder="Tapez une heure, ex : 07:30"
              style="width:100%;padding:0.6rem 0.85rem;background:var(--bg-input);color:var(--text);border:1px solid var(--border);border-radius:10px;font-size:0.9rem;font-family:var(--font);margin-bottom:0.6rem">
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
  app().innerHTML = loading();

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

      $("#route-stats-content").innerHTML = loading();

      try {
        const qs = buildFilterQS(filters, "?");
        const [stats, byDay, byHour] = await Promise.all([
          api(`/routes/${rid}/stats${qs}`),
          api(`/routes/${rid}/stats/by-day${qs}`),
          api(`/routes/${rid}/stats/by-hour${qs}`),
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
  app().innerHTML = loading();

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
      <h2 class="section-title">Pires arr\u00eats</h2>
      ${renderStopList(stops.worst)}

      <h2 class="section-title">Meilleurs arr\u00eats</h2>
      ${renderStopList(stops.best)}

      <h2 class="section-title">Pires lignes</h2>
      ${renderRouteList(routes.worst)}

      <h2 class="section-title">Meilleures lignes</h2>
      ${renderRouteList(routes.best)}
    `;
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

// ── Service worker ───────────────────────────────────────────

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// ── Init ─────────────────────────────────────────────────────

route();
