"""DuckDB analytical queries for delay statistics."""

from dataclasses import dataclass, field

import duckdb

from .holidays import holiday_clause

# Day names for output
_DAY_NAMES = {
    0: "Dimanche",
    1: "Lundi",
    2: "Mardi",
    3: "Mercredi",
    4: "Jeudi",
    5: "Vendredi",
    6: "Samedi",
}


@dataclass
class FilterParams:
    route_id: str
    stop_id: str | None = None
    days: int = 30
    time_from: str | None = None
    time_to: str | None = None
    days_of_week: list[int] | None = None  # DuckDB dayofweek: 0=Sun, 1=Mon...6=Sat
    holidays: str = "all"  # "all", "only", "exclude"


def _build_filters(
    f: FilterParams,
    *,
    include_stop: bool = True,
    include_days_of_week: bool = True,
) -> tuple[str, list]:
    """Build a WHERE clause and params list from FilterParams.

    include_stop: if False, skip the stop_id filter (for route-level queries).
    include_days_of_week: if False, skip days_of_week filter (for by-day grouping).
    """
    clauses = ["route_id = ?"]
    params: list = [f.route_id]

    if include_stop and f.stop_id:
        clauses.append(
            "stop_id IN (SELECT s2.stop_id FROM stops s2 "
            "WHERE s2.stop_name = (SELECT s1.stop_name FROM stops s1 WHERE s1.stop_id = ?))"
        )
        params.append(f.stop_id)

    clauses.append("observed_at >= current_date - INTERVAL (?) DAY")
    params.append(f.days)

    if f.time_from:
        clauses.append("CAST(scheduled_dep AS TIME) >= ?")
        params.append(f.time_from + ":00")

    if f.time_to:
        clauses.append("CAST(scheduled_dep AS TIME) <= ?")
        params.append(f.time_to + ":00")

    if include_days_of_week and f.days_of_week:
        placeholders = ", ".join("?" for _ in f.days_of_week)
        clauses.append(f"dayofweek(observed_at) IN ({placeholders})")
        params.extend(f.days_of_week)

    where = " AND ".join(clauses)

    # Holiday clause is inlined SQL (no params)
    hol = holiday_clause(f.holidays)
    if hol:
        where += " " + hol

    return f"WHERE {where}", params


# ── Aggregated delay stats (route + stop) ────────────────────────────


def get_delay_stats(conn: duckdb.DuckDBPyConnection, f: FilterParams) -> dict:
    where, params = _build_filters(f)

    row = conn.execute(f"""
        SELECT
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay,
            round(median(delay_seconds), 1) as median_delay,
            min(delay_seconds) as min_delay,
            max(delay_seconds) as max_delay,
            round(stddev(delay_seconds), 1) as stddev_delay,
            count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*) as on_time_pct,
            count(CASE WHEN delay_seconds > 120 THEN 1 END) * 100.0 / count(*) as late_2min_pct,
            count(CASE WHEN delay_seconds > 300 THEN 1 END) * 100.0 / count(*) as late_5min_pct,
            min(observed_at) as first_obs,
            max(observed_at) as last_obs,
            round(avg(CASE WHEN delay_seconds >= 60 THEN delay_seconds END), 0) as avg_late_delay
        FROM delay_observations
        {where}
    """, params).fetchone()

    if row[0] == 0:
        return {"total_observations": 0, "message": "No data for this filter"}

    return {
        "total_observations": row[0],
        "avg_delay_seconds": row[1],
        "median_delay_seconds": row[2],
        "min_delay_seconds": row[3],
        "max_delay_seconds": row[4],
        "stddev_delay_seconds": row[5],
        "on_time_percent": round(row[6], 1),
        "late_2min_percent": round(row[7], 1),
        "late_5min_percent": round(row[8], 1),
        "first_observation": str(row[9]),
        "last_observation": str(row[10]),
        "avg_late_delay_seconds": row[11],
    }


# ── Stats by day of week ─────────────────────────────────────────────


def get_stats_by_day_of_week(
    conn: duckdb.DuckDBPyConnection, f: FilterParams
) -> list[dict]:
    # Exclude days_of_week filter — grouping by day makes it redundant
    where, params = _build_filters(f, include_days_of_week=False)

    rows = conn.execute(f"""
        SELECT
            dayofweek(observed_at) as dow,
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay,
            round(median(delay_seconds), 1) as median_delay,
            count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*) as on_time_pct,
            count(CASE WHEN delay_seconds > 300 THEN 1 END) * 100.0 / count(*) as late_5min_pct
        FROM delay_observations
        {where}
        GROUP BY dayofweek(observed_at)
        ORDER BY (dayofweek(observed_at) + 6) % 7
    """, params).fetchall()

    return [
        {
            "day_of_week": r[0],
            "day_name": _DAY_NAMES.get(r[0], str(r[0])),
            "total_observations": r[1],
            "avg_delay_seconds": r[2],
            "median_delay_seconds": r[3],
            "on_time_percent": round(r[4], 1),
            "late_5min_percent": round(r[5], 1),
        }
        for r in rows
    ]


