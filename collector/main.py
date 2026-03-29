"""
Keleur collector — polls GTFS-RT, computes delays against static schedule,
and stores one observation per (trip, stop) passage in DuckDB.

Dedup strategy:
  - Buffer observations in memory, keyed by (trip_id, stop_sequence).
  - When a key disappears from the feed (bus passed), flush it to DB.
  - Safety flush every SAFETY_FLUSH_SECONDS to limit data loss on crash.
"""

import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import duckdb

from . import config, database, gtfs_rt, gtfs_static

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("keleur.collector")

# ── Scheduled time resolution ──────────────────────────────────────────

TZ = ZoneInfo(config.TIMEZONE)


def _parse_gtfs_time(time_str: str, service_date: datetime) -> datetime:
    """Convert GTFS time like '25:03:00' to a timezone-aware datetime."""
    h, m, s = map(int, time_str.split(":"))
    base = service_date.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(hours=h, minutes=m, seconds=s)


def _today_service_date() -> datetime:
    """Return today's date at midnight in local TZ, for GTFS time conversion.

    GTFS trips starting before midnight but running past midnight use times
    > 24:00:00. Their service date is the day they *started*, so between
    midnight and ~4 AM we also check yesterday's date when a trip isn't found.
    """
    return datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)


# ── Schedule cache ─────────────────────────────────────────────────────

class ScheduleCache:
    """Caches stop_times lookups from DuckDB to avoid repeated queries."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self._conn = conn
        self._cache: dict[str, dict[int, str]] = {}  # trip_id -> {seq: dep_time}

    def get(self, trip_id: str) -> dict[int, str] | None:
        if trip_id not in self._cache:
            times = database.get_scheduled_times(self._conn, trip_id)
            if times:
                self._cache[trip_id] = times
            else:
                return None
        return self._cache[trip_id]

    def evict(self, trip_ids: set[str]) -> None:
        for tid in trip_ids:
            self._cache.pop(tid, None)

    def clear(self) -> None:
        self._cache.clear()


# ── Main collector ─────────────────────────────────────────────────────

class Collector:
    def __init__(self, conn: duckdb.DuckDBPyConnection | None = None):
        self._running = True
        self._own_conn = conn is None  # True if we created the connection ourselves
        self._conn = conn
        self._schedule_cache: ScheduleCache | None = None
        self._buffer: dict[tuple[str, int], dict] = {}  # (trip_id, stop_seq) -> obs
        self._previous_keys: set[tuple[str, int]] = set()
        self._last_flush: float = 0
        self._last_static_refresh: float = 0
        self._consecutive_errors = 0

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        # Only register signal handlers from the main thread
        import threading
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)

        logger.info("Keleur collector starting")

        # Init database (use provided connection or create our own)
        if self._conn is None:
            self._conn = database.get_connection()
        self._schedule_cache = ScheduleCache(self._conn)

        # Initial GTFS static load
        self._refresh_static(force=False)

        self._last_flush = time.monotonic()
        self._last_static_refresh = time.monotonic()

        logger.info(
            "Polling %s every %ds", config.GTFS_RT_URL, config.POLL_INTERVAL_SECONDS
        )

        while self._running:
            cycle_start = time.monotonic()
            try:
                self._poll_cycle()
                self._consecutive_errors = 0
            except Exception:
                self._consecutive_errors += 1
                backoff = min(30, self._consecutive_errors * 5)
                logger.exception(
                    "Poll error (#%d consecutive), backing off %ds",
                    self._consecutive_errors,
                    backoff,
                )
                time.sleep(backoff)
                continue

            # Periodic GTFS static refresh
            if (
                time.monotonic() - self._last_static_refresh
                > config.STATIC_REFRESH_SECONDS
            ):
                try:
                    self._refresh_static(force=False)
                    self._last_static_refresh = time.monotonic()
                except Exception:
                    logger.exception("Failed to refresh GTFS static")

            # Sleep until next poll
            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0, config.POLL_INTERVAL_SECONDS - elapsed)
            if sleep_time > 0 and self._running:
                time.sleep(sleep_time)

        # Graceful shutdown: flush remaining buffer
        self._flush_buffer(self._buffer)
        if self._own_conn and self._conn:
            self._conn.close()
        logger.info("Collector stopped")

    def _poll_cycle(self) -> None:
        snapshot = gtfs_rt.fetch()
        now = datetime.now(TZ)
        service_date = _today_service_date()

        current_keys: set[tuple[str, int]] = set()

        for su in snapshot.stop_updates:
            key = (su.trip_id, su.stop_sequence)
            current_keys.add(key)

            # Look up scheduled time
            sched_times = self._schedule_cache.get(su.trip_id)
            if sched_times is None:
                # Trip not in static GTFS — might be yesterday's service date
                continue
            sched_str = sched_times.get(su.stop_sequence)
            if sched_str is None:
                continue

            scheduled_dep = _parse_gtfs_time(sched_str, service_date)
            realtime_dep = datetime.fromtimestamp(su.realtime_dep_timestamp, tz=TZ)
            delay_seconds = int((realtime_dep - scheduled_dep).total_seconds())

            # Skip obviously wrong delays (> 1h drift = likely date mismatch)
            if abs(delay_seconds) > 3600:
                continue

            self._buffer[key] = {
                "observed_at": now,
                "trip_id": su.trip_id,
                "route_id": su.route_id,
                "stop_id": su.stop_id,
                "direction_id": su.direction_id,
                "stop_sequence": su.stop_sequence,
                "scheduled_dep": scheduled_dep,
                "realtime_dep": realtime_dep,
                "delay_seconds": delay_seconds,
                "feed_timestamp": snapshot.timestamp,
            }

        # Flush observations for stops that disappeared (bus passed)
        disappeared = self._previous_keys - current_keys
        if disappeared:
            to_flush = [self._buffer.pop(k) for k in disappeared if k in self._buffer]
            if to_flush:
                database.insert_observations(self._conn, to_flush)
                logger.info(
                    "Flushed %d observations (stops passed)", len(to_flush)
                )

        # Evict schedule cache for completed trips
        completed_trips = {k[0] for k in disappeared} - {k[0] for k in current_keys}
        if completed_trips:
            self._schedule_cache.evict(completed_trips)

        self._previous_keys = current_keys

        # Safety flush
        if time.monotonic() - self._last_flush > config.SAFETY_FLUSH_SECONDS:
            self._flush_buffer(dict(self._buffer))
            self._last_flush = time.monotonic()

    def _flush_buffer(self, items: dict) -> None:
        if not items:
            return
        observations = list(items.values())
        database.insert_observations(self._conn, observations)
        logger.info("Safety flush: %d observations", len(observations))

    def _refresh_static(self, force: bool) -> None:
        gtfs_dir, changed = gtfs_static.download_and_extract(force=force)
        if changed or not self._is_static_loaded():
            database.import_gtfs_static(self._conn, gtfs_dir)
            self._schedule_cache.clear()
            logger.info("GTFS static loaded into database")

    def _is_static_loaded(self) -> bool:
        count = self._conn.execute("SELECT count(*) FROM stop_times").fetchone()[0]
        return count > 0

    def _handle_signal(self, signum, frame):
        logger.info("Received signal %d, shutting down…", signum)
        self._running = False


def main():
    Collector().run()


if __name__ == "__main__":
    main()
