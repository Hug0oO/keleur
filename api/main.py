from contextlib import asynccontextmanager
from pathlib import Path
import threading

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from collector import networks
from collector.config import DB_PATH
from . import queries
from .queries import FilterParams

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

_conn: duckdb.DuckDBPyConnection | None = None


def get_conn() -> duckdb.DuckDBPyConnection:
    """Return a thread-local cursor so API and collector don't conflict."""
    return _conn.cursor()


def _validate_network(network_id: str) -> None:
    if networks.get(network_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown network: {network_id}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn

    # Single shared connection for both collector and API
    from collector import database
    _conn = database.get_connection()

    # Deduplicate any existing duplicate observations
    database.deduplicate_observations(_conn)

    # Start multi-network collector in background thread
    from collector.main import MultiCollector
    collector = MultiCollector(conn=_conn)
    collector_thread = threading.Thread(
        target=collector.run, daemon=True, name="multicollector"
    )
    collector_thread.start()

    yield

    collector.stop()
    _conn.close()


app = FastAPI(title="Keleur API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Filter helper ─────────────────────────────────────────────────────


def _parse_filters(
    network_id: str,
    route_id: str,
    stop_id: str | None = None,
    headsign: str | None = None,
    days: int = 30,
    time_from: str | None = None,
    time_to: str | None = None,
    days_of_week: str | None = None,  # comma-separated "1,2,3,4,5"
    holidays: str = "all",
) -> FilterParams:
    _validate_network(network_id)
    dow = [int(x) for x in days_of_week.split(",")] if days_of_week else None
    return FilterParams(
        network_id=network_id,
        route_id=route_id,
        stop_id=stop_id,
        headsign=headsign,
        days=days,
        time_from=time_from,
        time_to=time_to,
        days_of_week=dow,
        holidays=holidays,
    )


# ── Networks registry ─────────────────────────────────────────────────

@app.get("/api/networks")
def list_networks():
    """List all networks the app knows about (enabled and disabled)."""
    return [
        {
            "id": n.id,
            "name": n.name,
            "operator": n.operator,
            "city": n.city,
            "region": n.region,
            "color": n.color,
            "enabled": n.enabled,
        }
        for n in networks.all_networks()
    ]


# ── Health check ──────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    """Per-network health: row counts, freshness, last observation timestamp."""
    from collector import database

    out = []
    for n in networks.all_networks():
        if not n.enabled:
            out.append({"network_id": n.id, "enabled": False, "status": "disabled"})
            continue
        try:
            last = database.last_observation_at(get_conn(), n.id)
            obs_count = get_conn().execute(
                "SELECT count(*) FROM delay_observations WHERE network_id = ?",
                [n.id],
            ).fetchone()[0]
            stops_loaded = get_conn().execute(
                "SELECT count(*) FROM stops WHERE network_id = ?", [n.id]
            ).fetchone()[0]
            # Stale if no obs in last 10 min
            from datetime import datetime, timedelta
            status = "ok"
            if not last:
                status = "no_data"
            else:
                last_dt = datetime.fromisoformat(last)
                if datetime.now() - last_dt > timedelta(minutes=10):
                    status = "stale"
            out.append({
                "network_id": n.id,
                "name": n.name,
                "enabled": True,
                "status": status,
                "last_observation": last,
                "observations": obs_count,
                "stops_loaded": stops_loaded,
            })
        except Exception as exc:
            out.append({
                "network_id": n.id,
                "enabled": True,
                "status": "error",
                "error": str(exc),
            })
    return {"networks": out}


# ── Routes list ────────────────────────────────────────────────────────

@app.get("/api/networks/{network_id}/routes")
def list_routes(network_id: str):
    """All routes for a network that have at least one observation."""
    _validate_network(network_id)
    rows = get_conn().execute("""
        SELECT r.route_id, r.short_name, r.long_name, r.route_type, r.color,
               count(DISTINCT o.stop_id) as stops_observed,
               count(*) as total_observations
        FROM routes r
        INNER JOIN delay_observations o
          ON r.route_id = o.route_id AND r.network_id = o.network_id
        WHERE r.network_id = ?
        GROUP BY r.route_id, r.short_name, r.long_name, r.route_type, r.color
        ORDER BY r.route_type, r.short_name
    """, [network_id]).fetchall()
    return [
        {
            "route_id": r[0], "short_name": r[1], "long_name": r[2],
            "route_type": r[3], "color": r[4],
            "stops_observed": r[5], "total_observations": r[6],
        }
        for r in rows
    ]


# ── Directions for a route ────────────────────────────────────────────

@app.get("/api/networks/{network_id}/routes/{route_id}/directions")
def route_directions(network_id: str, route_id: str):
    """Available directions (headsigns) for a route, based on observed data."""
    _validate_network(network_id)
    rows = get_conn().execute("""
        SELECT DISTINCT t.trip_headsign, t.direction_id
        FROM delay_observations o
        JOIN trips t ON o.trip_id = t.trip_id AND o.network_id = t.network_id
        WHERE o.network_id = ? AND o.route_id = ?
        ORDER BY t.trip_headsign
    """, [network_id, route_id]).fetchall()
    return [
        {"headsign": r[0], "direction_id": r[1]}
        for r in rows
    ]


# ── Stops for a route ─────────────────────────────────────────────────

@app.get("/api/networks/{network_id}/routes/{route_id}/stops")
def route_stops(
    network_id: str,
    route_id: str,
    headsign: str = Query(default=None),
):
    """Stops served on a route, filtered by headsign."""
    _validate_network(network_id)
    if headsign:
        rows = get_conn().execute("""
            WITH matching_trips AS (
                SELECT trip_id FROM trips
                WHERE network_id = ? AND route_id = ? AND trip_headsign = ?
            ),
            stop_order AS (
                SELECT st.stop_id, avg(st.stop_sequence) as avg_seq
                FROM stop_times st
                WHERE st.network_id = ?
                  AND st.trip_id IN (SELECT trip_id FROM matching_trips)
                GROUP BY st.stop_id
            )
            SELECT min(o.stop_id) as stop_id, s.stop_name,
                   avg(s.lat) as lat, avg(s.lon) as lon,
                   min(so.avg_seq) as seq
            FROM delay_observations o
            JOIN trips t ON o.trip_id = t.trip_id AND o.network_id = t.network_id
            LEFT JOIN stops s ON o.stop_id = s.stop_id AND o.network_id = s.network_id
            INNER JOIN stop_order so ON o.stop_id = so.stop_id
            WHERE o.network_id = ? AND o.route_id = ? AND t.trip_headsign = ?
            GROUP BY s.stop_name
            ORDER BY seq, s.stop_name
        """, [network_id, route_id, headsign, network_id, network_id, route_id, headsign]).fetchall()
    else:
        rows = get_conn().execute("""
            WITH stop_order AS (
                SELECT st.stop_id, avg(st.stop_sequence) as avg_seq
                FROM stop_times st
                JOIN trips t ON st.trip_id = t.trip_id AND st.network_id = t.network_id
                WHERE st.network_id = ? AND t.route_id = ?
                GROUP BY st.stop_id
            )
            SELECT min(o.stop_id) as stop_id, s.stop_name,
                   avg(s.lat) as lat, avg(s.lon) as lon,
                   min(so.avg_seq) as seq
            FROM delay_observations o
            LEFT JOIN stops s ON o.stop_id = s.stop_id AND o.network_id = s.network_id
            INNER JOIN stop_order so ON o.stop_id = so.stop_id
            WHERE o.network_id = ? AND o.route_id = ?
            GROUP BY s.stop_name
            ORDER BY seq, s.stop_name
        """, [network_id, route_id, network_id, route_id]).fetchall()
    return [
        {"stop_id": r[0], "stop_name": r[1], "lat": r[2], "lon": r[3]}
        for r in rows
    ]


# ── Stats for a (route, stop) ───────────────────────────────────────

@app.get("/api/networks/{network_id}/stats")
def delay_stats(
    network_id: str,
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    time_from: str = Query(default=None, description="HH:MM"),
    time_to: str = Query(default=None, description="HH:MM"),
    days: int = Query(default=30),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, stop_id=stop_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_delay_stats(get_conn(), f)


@app.get("/api/networks/{network_id}/stats/by-day")
def stats_by_day(
    network_id: str,
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days: int = Query(default=30),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, stop_id=stop_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_stats_by_day_of_week(get_conn(), f)


@app.get("/api/networks/{network_id}/stats/by-hour")
def stats_by_hour(
    network_id: str,
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days: int = Query(default=30),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, stop_id=stop_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_stats_by_hour(get_conn(), f)


@app.get("/api/networks/{network_id}/stats/worst-departures")
def worst_departures(
    network_id: str,
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    days: int = Query(default=30),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, stop_id=stop_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_worst_departures(get_conn(), f)


@app.get("/api/networks/{network_id}/stats/departures")
def departure_times(
    network_id: str,
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    days: int = Query(default=30),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, stop_id=stop_id, headsign=headsign, days=days, days_of_week=days_of_week, holidays=holidays)
    return queries.get_departure_times(get_conn(), f)


@app.get("/api/networks/{network_id}/stats/trend")
def weekly_trend(
    network_id: str,
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    days: int = Query(default=90),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, stop_id=stop_id, headsign=headsign, days=days, days_of_week=days_of_week, holidays=holidays)
    return queries.get_weekly_trend(get_conn(), f)


# ── Route-level stats (all stops) ─────────────────────────────────────

@app.get("/api/networks/{network_id}/routes/{route_id}/stats")
def route_global_stats(
    network_id: str,
    route_id: str,
    headsign: str = Query(default=None),
    days: int = Query(default=30),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_route_stats(get_conn(), f)


@app.get("/api/networks/{network_id}/routes/{route_id}/stats/by-day")
def route_stats_by_day(
    network_id: str,
    route_id: str,
    headsign: str = Query(default=None),
    days: int = Query(default=30),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_route_stats_by_day(get_conn(), f)


@app.get("/api/networks/{network_id}/routes/{route_id}/stats/by-hour")
def route_stats_by_hour(
    network_id: str,
    route_id: str,
    headsign: str = Query(default=None),
    days: int = Query(default=30),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_route_stats_by_hour(get_conn(), f)


@app.get("/api/networks/{network_id}/routes/{route_id}/stats/trend")
def route_weekly_trend(
    network_id: str,
    route_id: str,
    headsign: str = Query(default=None),
    days: int = Query(default=90),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(network_id, route_id, headsign=headsign, days=days, days_of_week=days_of_week, holidays=holidays)
    return queries.get_weekly_trend(get_conn(), f)


# ── Recommendations: alternative departure times ─────────────────────

@app.get("/api/networks/{network_id}/recommendations")
def recommendations(
    network_id: str,
    route_id: str,
    stop_id: str,
    headsign: str = Query(default=None),
    departure_time: str = Query(description="HH:MM"),
    window_minutes: int = Query(default=20),
    days: int = Query(default=30),
):
    """Suggest the most reliable departures within ±window_minutes of a given time.

    Useful for "your usual 8:15 is always 4 min late — try the 8:08, it's on time".
    Returns up to 3 alternatives sorted by punctuality.
    """
    _validate_network(network_id)

    headsign_filter = ""
    params: list = [network_id, route_id, network_id, stop_id]
    if headsign:
        headsign_filter = (
            "AND trip_id IN (SELECT t.trip_id FROM trips t "
            "WHERE t.network_id = ? AND t.trip_headsign = ?)"
        )
        params.extend([network_id, headsign])
    params.extend([days, departure_time, window_minutes])

    rows = get_conn().execute(f"""
        WITH ref AS (
            SELECT CAST(? AS TIME) as t
        )
        SELECT
            strftime(scheduled_dep, '%H:%M') as dep,
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay,
            round(count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*), 1) as on_time_pct,
            round(avg(CASE WHEN delay_seconds >= 60 THEN delay_seconds END), 0) as avg_late_delay,
            abs(date_diff('minute', CAST(? AS TIME), CAST(scheduled_dep AS TIME))) as offset_min
        FROM delay_observations
        WHERE network_id = ? AND route_id = ?
          AND stop_id IN (SELECT s2.stop_id FROM stops s2
              WHERE s2.network_id = ?
              AND s2.stop_name = (SELECT s1.stop_name FROM stops s1
                  WHERE s1.network_id = ? AND s1.stop_id = ?))
          {headsign_filter}
          AND observed_at >= current_date - INTERVAL (?) DAY
          AND abs(date_diff('minute', CAST(? AS TIME), CAST(scheduled_dep AS TIME))) <= ?
        GROUP BY strftime(scheduled_dep, '%H:%M')
        HAVING count(*) >= 5
        ORDER BY on_time_pct DESC, offset_min ASC
        LIMIT 5
    """, [departure_time, departure_time] + params).fetchall()

    return [
        {
            "departure_time": r[0],
            "total_observations": r[1],
            "avg_delay_seconds": r[2],
            "on_time_percent": r[3],
            "avg_late_delay_seconds": r[4],
            "offset_minutes": r[5],
        }
        for r in rows
    ]


# ── Anomalies: today vs baseline ──────────────────────────────────────

@app.get("/api/networks/{network_id}/anomalies")
def anomalies(network_id: str, days: int = Query(default=30)):
    """Routes whose punctuality today is significantly worse than their N-day baseline."""
    _validate_network(network_id)

    rows = get_conn().execute("""
        WITH baseline AS (
            SELECT route_id,
                   avg(delay_seconds) as baseline_avg,
                   count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*) as baseline_pct,
                   count(*) as baseline_total
            FROM delay_observations
            WHERE network_id = ?
              AND observed_at >= current_date - INTERVAL (?) DAY
              AND observed_at < current_date
            GROUP BY route_id
            HAVING count(*) >= 100
        ),
        today AS (
            SELECT route_id,
                   avg(delay_seconds) as today_avg,
                   count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*) as today_pct,
                   count(*) as today_total
            FROM delay_observations
            WHERE network_id = ?
              AND observed_at >= current_date
            GROUP BY route_id
            HAVING count(*) >= 10
        )
        SELECT
            r.route_id, r.short_name, r.long_name, r.color, r.route_type,
            round(b.baseline_avg, 1) as baseline_avg,
            round(b.baseline_pct, 1) as baseline_pct,
            round(t.today_avg, 1) as today_avg,
            round(t.today_pct, 1) as today_pct,
            t.today_total
        FROM today t
        JOIN baseline b USING (route_id)
        JOIN routes r ON r.route_id = t.route_id AND r.network_id = ?
        WHERE t.today_pct < b.baseline_pct - 10
        ORDER BY (b.baseline_pct - t.today_pct) DESC
        LIMIT 20
    """, [network_id, days, network_id, network_id]).fetchall()

    return [
        {
            "route_id": r[0], "short_name": r[1], "long_name": r[2],
            "color": r[3], "route_type": r[4],
            "baseline_avg_delay": r[5],
            "baseline_on_time_percent": r[6],
            "today_avg_delay": r[7],
            "today_on_time_percent": r[8],
            "today_observations": r[9],
            "punctuality_drop": round(r[6] - r[8], 1),
        }
        for r in rows
    ]


# ── Rankings ──────────────────────────────────────────────────

@app.get("/api/networks/{network_id}/rankings/stops")
def rankings_stops(network_id: str):
    """Top 10 best and worst stops (last 30 days, min 20 observations)."""
    _validate_network(network_id)
    rows = get_conn().execute("""
        SELECT
            s.stop_name,
            r.short_name,
            r.color,
            t.trip_headsign,
            round(avg(o.delay_seconds), 1) as avg_delay_seconds,
            round(count(CASE WHEN abs(o.delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*), 1) as on_time_percent,
            count(*) as total_passages,
            r.route_id,
            round(avg(CASE WHEN o.delay_seconds >= 60 THEN o.delay_seconds END), 0) as avg_late_delay
        FROM delay_observations o
        JOIN stops s ON o.stop_id = s.stop_id AND o.network_id = s.network_id
        JOIN trips t ON o.trip_id = t.trip_id AND o.network_id = t.network_id
        JOIN routes r ON o.route_id = r.route_id AND o.network_id = r.network_id
        WHERE o.network_id = ?
          AND o.observed_at >= current_date - INTERVAL '30 days'
          AND o.stop_sequence > 1
        GROUP BY s.stop_name, r.route_id, r.short_name, r.color, t.trip_headsign
        HAVING count(*) >= 20 AND stddev(o.delay_seconds) > 0
    """, [network_id]).fetchall()

    items = [
        {
            "stop_name": r[0], "short_name": r[1], "color": r[2],
            "headsign": r[3], "avg_delay_seconds": r[4],
            "on_time_percent": r[5], "total_passages": r[6],
            "route_id": r[7], "avg_late_delay_seconds": r[8],
        }
        for r in rows
    ]

    worst = sorted(items, key=lambda x: x["avg_delay_seconds"] or 0, reverse=True)[:10]
    best = sorted(items, key=lambda x: x["on_time_percent"], reverse=True)[:10]
    return {"worst": worst, "best": best}


@app.get("/api/networks/{network_id}/rankings/routes")
def rankings_routes(network_id: str):
    """Top 10 best and worst routes (last 30 days, min 50 observations)."""
    _validate_network(network_id)
    rows = get_conn().execute("""
        SELECT
            r.route_id,
            r.short_name,
            r.long_name,
            r.color,
            round(avg(o.delay_seconds), 1) as avg_delay_seconds,
            round(count(CASE WHEN abs(o.delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*), 1) as on_time_percent,
            count(*) as total_passages,
            round(avg(CASE WHEN o.delay_seconds >= 60 THEN o.delay_seconds END), 0) as avg_late_delay
        FROM delay_observations o
        JOIN routes r ON o.route_id = r.route_id AND o.network_id = r.network_id
        WHERE o.network_id = ?
          AND o.observed_at >= current_date - INTERVAL '30 days'
        GROUP BY r.route_id, r.short_name, r.long_name, r.color
        HAVING count(*) >= 50
    """, [network_id]).fetchall()

    items = [
        {
            "route_id": r[0], "short_name": r[1], "long_name": r[2],
            "color": r[3], "avg_delay_seconds": r[4],
            "on_time_percent": r[5], "total_passages": r[6],
            "avg_late_delay_seconds": r[7],
        }
        for r in rows
    ]

    worst = sorted(items, key=lambda x: x["avg_delay_seconds"] or 0, reverse=True)[:10]
    best = sorted(items, key=lambda x: x["on_time_percent"], reverse=True)[:10]
    return {"worst": worst, "best": best}


# ── Stop search ──────────────────────────────────────────────────────

@app.get("/api/networks/{network_id}/search/stops")
def search_stops(network_id: str, q: str = Query(description="Search query")):
    """Search stops by name within a network."""
    _validate_network(network_id)
    if len(q) < 2:
        return []
    rows = get_conn().execute("""
        SELECT DISTINCT
            s.stop_name,
            r.route_id,
            r.short_name,
            r.long_name,
            r.color,
            t.trip_headsign
        FROM delay_observations o
        JOIN stops s ON o.stop_id = s.stop_id AND o.network_id = s.network_id
        JOIN routes r ON o.route_id = r.route_id AND o.network_id = r.network_id
        JOIN trips t ON o.trip_id = t.trip_id AND o.network_id = t.network_id
        WHERE o.network_id = ?
          AND lower(s.stop_name) LIKE '%' || lower(?) || '%'
        GROUP BY s.stop_name, r.route_id, r.short_name, r.long_name, r.color, t.trip_headsign
        ORDER BY s.stop_name, r.short_name
        LIMIT 50
    """, [network_id, q]).fetchall()
    return [
        {
            "stop_name": r[0], "route_id": r[1], "short_name": r[2],
            "long_name": r[3], "color": r[4], "headsign": r[5],
        }
        for r in rows
    ]


# ── Network overview ──────────────────────────────────────────────────

@app.get("/api/networks/{network_id}/overview")
def overview(network_id: str):
    """Global stats for a network: data range, total observations, routes covered."""
    _validate_network(network_id)
    row = get_conn().execute("""
        SELECT
            count(*) as total_obs,
            min(observed_at) as first_obs,
            max(observed_at) as last_obs,
            count(DISTINCT route_id) as routes,
            count(DISTINCT stop_id) as stops,
            round(avg(delay_seconds), 1) as avg_delay,
            count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*) as on_time_pct,
            round(avg(CASE WHEN delay_seconds >= 60 THEN delay_seconds END), 0) as avg_late_delay,
            count(CASE WHEN delay_seconds > 300 THEN 1 END) * 100.0 / count(*) as late_5min_pct
        FROM delay_observations
        WHERE network_id = ?
    """, [network_id]).fetchone()

    if not row or row[0] == 0:
        return {
            "total_observations": 0,
            "first_observation": None,
            "last_observation": None,
            "routes_count": 0,
            "stops_count": 0,
            "avg_delay_seconds": None,
            "on_time_percent": None,
            "avg_late_delay_seconds": None,
            "late_5min_percent": None,
        }

    return {
        "total_observations": row[0],
        "first_observation": str(row[1]) if row[1] else None,
        "last_observation": str(row[2]) if row[2] else None,
        "routes_count": row[3],
        "stops_count": row[4],
        "avg_delay_seconds": row[5],
        "on_time_percent": round(row[6], 1) if row[6] else None,
        "avg_late_delay_seconds": row[7],
        "late_5min_percent": round(row[8], 1) if row[8] is not None else None,
    }


# ── Frontend static files ─────────────────────────────────────────────

@app.get("/")
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


# Mount static files AFTER API routes so /api/* takes priority
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