# ── Stats by hour ────────────────────────────────────────────────────


def get_stats_by_hour(
    conn: duckdb.DuckDBPyConnection, f: FilterParams
) -> list[dict]:
    where, params = _build_filters(f)

    rows = conn.execute(f"""
        SELECT
            hour(scheduled_dep) as h,
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay,
            round(median(delay_seconds), 1) as median_delay,
            count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*) as on_time_pct
        FROM delay_observations
        {where}
        GROUP BY hour(scheduled_dep)
        ORDER BY hour(scheduled_dep)
    """, params).fetchall()

    return [
        {
            "hour": r[0],
            "total_observations": r[1],
            "avg_delay_seconds": r[2],
            "median_delay_seconds": r[3],
            "on_time_percent": round(r[4], 1),
        }
        for r in rows
    ]


# ── Route-level stats (all stops combined) ───────────────────────────


def get_route_stats(conn: duckdb.DuckDBPyConnection, f: FilterParams) -> dict:
    where, params = _build_filters(f, include_stop=False)

    row = conn.execute(f"""
        SELECT
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay,
            count(CASE WHEN abs(delay_seconds) < 60 THEN 1 END) * 100.0 / count(*) as on_time_pct,
            count(CASE WHEN delay_seconds > 300 THEN 1 END) * 100.0 / count(*) as late_5min_pct,
            round(avg(CASE WHEN delay_seconds >= 60 THEN delay_seconds END), 0) as avg_late_delay,
            min(observed_at) as first_obs,
            max(observed_at) as last_obs
        FROM delay_observations
        {where}
    """, params).fetchone()

    if row[0] == 0:
        return {"total_observations": 0, "message": "No data"}

    return {
        "total_observations": row[0],
        "avg_delay_seconds": row[1],
        "on_time_percent": round(row[2], 1),
        "late_5min_percent": round(row[3], 1),
        "avg_late_delay_seconds": row[4],
        "first_observation": str(row[5]),
        "last_observation": str(row[6]),
    }


def get_route_stats_by_day(
    conn: duckdb.DuckDBPyConnection, f: FilterParams
) -> list[dict]:
    where, params = _build_filters(
        f, include_stop=False, include_days_of_week=False
    )

    rows = conn.execute(f"""
        SELECT
            dayofweek(observed_at) as dow,
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay
        FROM delay_observations
        {where}
        GROUP BY dayofweek(observed_at)
        ORDER BY (dayofweek(observed_at) + 6) % 7
    """, params).fetchall()

    return [
        {
            "day_of_week": r[0],
            "day_name": _DAY_NAMES.get(r[0], str(r[0])),
            "total_observations": r[1],
            "avg_delay_seconds": r[2],
        }
        for r in rows
    ]


def get_route_stats_by_hour(
    conn: duckdb.DuckDBPyConnection, f: FilterParams
) -> list[dict]:
    where, params = _build_filters(f, include_stop=False)

    rows = conn.execute(f"""
        SELECT
            hour(scheduled_dep) as h,
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay
        FROM delay_observations
        {where}
        GROUP BY hour(scheduled_dep)
        ORDER BY hour(scheduled_dep)
    """, params).fetchall()

    return [
        {
            "hour": r[0],
            "total_observations": r[1],
            "avg_delay_seconds": r[2],
        }
        for r in rows
    ]


# ── Worst departures ────────────────────────────────────────────────


def get_worst_departures(
    conn: duckdb.DuckDBPyConnection, f: FilterParams, limit: int = 5
) -> list[dict]:
    where, params = _build_filters(f)

    rows = conn.execute(f"""
        SELECT
            strftime(scheduled_dep, '%H:%M') as departure_time,
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay_seconds
        FROM delay_observations
        {where}
        GROUP BY strftime(scheduled_dep, '%H:%M')
        HAVING count(*) >= 3
        ORDER BY avg(delay_seconds) DESC
        LIMIT ?
    """, params + [limit]).fetchall()

    return [
        {
            "departure_time": r[0],
            "total": r[1],
            "avg_delay_seconds": r[2],
        }
        for r in rows
    ]
