import logging
from pathlib import Path

import duckdb

from . import config

logger = logging.getLogger(__name__)


def get_connection() -> duckdb.DuckDBPyConnection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(config.DB_PATH))
    _init_schema(conn)
    _migrate_add_network_id(conn)
    return conn


def _init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delay_observations (
            network_id      VARCHAR,
            observed_at     TIMESTAMP,
            trip_id         VARCHAR,
            route_id        VARCHAR,
            stop_id         VARCHAR,
            direction_id    SMALLINT,
            stop_sequence   INTEGER,
            scheduled_dep   TIMESTAMP,
            realtime_dep    TIMESTAMP,
            delay_seconds   INTEGER,
            feed_timestamp  BIGINT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            network_id      VARCHAR,
            route_id        VARCHAR,
            short_name      VARCHAR,
            long_name       VARCHAR,
            route_type      SMALLINT,
            color           VARCHAR
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS stops (
            network_id      VARCHAR,
            stop_id         VARCHAR,
            stop_name       VARCHAR,
            lat             DOUBLE,
            lon             DOUBLE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS stop_times (
            network_id      VARCHAR,
            trip_id         VARCHAR,
            stop_id         VARCHAR,
            stop_sequence   INTEGER,
            departure_time  VARCHAR,
            arrival_time    VARCHAR
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            network_id      VARCHAR,
            trip_id         VARCHAR,
            route_id        VARCHAR,
            service_id      VARCHAR,
            trip_headsign   VARCHAR,
            direction_id    SMALLINT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_dates (
            network_id      VARCHAR,
            service_id      VARCHAR,
            date            VARCHAR,
            exception_type  SMALLINT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS gtfs_meta (
            network_id      VARCHAR,
            key             VARCHAR,
            value           VARCHAR
        )
    """)

    # Indexes — created once, safe for concurrent reads
    for stmt in [
        "CREATE INDEX IF NOT EXISTS idx_stop_times_trip ON stop_times(network_id, trip_id)",
        "CREATE INDEX IF NOT EXISTS idx_calendar_dates_service ON calendar_dates(network_id, service_id, date)",
        "CREATE INDEX IF NOT EXISTS idx_obs_network_route ON delay_observations(network_id, route_id)",
    ]:
        try:
            conn.execute(stmt)
        except Exception:
            pass  # Index may already exist from previous schema version


def _migrate_add_network_id(conn: duckdb.DuckDBPyConnection) -> None:
    """Backfill network_id='ilevia' on rows that predate multi-network support.

    Idempotent: only updates rows where network_id IS NULL or empty.
    """
    for table in (
        "delay_observations",
        "routes",
        "stops",
        "stop_times",
        "trips",
        "calendar_dates",
        "gtfs_meta",
    ):
        try:
            cols = conn.execute(f"DESCRIBE {table}").fetchall()
            col_names = {c[0] for c in cols}
            if "network_id" not in col_names:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN network_id VARCHAR")
            updated = conn.execute(
                f"UPDATE {table} SET network_id = 'ilevia' "
                f"WHERE network_id IS NULL OR network_id = ''"
            )
        except Exception as exc:
            logger.warning("Migration of %s skipped: %s", table, exc)


def import_gtfs_static(
    conn: duckdb.DuckDBPyConnection,
    gtfs_dir: Path,
    network_id: str,
) -> None:
    """Import GTFS static CSV files into DuckDB, replacing previous data for this network."""
    logger.info("[%s] Importing GTFS static data from %s", network_id, gtfs_dir)

    # Routes (DISTINCT ON route_id: some GTFS feeds have duplicate route entries)
    conn.execute("DELETE FROM routes WHERE network_id = ?", [network_id])
    conn.execute(f"""
        INSERT INTO routes (network_id, route_id, short_name, long_name, route_type, color)
        SELECT '{network_id}', route_id, first(route_short_name), first(route_long_name),
               CAST(first(route_type) AS SMALLINT), first(route_color)
        FROM read_csv_auto('{gtfs_dir}/routes.txt', header=true, all_varchar=true)
        GROUP BY route_id
    """)
    count = conn.execute(
        "SELECT count(*) FROM routes WHERE network_id = ?", [network_id]
    ).fetchone()[0]
    logger.info("[%s] Imported %d routes", network_id, count)

    # Stops (GROUP BY stop_id: some GTFS feeds have duplicate stop entries)
    conn.execute("DELETE FROM stops WHERE network_id = ?", [network_id])
    conn.execute(f"""
        INSERT INTO stops (network_id, stop_id, stop_name, lat, lon)
        SELECT '{network_id}', stop_id, first(stop_name),
               CAST(first(stop_lat) AS DOUBLE), CAST(first(stop_lon) AS DOUBLE)
        FROM read_csv_auto('{gtfs_dir}/stops.txt', header=true, all_varchar=true)
        GROUP BY stop_id
    """)
    count = conn.execute(
        "SELECT count(*) FROM stops WHERE network_id = ?", [network_id]
    ).fetchone()[0]
    logger.info("[%s] Imported %d stops", network_id, count)

    # Trips (GROUP BY trip_id: some GTFS feeds have duplicate trip entries)
    conn.execute("DELETE FROM trips WHERE network_id = ?", [network_id])
    conn.execute(f"""
        INSERT INTO trips (network_id, trip_id, route_id, service_id, trip_headsign, direction_id)
        SELECT '{network_id}', trip_id, first(route_id), first(service_id), first(trip_headsign),
               CAST(first(direction_id) AS SMALLINT)
        FROM read_csv_auto('{gtfs_dir}/trips.txt', header=true, all_varchar=true)
        GROUP BY trip_id
    """)
    count = conn.execute(
        "SELECT count(*) FROM trips WHERE network_id = ?", [network_id]
    ).fetchone()[0]
    logger.info("[%s] Imported %d trips", network_id, count)

    # Stop times
    conn.execute("DELETE FROM stop_times WHERE network_id = ?", [network_id])
    conn.execute(f"""
        INSERT INTO stop_times (network_id, trip_id, stop_id, stop_sequence, departure_time, arrival_time)
        SELECT '{network_id}', trip_id, stop_id,
               CAST(stop_sequence AS INTEGER),
               departure_time, arrival_time
        FROM read_csv_auto('{gtfs_dir}/stop_times.txt', header=true, all_varchar=true)
    """)
    count = conn.execute(
        "SELECT count(*) FROM stop_times WHERE network_id = ?", [network_id]
    ).fetchone()[0]
    logger.info("[%s] Imported %d stop_times", network_id, count)

    # Calendar dates
    conn.execute("DELETE FROM calendar_dates WHERE network_id = ?", [network_id])
    cal_file = gtfs_dir / "calendar_dates.txt"
    if cal_file.exists():
        conn.execute(f"""
            INSERT INTO calendar_dates (network_id, service_id, date, exception_type)
            SELECT '{network_id}', service_id, date, CAST(exception_type AS SMALLINT)
            FROM read_csv_auto('{gtfs_dir}/calendar_dates.txt', header=true, all_varchar=true)
        """)
        count = conn.execute(
            "SELECT count(*) FROM calendar_dates WHERE network_id = ?", [network_id]
        ).fetchone()[0]
        logger.info("[%s] Imported %d calendar_dates", network_id, count)

    # Indexes are created once at startup in _init_schema, not per-import


def insert_observations(
    conn: duckdb.DuckDBPyConnection, observations: list[dict]
) -> None:
    """Batch insert delay observations. Each obs dict must have network_id."""
    if not observations:
        return
    conn.executemany(
        """
        INSERT INTO delay_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                obs["network_id"],
                obs["observed_at"],
                obs["trip_id"],
                obs["route_id"],
                obs["stop_id"],
                obs["direction_id"],
                obs["stop_sequence"],
                obs["scheduled_dep"],
                obs["realtime_dep"],
                obs["delay_seconds"],
                obs["feed_timestamp"],
            )
            for obs in observations
        ],
    )
    logger.debug("Inserted %d observations", len(observations))


def deduplicate_observations(conn: duckdb.DuckDBPyConnection) -> None:
    """Remove duplicate observations, keeping the last one per (network_id, trip_id, stop_id, scheduled_dep)."""
    try:
        before = conn.execute("SELECT count(*) FROM delay_observations").fetchone()[0]
        if before == 0:
            return
        conn.execute("""
            CREATE TABLE delay_observations_dedup AS
            SELECT * FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY network_id, trip_id, stop_id, scheduled_dep
                    ORDER BY feed_timestamp DESC
                ) as rn
                FROM delay_observations
            ) WHERE rn = 1
        """)
        conn.execute("DROP TABLE delay_observations")
        conn.execute("ALTER TABLE delay_observations_dedup RENAME TO delay_observations")
        conn.execute("ALTER TABLE delay_observations DROP COLUMN rn")
        after = conn.execute("SELECT count(*) FROM delay_observations").fetchone()[0]
        logger.info(
            "Deduplicated observations: %d -> %d (removed %d)", before, after, before - after
        )
    except Exception:
        # Dedup failed — clean up temp table but NEVER drop observations data
        logger.exception("Dedup failed, skipping (observations data preserved)")
        try:
            conn.execute("DROP TABLE IF EXISTS delay_observations_dedup")
        except Exception:
            pass


def get_scheduled_times(
    conn: duckdb.DuckDBPyConnection, network_id: str, trip_id: str
) -> dict[int, str]:
    """Return {stop_sequence: departure_time} for a given (network, trip)."""
    rows = conn.execute(
        "SELECT stop_sequence, departure_time FROM stop_times "
        "WHERE network_id = ? AND trip_id = ?",
        [network_id, trip_id],
    ).fetchall()
    return {seq: dep for seq, dep in rows}


def get_active_service_ids(
    conn: duckdb.DuckDBPyConnection, network_id: str, date_str: str
) -> set[str]:
    """Return service_ids active on a given date (YYYYMMDD format) for a network."""
    rows = conn.execute(
        "SELECT service_id FROM calendar_dates "
        "WHERE network_id = ? AND date = ? AND exception_type = 1",
        [network_id, date_str],
    ).fetchall()
    return {r[0] for r in rows}


def get_trip_service_id(
    conn: duckdb.DuckDBPyConnection, network_id: str, trip_id: str
) -> str | None:
    """Return the service_id for a (network, trip), or None if not found."""
    row = conn.execute(
        "SELECT service_id FROM trips WHERE network_id = ? AND trip_id = ?",
        [network_id, trip_id],
    ).fetchone()
    return row[0] if row else None


def last_observation_at(
    conn: duckdb.DuckDBPyConnection, network_id: str
) -> str | None:
    """Most recent observed_at for a network, or None if no data yet."""
    row = conn.execute(
        "SELECT max(observed_at) FROM delay_observations WHERE network_id = ?",
        [network_id],
    ).fetchone()
    return str(row[0]) if row and row[0] else None
