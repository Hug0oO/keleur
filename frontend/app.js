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
  const hash = location.hash || "#/";
  const parts = hash.slice(2).split("/");

  // Highlight active nav
  document.querySelectorAll(".nav-links a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("href") === hash.split("/").slice(0, 2).join("/") || (hash === "#/" && a.getAttribute("href") === "#/"));
  });

  if (parts[0] === "" || parts[0] === undefined) return viewOverview();
  if (parts[0] === "route" && parts[1]) return viewRoute(decodeURIComponent(parts[1]));
  if (parts[0] === "trips") return viewTrips();
  return viewOverview();
}

window.addEventListener("hashchange", route);

// ── Helpers ───────────────────────────────────────────────────

function loading() {
  return `<div class="loading"><div class="spinner"></div>Chargement...</div>`;
}

function delayColor(seconds) {
  if (seconds === null || seconds === undefined) return "blue";
  const abs = Math.abs(seconds);
  if (abs <= 60) return "green";
  if (abs <= 180) return "orange";
  return "red";
}

function formatDelay(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const abs = Math.abs(Math.round(seconds));
  const sign = seconds >= 0 ? "+" : "-";
  if (abs < 60) return `${sign}${abs}s`;
  const min = Math.floor(abs / 60);
  const sec = abs % 60;
  return sec > 0 ? `${sign}${min}m${sec.toString().padStart(2, "0")}` : `${sign}${min}m`;
}

function routeBadge(shortName, color) {
  const bg = color && color !== "" ? `#${color}` : "#666";
  // Determine text color based on background brightness
  const r = parseInt(color?.slice(0, 2) || "66", 16);
  const g = parseInt(color?.slice(2, 4) || "66", 16);
  const b = parseInt(color?.slice(4, 6) || "66", 16);
  const textColor = (r * 0.299 + g * 0.587 + b * 0.114) > 150 ? "#000" : "#fff";
  return `<span class="route-badge" style="background:${bg};color:${textColor}">${shortName}</span>`;
}

function barChart(rows, labelKey, valueKey, maxValue, colorFn) {
  if (!rows.length) return `<div class="empty"><div class="empty-text">Pas assez de donn&eacute;es</div></div>`;
  const max = maxValue || Math.max(...rows.map((r) => Math.abs(r[valueKey])), 1);
  return `<div class="bar-chart">${rows
    .map((r) => {
      const val = r[valueKey];
      const pct = Math.min(100, (Math.abs(val) / max) * 100);
      const color = colorFn ? colorFn(val) : "var(--blue)";
      return `<div class="bar-row">
        <span class="bar-label">${r[labelKey]}</span>
        <div class="bar-track">
          <div class="bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <span class="bar-value" style="color:${color}">${formatDelay(val)}</span>
      </div>`;
    })
    .join("")}</div>`;
}

function delayColorCSS(seconds) {
  const c = delayColor(seconds);
  return c === "green" ? "var(--green)" : c === "orange" ? "var(--orange)" : c === "red" ? "var(--red)" : "var(--blue)";
}

// ── Trips (localStorage) ─────────────────────────────────────

function getTrips() {
  try { return JSON.parse(localStorage.getItem("keleur_trips") || "[]"); }
  catch { return []; }
}
function saveTrips(trips) { localStorage.setItem("keleur_trips", JSON.stringify(trips)); }

// ── View: Overview ────────────────────────────────────────────

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
      <h2 class="section-title">Vue d'ensemble</h2>
      <div class="card-grid">
        <div class="stat-card">
          <div class="value blue">${overview.total_observations.toLocaleString("fr")}</div>
          <div class="label">Observations</div>
        </div>
        <div class="stat-card">
          <div class="value blue">${overview.routes_count}</div>
          <div class="label">Lignes suivies</div>
        </div>
        <div class="stat-card">
          <div class="value ${delayColor(overview.avg_delay_seconds)}">${formatDelay(Math.round(overview.avg_delay_seconds))}</div>
          <div class="label">Retard moyen</div>
        </div>
        <div class="stat-card">
          <div class="value ${overview.on_time_percent >= 70 ? "green" : overview.on_time_percent >= 50 ? "orange" : "red"}">${overview.on_time_percent?.toFixed(0) ?? "-"}%</div>
          <div class="label">&Agrave; l'heure (&plusmn;1min)</div>
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
                  <div class="route-meta">${r.total_observations} obs &middot; ${r.stops_observed} arr&ecirc;ts</div>
                </div>
              </a>
            `).join("")}
          </ul>
        `).join("")}
    `;
  } catch (err) {
    app().innerHTML = `<div class="empty"><div class="empty-icon">&#x26a0;&#xfe0f;</div><div class="empty-text">Erreur de chargement: ${err.message}</div></div>`;
  }
}

