"""DuckDB analytical queries for delay statistics."""

import duckdb

# Day names for output
_DAY_NAMES = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _time_filter(time_from: str | None, time_to: str | None) -> tuple[str, list]:
    """Build SQL clause to filter by time-of-day window."""
    if not time_from and not time_to:
        return "", []
    clauses = []
    params = []
    if time_from:
        clauses.append("CAST(scheduled_dep AS TIME) >= ?")
        params.append(time_from + ":00")
    if time_to:
        clauses.append("CAST(scheduled_dep AS TIME) <= ?")
        params.append(time_to + ":00")
    return " AND " + " AND ".join(clauses), params


def get_delay_stats(
    conn: duckdb.DuckDBPyConnection,
    route_id: str,
    stop_id: str,
    direction_id: int,
    time_from: str | None,
    time_to: str | None,
    days: int,
) -> dict:
    time_clause, time_params = _time_filter(time_from, time_to)
    params = [route_id, direction_id, stop_id, days] + time_params

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
            max(observed_at) as last_obs
        FROM delay_observations
        WHERE route_id = ? AND direction_id = ?
          AND stop_id IN (SELECT s2.stop_id FROM stops s2 WHERE s2.stop_name = (SELECT s1.stop_name FROM stops s1 WHERE s1.stop_id = ?))
          AND observed_at >= current_date - INTERVAL (?) DAY
          {time_clause}
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
    }


def get_stats_by_day_of_week(
    conn: duckdb.DuckDBPyConnection,
    route_id: str,
    stop_id: str,
    direction_id: int,
    time_from: str | None,
    time_to: str | None,
    days: int,
) -> list[dict]:
    time_clause, time_params = _time_filter(time_from, time_to)
    params = [route_id, direction_id, stop_id, days] + time_params

    rows = conn.execute(f"""
        SELECT
            dayofweek(observed_at) as dow,
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay,
            round(median(delay_seconds), 1) as median_delay,
            count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*) as on_time_pct,
            count(CASE WHEN delay_seconds > 300 THEN 1 END) * 100.0 / count(*) as late_5min_pct
        FROM delay_observations
        WHERE route_id = ? AND direction_id = ?
          AND stop_id IN (SELECT s2.stop_id FROM stops s2 WHERE s2.stop_name = (SELECT s1.stop_name FROM stops s1 WHERE s1.stop_id = ?))
          AND observed_at >= current_date - INTERVAL (?) DAY
          {time_clause}
        GROUP BY dayofweek(observed_at)
        ORDER BY dayofweek(observed_at)
    """, params).fetchall()

    return [
        {
            "day_of_week": r[0],
            "day_name": _DAY_NAMES[r[0] - 1] if 1 <= r[0] <= 7 else str(r[0]),
            "total_observations": r[1],
            "avg_delay_seconds": r[2],
            "median_delay_seconds": r[3],
            "on_time_percent": round(r[4], 1),
            "late_5min_percent": round(r[5], 1),
        }
        for r in rows
    ]


def get_stats_by_hour(
    conn: duckdb.DuckDBPyConnection,
    route_id: str,
    stop_id: str,
    direction_id: int,
    days: int,
) -> list[dict]:
    rows = conn.execute("""
        SELECT
            hour(scheduled_dep) as h,
            count(*) as total,
            round(avg(delay_seconds), 1) as avg_delay,
            round(median(delay_seconds), 1) as median_delay,
            count(CASE WHEN abs(delay_seconds) <= 60 THEN 1 END) * 100.0 / count(*) as on_time_pct
        FROM delay_observations
        WHERE route_id = ? AND direction_id = ?
          AND stop_id IN (SELECT s2.stop_id FROM stops s2 WHERE s2.stop_name = (SELECT s1.stop_name FROM stops s1 WHERE s1.stop_id = ?))
          AND observed_at >= current_date - INTERVAL (?) DAY
        GROUP BY hour(scheduled_dep)
        ORDER BY hour(scheduled_dep)
    """, [route_id, direction_id, stop_id, days]).fetchall()

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
