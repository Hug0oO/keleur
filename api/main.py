from contextlib import asynccontextmanager
from pathlib import Path
import threading

import duckdb
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from collector.config import DB_PATH
from . import queries
from .queries import FilterParams

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

_conn: duckdb.DuckDBPyConnection | None = None


def get_conn() -> duckdb.DuckDBPyConnection:
    """Return a thread-local cursor so API and collector don't conflict."""
    return _conn.cursor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn

    # Single shared connection for both collector and API
    from collector import database, config
    _conn = database.get_connection()

    # Deduplicate any existing duplicate observations
    database.deduplicate_observations(_conn)

    # Start collector in background thread
    from collector.main import Collector
    collector = Collector(conn=_conn)
    collector_thread = threading.Thread(target=collector.run, daemon=True, name="collector")
    collector_thread.start()

    yield

    collector.stop()
    _conn.close()


app = FastAPI(title="Keleur API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Filter helper ─────────────────────────────────────────────────────


def _parse_filters(
    route_id: str,
    stop_id: str | None = None,
    headsign: str | None = None,
    days: int = 30,
    time_from: str | None = None,
    time_to: str | None = None,
    days_of_week: str | None = None,  # comma-separated "1,2,3,4,5"
    holidays: str = "all",
) -> FilterParams:
    dow = [int(x) for x in days_of_week.split(",")] if days_of_week else None
    return FilterParams(
        route_id=route_id,
        stop_id=stop_id,
        headsign=headsign,
        days=days,
        time_from=time_from,
        time_to=time_to,
        days_of_week=dow,
        holidays=holidays,
    )


# ── Routes list ────────────────────────────────────────────────────────

@app.get("/api/routes")
def list_routes():
    """All routes that have at least one observation."""
    rows = get_conn().execute("""
        SELECT r.route_id, r.short_name, r.long_name, r.route_type, r.color,
               count(DISTINCT o.stop_id) as stops_observed,
               count(*) as total_observations
        FROM routes r
        INNER JOIN delay_observations o ON r.route_id = o.route_id
        GROUP BY r.route_id, r.short_name, r.long_name, r.route_type, r.color
        ORDER BY r.route_type, r.short_name
    """).fetchall()
    return [
        {
            "route_id": r[0], "short_name": r[1], "long_name": r[2],
            "route_type": r[3], "color": r[4],
            "stops_observed": r[5], "total_observations": r[6],
        }
        for r in rows
    ]


# ── Directions for a route ────────────────────────────────────────────

@app.get("/api/routes/{route_id}/directions")
def route_directions(route_id: str):
    """Available directions (headsigns) for a route, based on observed data."""
    rows = get_conn().execute("""
        SELECT DISTINCT t.trip_headsign, t.direction_id
        FROM delay_observations o
        JOIN trips t ON o.trip_id = t.trip_id
        WHERE o.route_id = ?
        ORDER BY t.trip_headsign
    """, [route_id]).fetchall()
    return [
        {"headsign": r[0], "direction_id": r[1]}
        for r in rows
    ]


# ── Stops for a route ─────────────────────────────────────────────────

@app.get("/api/routes/{route_id}/stops")
def route_stops(
    route_id: str,
    headsign: str = Query(default=None),
):
    """Stops served on a route, filtered by headsign."""
    if headsign:
        rows = get_conn().execute("""
            WITH matching_trips AS (
                SELECT trip_id FROM trips
                WHERE route_id = ? AND trip_headsign = ?
            ),
            stop_order AS (
                SELECT st.stop_id, avg(st.stop_sequence) as avg_seq
                FROM stop_times st
                WHERE st.trip_id IN (SELECT trip_id FROM matching_trips)
                GROUP BY st.stop_id
            )
            SELECT min(o.stop_id) as stop_id, s.stop_name,
                   avg(s.lat) as lat, avg(s.lon) as lon,
                   min(so.avg_seq) as seq
            FROM delay_observations o
            JOIN trips t ON o.trip_id = t.trip_id
            LEFT JOIN stops s ON o.stop_id = s.stop_id
            INNER JOIN stop_order so ON o.stop_id = so.stop_id
            WHERE o.route_id = ? AND t.trip_headsign = ?
            GROUP BY s.stop_name
            ORDER BY seq, s.stop_name
        """, [route_id, headsign, route_id, headsign]).fetchall()
    else:
        rows = get_conn().execute("""
            WITH stop_order AS (
                SELECT st.stop_id, avg(st.stop_sequence) as avg_seq
                FROM stop_times st
                JOIN trips t ON st.trip_id = t.trip_id
                WHERE t.route_id = ?
                GROUP BY st.stop_id
            )
            SELECT min(o.stop_id) as stop_id, s.stop_name,
                   avg(s.lat) as lat, avg(s.lon) as lon,
                   min(so.avg_seq) as seq
            FROM delay_observations o
            LEFT JOIN stops s ON o.stop_id = s.stop_id
            INNER JOIN stop_order so ON o.stop_id = so.stop_id
            WHERE o.route_id = ?
            GROUP BY s.stop_name
            ORDER BY seq, s.stop_name
        """, [route_id, route_id]).fetchall()
    return [
        {"stop_id": r[0], "stop_name": r[1], "lat": r[2], "lon": r[3]}
        for r in rows
    ]


# ── Stats for a (route, stop) ───────────────────────────────────────

@app.get("/api/stats")
def delay_stats(
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    time_from: str = Query(default=None, description="HH:MM"),
    time_to: str = Query(default=None, description="HH:MM"),
    days: int = Query(default=30),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(route_id, stop_id=stop_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_delay_stats(get_conn(), f)


@app.get("/api/stats/by-day")
def stats_by_day(
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days: int = Query(default=30),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(route_id, stop_id=stop_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_stats_by_day_of_week(get_conn(), f)


@app.get("/api/stats/by-hour")
def stats_by_hour(
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days: int = Query(default=30),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(route_id, stop_id=stop_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_stats_by_hour(get_conn(), f)


@app.get("/api/stats/worst-departures")
def worst_departures(
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    days: int = Query(default=30),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(route_id, stop_id=stop_id, headsign=headsign, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_worst_departures(get_conn(), f)


@app.get("/api/stats/departures")
def departure_times(
    route_id: str,
    stop_id: str = Query(default=None),
    headsign: str = Query(default=None),
    days: int = Query(default=30),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(route_id, stop_id=stop_id, headsign=headsign, days=days, days_of_week=days_of_week, holidays=holidays)
    return queries.get_departure_times(get_conn(), f)


# ── Route-level stats (all stops) ─────────────────────────────────────

@app.get("/api/routes/{route_id}/stats")
def route_global_stats(
    route_id: str,
    days: int = Query(default=30),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(route_id, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_route_stats(get_conn(), f)

@app.get("/api/routes/{route_id}/stats/by-day")
def route_stats_by_day(
    route_id: str,
    days: int = Query(default=30),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(route_id, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_route_stats_by_day(get_conn(), f)

@app.get("/api/routes/{route_id}/stats/by-hour")
def route_stats_by_hour(
    route_id: str,
    days: int = Query(default=30),
    time_from: str = Query(default=None),
    time_to: str = Query(default=None),
    days_of_week: str = Query(default=None),
    holidays: str = Query(default="all"),
):
    f = _parse_filters(route_id, days=days, time_from=time_from, time_to=time_to, days_of_week=days_of_week, holidays=holidays)
    return queries.get_route_stats_by_hour(get_conn(), f)


# ── Rankings ──────────────────────────────────────────────────

@app.get("/api/rankings/stops")
def rankings_stops():
    """Top 3 best and worst stops (last 30 days, min 20 observations)."""
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
        JOIN stops s ON o.stop_id = s.stop_id
        JOIN trips t ON o.trip_id = t.trip_id
        JOIN routes r ON o.route_id = r.route_id
        WHERE o.observed_at >= current_date - INTERVAL '30 days'
          AND o.stop_sequence > 1
        GROUP BY s.stop_name, r.route_id, r.short_name, r.color, t.trip_headsign
        HAVING count(*) >= 20 AND stddev(o.delay_seconds) > 0
    """).fetchall()

    items = [
        {
            "stop_name": r[0], "short_name": r[1], "color": r[2],
            "headsign": r[3], "avg_delay_seconds": r[4],
            "on_time_percent": r[5], "total_passages": r[6],
            "route_id": r[7], "avg_late_delay_seconds": r[8],
        }
        for r in rows
    ]

    worst = sorted(items, key=lambda x: x["avg_delay_seconds"] or 0, reverse=True)[:3]
    best = sorted(items, key=lambda x: x["on_time_percent"], reverse=True)[:3]
    return {"worst": worst, "best": best}


@app.get("/api/rankings/routes")
def rankings_routes():
    """Top 3 best and worst routes (last 30 days, min 50 observations)."""
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
        JOIN routes r ON o.route_id = r.route_id
        WHERE o.observed_at >= current_date - INTERVAL '30 days'
        GROUP BY r.route_id, r.short_name, r.long_name, r.color
        HAVING count(*) >= 50
    """).fetchall()

    items = [
        {
            "route_id": r[0], "short_name": r[1], "long_name": r[2],
            "color": r[3], "avg_delay_seconds": r[4],
            "on_time_percent": r[5], "total_passages": r[6],
            "avg_late_delay_seconds": r[7],
        }
        for r in rows
    ]

    worst = sorted(items, key=lambda x: x["avg_delay_seconds"] or 0, reverse=True)[:3]
    best = sorted(items, key=lambda x: x["on_time_percent"], reverse=True)[:3]
    return {"worst": worst, "best": best}


# ── Stop search ──────────────────────────────────────────────────────

@app.get("/api/search/stops")
def search_stops(q: str = Query(description="Search query")):
    """Search stops by name, returning matching stops with their routes."""
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
        JOIN stops s ON o.stop_id = s.stop_id
        JOIN routes r ON o.route_id = r.route_id
        JOIN trips t ON o.trip_id = t.trip_id
        WHERE lower(s.stop_name) LIKE '%' || lower(?) || '%'
        GROUP BY s.stop_name, r.route_id, r.short_name, r.long_name, r.color, t.trip_headsign
        ORDER BY s.stop_name, r.short_name
        LIMIT 50
    """, [q]).fetchall()
    return [
        {
            "stop_name": r[0], "route_id": r[1], "short_name": r[2],
            "long_name": r[3], "color": r[4], "headsign": r[5],
        }
        for r in rows
    ]


# ── Global overview ───────────────────────────────────────────────────

@app.get("/api/overview")
def overview():
    """Global stats: data range, total observations, routes covered."""
    row = get_conn().execute("""
        SELECT
            count(*) as total_obs,
            min(observed_at) as first_obs,
            max(observed_at) as last_obs,
            count(DISTINCT route_id) as routes,
            count(DISTINCT stop_id) as stops,
            round(avg(delay_seconds), 1) as avg_delay,
            count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*) as on_time_pct
        FROM delay_observations
    """).fetchone()
    return {
        "total_observations": row[0],
        "first_observation": str(row[1]) if row[1] else None,
        "last_observation": str(row[2]) if row[2] else None,
        "routes_count": row[3],
        "stops_count": row[4],
        "avg_delay_seconds": row[5],
        "on_time_percent": round(row[6], 1) if row[6] else None,
    }


# ── Frontend static files ─────────────────────────────────────────────

@app.get("/")
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


# Mount static files AFTER API routes so /api/* takes priority
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