// ── View: Route detail ────────────────────────────────────────

async function viewRoute(routeId) {
  app().innerHTML = loading();

  try {
    const [routes, stops0, stops1] = await Promise.all([
      api("/routes"),
      api(`/routes/${encodeURIComponent(routeId)}/stops?direction_id=0`),
      api(`/routes/${encodeURIComponent(routeId)}/stops?direction_id=1`),
    ]);

    const routeInfo = routes.find((r) => r.route_id === routeId) || {};
    const allStops = { 0: stops0, 1: stops1 };

    app().innerHTML = `
      <a href="#/" class="back-link">&larr; Retour</a>
      <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:1.25rem">
        ${routeBadge(routeInfo.short_name || routeId, routeInfo.color)}
        <div>
          <div style="font-weight:700;font-size:1.1rem">${routeInfo.long_name || routeId}</div>
          <div style="font-size:0.85rem;color:var(--text-muted)">${routeInfo.total_observations || 0} observations</div>
        </div>
      </div>

      <div class="select-group">
        <select id="sel-dir">
          <option value="0">Direction A</option>
          <option value="1">Direction B</option>
        </select>
        <select id="sel-stop">
          ${stops0.map((s) => `<option value="${s.stop_id}">${s.stop_name}</option>`).join("")}
        </select>
        <button class="btn btn-outline btn-sm" id="btn-save-trip">Sauvegarder</button>
      </div>

      <div id="route-stats">${loading()}</div>
    `;

    const selDir = $("#sel-dir");
    const selStop = $("#sel-stop");

    function updateStopOptions() {
      const dir = selDir.value;
      const stops = allStops[dir] || [];
      selStop.innerHTML = stops.map((s) => `<option value="${s.stop_id}">${s.stop_name}</option>`).join("");
      if (!stops.length) selStop.innerHTML = `<option>Aucun arr&ecirc;t</option>`;
    }

    async function loadStats() {
      const dir = selDir.value;
      const stopId = selStop.value;
      if (!stopId) return;

      $("#route-stats").innerHTML = loading();

      try {
        const [stats, byDay, byHour] = await Promise.all([
          api(`/stats?route_id=${encodeURIComponent(routeId)}&stop_id=${encodeURIComponent(stopId)}&direction_id=${dir}`),
          api(`/stats/by-day?route_id=${encodeURIComponent(routeId)}&stop_id=${encodeURIComponent(stopId)}&direction_id=${dir}`),
          api(`/stats/by-hour?route_id=${encodeURIComponent(routeId)}&stop_id=${encodeURIComponent(stopId)}&direction_id=${dir}`),
        ]);

        if (stats.total_observations === 0) {
          $("#route-stats").innerHTML = `<div class="empty"><div class="empty-text">Pas encore de donn&eacute;es pour cet arr&ecirc;t</div></div>`;
          return;
        }

        $("#route-stats").innerHTML = `
          <div class="card-grid">
            <div class="stat-card">
              <div class="value ${delayColor(stats.avg_delay_seconds)}">${formatDelay(Math.round(stats.avg_delay_seconds))}</div>
              <div class="label">Retard moyen</div>
            </div>
            <div class="stat-card">
              <div class="value ${delayColor(stats.median_delay_seconds)}">${formatDelay(Math.round(stats.median_delay_seconds))}</div>
              <div class="label">Retard m&eacute;dian</div>
            </div>
            <div class="stat-card">
              <div class="value ${stats.on_time_percent >= 70 ? "green" : stats.on_time_percent >= 50 ? "orange" : "red"}">${stats.on_time_percent.toFixed(0)}%</div>
              <div class="label">&Agrave; l'heure</div>
            </div>
            <div class="stat-card">
              <div class="value ${stats.late_5min_percent <= 10 ? "green" : stats.late_5min_percent <= 25 ? "orange" : "red"}">${stats.late_5min_percent.toFixed(0)}%</div>
              <div class="label">&gt; 5min retard</div>
            </div>
          </div>
          <div class="stat-card" style="margin-bottom:1rem;text-align:center">
            <div style="font-size:0.8rem;color:var(--text-muted)">${stats.total_observations} observations depuis le ${new Date(stats.first_observation).toLocaleDateString("fr")}</div>
          </div>

          <h2 class="section-title">Par jour de la semaine</h2>
          <div class="card">
            ${barChart(
              byDay,
              "day_name",
              "avg_delay_seconds",
              null,
              (v) => delayColorCSS(v)
            )}
          </div>

          <h2 class="section-title">Par heure</h2>
          <div class="card">
            ${barChart(
              byHour.map((h) => ({ ...h, label: `${h.hour}h` })),
              "label",
              "avg_delay_seconds",
              null,
              (v) => delayColorCSS(v)
            )}
          </div>
        `;
      } catch (err) {
        $("#route-stats").innerHTML = `<div class="empty">Erreur: ${err.message}</div>`;
      }
    }

    selDir.addEventListener("change", () => { updateStopOptions(); loadStats(); });
    selStop.addEventListener("change", loadStats);

    // Save trip button
    $("#btn-save-trip").addEventListener("click", () => {
      const trips = getTrips();
      const trip = {
        route_id: routeId,
        short_name: routeInfo.short_name,
        long_name: routeInfo.long_name,
        color: routeInfo.color,
        stop_id: selStop.value,
        stop_name: selStop.options[selStop.selectedIndex]?.text,
        direction_id: parseInt(selDir.value),
      };
      // Avoid duplicates
      const exists = trips.some(
        (t) => t.route_id === trip.route_id && t.stop_id === trip.stop_id && t.direction_id === trip.direction_id
      );
      if (!exists) {
        trips.push(trip);
        saveTrips(trips);
      }
      $("#btn-save-trip").textContent = "Sauvegard\u00e9 !";
      setTimeout(() => { $("#btn-save-trip").textContent = "Sauvegarder"; }, 1500);
    });

    loadStats();
  } catch (err) {
    app().innerHTML = `<div class="empty"><div class="empty-icon">&#x26a0;&#xfe0f;</div><div class="empty-text">Erreur: ${err.message}</div></div>`;
  }
}

