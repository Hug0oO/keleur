import logging
from pathlib import Path

import duckdb

from . import config

logger = logging.getLogger(__name__)


def get_connection() -> duckdb.DuckDBPyConnection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(config.DB_PATH))
    _init_schema(conn)
    return conn


def _init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delay_observations (
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
            route_id        VARCHAR PRIMARY KEY,
            short_name      VARCHAR,
            long_name       VARCHAR,
            route_type      SMALLINT,
            color           VARCHAR
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS stops (
            stop_id         VARCHAR PRIMARY KEY,
            stop_name       VARCHAR,
            lat             DOUBLE,
            lon             DOUBLE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS stop_times (
            trip_id         VARCHAR,
            stop_id         VARCHAR,
            stop_sequence   INTEGER,
            departure_time  VARCHAR,
            arrival_time    VARCHAR
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            trip_id         VARCHAR PRIMARY KEY,
            route_id        VARCHAR,
            service_id      VARCHAR,
            trip_headsign   VARCHAR,
            direction_id    SMALLINT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_dates (
            service_id      VARCHAR,
            date            VARCHAR,
            exception_type  SMALLINT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS gtfs_meta (
            key             VARCHAR PRIMARY KEY,
            value           VARCHAR
        )
    """)


def import_gtfs_static(conn: duckdb.DuckDBPyConnection, gtfs_dir: Path) -> None:
    """Import GTFS static CSV files into DuckDB, replacing previous data."""
    logger.info("Importing GTFS static data from %s", gtfs_dir)

    # Routes
    conn.execute("DELETE FROM routes")
    conn.execute(f"""
        INSERT INTO routes
        SELECT route_id, route_short_name, route_long_name,
               CAST(route_type AS SMALLINT), route_color
        FROM read_csv_auto('{gtfs_dir}/routes.txt', header=true, all_varchar=true)
    """)
    count = conn.execute("SELECT count(*) FROM routes").fetchone()[0]
    logger.info("Imported %d routes", count)

    # Stops
    conn.execute("DELETE FROM stops")
    conn.execute(f"""
        INSERT INTO stops
        SELECT stop_id, stop_name,
               CAST(stop_lat AS DOUBLE), CAST(stop_lon AS DOUBLE)
        FROM read_csv_auto('{gtfs_dir}/stops.txt', header=true, all_varchar=true)
    """)
    count = conn.execute("SELECT count(*) FROM stops").fetchone()[0]
    logger.info("Imported %d stops", count)

    # Trips
    conn.execute("DELETE FROM trips")
    conn.execute(f"""
        INSERT INTO trips
        SELECT trip_id, route_id, service_id, trip_headsign,
               CAST(direction_id AS SMALLINT)
        FROM read_csv_auto('{gtfs_dir}/trips.txt', header=true, all_varchar=true)
    """)
    count = conn.execute("SELECT count(*) FROM trips").fetchone()[0]
    logger.info("Imported %d trips", count)

    # Stop times - the big one (~1.6M rows)
    conn.execute("DELETE FROM stop_times")
    conn.execute(f"""
        INSERT INTO stop_times
        SELECT trip_id, stop_id,
               CAST(stop_sequence AS INTEGER),
               departure_time, arrival_time
        FROM read_csv_auto('{gtfs_dir}/stop_times.txt', header=true, all_varchar=true)
    """)
    count = conn.execute("SELECT count(*) FROM stop_times").fetchone()[0]
    logger.info("Imported %d stop_times", count)

    # Calendar dates
    conn.execute("DELETE FROM calendar_dates")
    cal_file = gtfs_dir / "calendar_dates.txt"
    if cal_file.exists():
        conn.execute(f"""
            INSERT INTO calendar_dates
            SELECT service_id, date, CAST(exception_type AS SMALLINT)
            FROM read_csv_auto('{gtfs_dir}/calendar_dates.txt', header=true, all_varchar=true)
        """)
        count = conn.execute("SELECT count(*) FROM calendar_dates").fetchone()[0]
        logger.info("Imported %d calendar_dates", count)

    # Create indexes for fast lookups
    conn.execute("DROP INDEX IF EXISTS idx_stop_times_trip")
    conn.execute("CREATE INDEX idx_stop_times_trip ON stop_times(trip_id)")
    conn.execute("DROP INDEX IF EXISTS idx_calendar_dates_service")
    conn.execute("CREATE INDEX idx_calendar_dates_service ON calendar_dates(service_id, date)")


def insert_observations(conn: duckdb.DuckDBPyConnection, observations: list[dict]) -> None:
    """Batch insert delay observations."""
    if not observations:
        return
    conn.executemany(
        """
        INSERT INTO delay_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
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
    """Remove duplicate observations, keeping the last one per (trip_id, stop_id, scheduled_dep)."""
    before = conn.execute("SELECT count(*) FROM delay_observations").fetchone()[0]
    conn.execute("""
        CREATE TABLE delay_observations_dedup AS
        SELECT * FROM (
            SELECT *, row_number() OVER (
                PARTITION BY trip_id, stop_id, scheduled_dep
                ORDER BY feed_timestamp DESC
            ) as rn
            FROM delay_observations
        ) WHERE rn = 1
    """)
    conn.execute("DROP TABLE delay_observations")
    conn.execute("ALTER TABLE delay_observations_dedup RENAME TO delay_observations")
    # Drop the rn column
    conn.execute("ALTER TABLE delay_observations DROP COLUMN rn")
    after = conn.execute("SELECT count(*) FROM delay_observations").fetchone()[0]
    logger.info("Deduplicated observations: %d -> %d (removed %d)", before, after, before - after)


def get_scheduled_times(
    conn: duckdb.DuckDBPyConnection, trip_id: str
) -> dict[int, str]:
    """Return {stop_sequence: departure_time} for a given trip."""
    rows = conn.execute(
        "SELECT stop_sequence, departure_time FROM stop_times WHERE trip_id = ?",
        [trip_id],
    ).fetchall()
    return {seq: dep for seq, dep in rows}


def get_active_service_ids(
    conn: duckdb.DuckDBPyConnection, date_str: str
) -> set[str]:
    """Return service_ids active on a given date (YYYYMMDD format)."""
    rows = conn.execute(
        "SELECT service_id FROM calendar_dates WHERE date = ? AND exception_type = 1",
        [date_str],
    ).fetchall()
    return {r[0] for r in rows}


def get_trip_service_id(
    conn: duckdb.DuckDBPyConnection, trip_id: str
) -> str | None:
    """Return the service_id for a trip, or None if not found."""
    row = conn.execute(
        "SELECT service_id FROM trips WHERE trip_id = ?",
        [trip_id],
    ).fetchone()
    return row[0] if row else None