// ── View: My trips ────────────────────────────────────────────

async function viewTrips() {
  const trips = getTrips();

  if (!trips.length) {
    app().innerHTML = `
      <h2 class="section-title">Mes trajets</h2>
      <div class="empty">
        <div class="empty-icon">&#x1f68f;</div>
        <div class="empty-text">
          Aucun trajet sauvegard&eacute;.<br>
          Va sur une ligne et clique &laquo; Sauvegarder &raquo;.
        </div>
      </div>
    `;
    return;
  }

  // Load stats for all trips in parallel
  const statsPromises = trips.map((t) =>
    api(`/stats?route_id=${encodeURIComponent(t.route_id)}&stop_id=${encodeURIComponent(t.stop_id)}&direction_id=${t.direction_id}&days=30`)
      .catch(() => null)
  );
  const allStats = await Promise.all(statsPromises);

  app().innerHTML = `
    <h2 class="section-title">Mes trajets</h2>
    ${trips
      .map((t, i) => {
        const s = allStats[i];
        const delayStr = s && s.total_observations > 0 ? formatDelay(Math.round(s.avg_delay_seconds)) : "-";
        const onTime = s && s.total_observations > 0 ? `${s.on_time_percent.toFixed(0)}%` : "-";
        return `
          <div class="trip-card">
            ${routeBadge(t.short_name, t.color)}
            <div class="trip-info">
              <div style="font-weight:600">${t.stop_name}</div>
              <div style="font-size:0.8rem;color:var(--text-muted)">
                Moy. <span style="color:${delayColorCSS(s?.avg_delay_seconds)}">${delayStr}</span>
                &middot; &Agrave; l'heure ${onTime}
              </div>
            </div>
            <div class="trip-actions">
              <a href="#/route/${encodeURIComponent(t.route_id)}" class="btn btn-sm btn-outline">Voir</a>
              <button class="btn btn-sm btn-danger" onclick="removeTrip(${i})">&#x2715;</button>
            </div>
          </div>
        `;
      })
      .join("")}
  `;
}

// Global function for trip removal
window.removeTrip = function (idx) {
  const trips = getTrips();
  trips.splice(idx, 1);
  saveTrips(trips);
  viewTrips();
};

// ── Service worker registration ───────────────────────────────

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// ── Init ──────────────────────────────────────────────────────

route();
