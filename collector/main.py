"""
Keleur collector — polls GTFS-RT, computes delays against static schedule,
and stores one observation per (trip, stop) passage in DuckDB.

Multi-network architecture:
  - One `Collector` instance per network, each running in its own thread.
  - All threads share the same DuckDB connection (DuckDB cursors are
    thread-safe; rows are tagged with `network_id`).
  - `MultiCollector` orchestrates startup, polling, and shutdown.

Dedup strategy:
  - Buffer observations in memory, keyed by (trip_id, stop_sequence).
  - When a key disappears from the feed (bus passed), flush it to DB.
  - Safety flush every SAFETY_FLUSH_SECONDS to limit data loss on crash.
"""

import logging
import signal
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import duckdb

from . import config, database, gtfs_rt, gtfs_static, networks
from .networks import Network

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("keleur.collector")

# ── Scheduled time resolution ──────────────────────────────────────────


def _parse_gtfs_time(time_str: str, service_date: datetime) -> datetime:
    """Convert GTFS time like '25:03:00' to a timezone-aware datetime."""
    h, m, s = map(int, time_str.split(":"))
    base = service_date.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(hours=h, minutes=m, seconds=s)


# ── Schedule cache ─────────────────────────────────────────────────────


class ScheduleCache:
    """Caches stop_times lookups from DuckDB to avoid repeated queries.

    Scoped to a single network. Only returns scheduled times for trips
    whose service_id is active today, to prevent matching a GTFS-RT
    trip_id against the wrong schedule (e.g. summer schedule trip_ids
    emitted during the school-year period).
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection, network_id: str):
        self._conn = conn
        self._network_id = network_id
        self._cache: dict[str, dict[int, str] | None] = {}
        self._active_services: set[str] = set()
        self._service_date_str: str = ""

    def refresh_active_services(self, date_str: str) -> None:
        """Reload active service_ids for the given date (YYYYMMDD)."""
        if date_str != self._service_date_str:
            self._active_services = database.get_active_service_ids(
                self._conn, self._network_id, date_str
            )
            self._service_date_str = date_str
            self._cache.clear()
            logger.info(
                "[%s] Loaded %d active service_ids for %s",
                self._network_id,
                len(self._active_services),
                date_str,
            )

    def get(self, trip_id: str) -> dict[int, str] | None:
        if trip_id not in self._cache:
            service_id = database.get_trip_service_id(
                self._conn, self._network_id, trip_id
            )
            if (
                service_id
                and self._active_services
                and service_id not in self._active_services
            ):
                self._cache[trip_id] = None  # Cache negative result
                return None
            times = database.get_scheduled_times(
                self._conn, self._network_id, trip_id
            )
            self._cache[trip_id] = times if times else None
        return self._cache[trip_id]

    def evict(self, trip_ids: set[str]) -> None:
        for tid in trip_ids:
            self._cache.pop(tid, None)

    def clear(self) -> None:
        self._cache.clear()
        self._service_date_str = ""


# ── Per-network collector ──────────────────────────────────────────────


class Collector:
    """Polls and stores observations for a single network."""

    def __init__(
        self,
        network: Network,
        conn: duckdb.DuckDBPyConnection,
    ):
        self._network = network
        self._tz = ZoneInfo(network.timezone)
        self._running = True
        # Each collector gets its own cursor for thread-safe DB access
        self._conn = conn.cursor()
        self._schedule_cache = ScheduleCache(self._conn, network.id)
        self._buffer: dict[tuple[str, int], dict] = {}
        self._previous_keys: set[tuple[str, int]] = set()
        self._last_flush: float = 0
        self._last_static_refresh: float = 0
        self._consecutive_errors = 0

    @property
    def network(self) -> Network:
        return self._network

    def stop(self) -> None:
        self._running = False

    def _today_service_date(self) -> datetime:
        """Today's date at midnight in the network's TZ."""
        return datetime.now(self._tz).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    def init_static(self) -> bool:
        """Load GTFS static data (called sequentially from MultiCollector).
        Returns True if successful."""
        try:
            self._refresh_static(force=False)
            return True
        except Exception:
            logger.exception("[%s] Initial GTFS static load failed", self._network.id)
            return False

    def run(self) -> None:
        nid = self._network.id
        logger.info("[%s] Collector starting", nid)

        # Static data should already be loaded by MultiCollector.
        # If not, try once more.
        if not self._is_static_loaded():
            try:
                self._refresh_static(force=False)
            except Exception:
                logger.exception("[%s] Initial GTFS static load failed", nid)
                return

        self._last_flush = time.monotonic()
        self._last_static_refresh = time.monotonic()

        logger.info(
            "[%s] Polling %s every %ds",
            nid,
            self._network.gtfs_rt_url,
            config.POLL_INTERVAL_SECONDS,
        )

        while self._running:
            cycle_start = time.monotonic()
            try:
                self._poll_cycle()
                self._consecutive_errors = 0
            except Exception:
                self._consecutive_errors += 1
                backoff = min(60, self._consecutive_errors * 5)
                logger.exception(
                    "[%s] Poll error (#%d consecutive), backing off %ds",
                    nid,
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
                    logger.exception("[%s] Failed to refresh GTFS static", nid)

            # Sleep until next poll
            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0, config.POLL_INTERVAL_SECONDS - elapsed)
            if sleep_time > 0 and self._running:
                # Sleep in small chunks to react quickly to shutdown
                end = time.monotonic() + sleep_time
                while self._running and time.monotonic() < end:
                    time.sleep(min(1.0, end - time.monotonic()))

        # Graceful shutdown: flush remaining buffer
        self._flush_buffer(self._buffer)
        logger.info("[%s] Collector stopped", nid)

    def _poll_cycle(self) -> None:
        snapshot = gtfs_rt.fetch(self._network)
        now = datetime.now(self._tz)
        service_date = self._today_service_date()

        # Refresh active service_ids once per day
        date_str = service_date.strftime("%Y%m%d")
        self._schedule_cache.refresh_active_services(date_str)

        current_keys: set[tuple[str, int]] = set()

        for su in snapshot.stop_updates:
            key = (su.trip_id, su.stop_sequence)
            current_keys.add(key)

            sched_times = self._schedule_cache.get(su.trip_id)
            if sched_times is None:
                continue
            sched_str = sched_times.get(su.stop_sequence)
            if sched_str is None:
                continue

            scheduled_dep = _parse_gtfs_time(sched_str, service_date)
            realtime_dep = datetime.fromtimestamp(
                su.realtime_dep_timestamp, tz=self._tz
            )
            delay_seconds = int((realtime_dep - scheduled_dep).total_seconds())

            # Skip obviously wrong delays (> 1h drift = likely date mismatch)
            if abs(delay_seconds) > 3600:
                continue

            # Strip tzinfo before storing: DuckDB TIMESTAMP has no timezone and
            # would convert tz-aware datetimes to UTC, breaking local-time queries
            # like "departures around 20:59". Store the wall-clock local time.
            self._buffer[key] = {
                "network_id": self._network.id,
                "observed_at": now.replace(tzinfo=None),
                "trip_id": su.trip_id,
                "route_id": su.route_id,
                "stop_id": su.stop_id,
                "direction_id": su.direction_id,
                "stop_sequence": su.stop_sequence,
                "scheduled_dep": scheduled_dep.replace(tzinfo=None),
                "realtime_dep": realtime_dep.replace(tzinfo=None),
                "delay_seconds": delay_seconds,
                "feed_timestamp": snapshot.timestamp,
            }

        # Flush observations for stops that disappeared (bus passed)
        disappeared = self._previous_keys - current_keys
        if disappeared:
            to_flush = [
                self._buffer.pop(k) for k in disappeared if k in self._buffer
            ]
            if to_flush:
                database.insert_observations(self._conn, to_flush)
                logger.info(
                    "[%s] Flushed %d observations (stops passed)",
                    self._network.id,
                    len(to_flush),
                )

        # Evict schedule cache for completed trips
        completed_trips = {k[0] for k in disappeared} - {k[0] for k in current_keys}
        if completed_trips:
            self._schedule_cache.evict(completed_trips)

        self._previous_keys = current_keys

        # Safety flush
        if time.monotonic() - self._last_flush > config.SAFETY_FLUSH_SECONDS:
            self._flush_buffer(dict(self._buffer))
            self._buffer.clear()
            self._last_flush = time.monotonic()

    def _flush_buffer(self, items: dict) -> None:
        if not items:
            return
        observations = list(items.values())
        database.insert_observations(self._conn, observations)
        logger.info(
            "[%s] Safety flush: %d observations",
            self._network.id,
            len(observations),
        )

    def _refresh_static(self, force: bool) -> None:
        gtfs_dir, changed = gtfs_static.download_and_extract(
            self._network, force=force
        )
        # Also reimport if calendar table is missing data (new table added)
        cal_file_exists = (gtfs_dir / "calendar.txt").exists()
        cal_empty = self._calendar_count() == 0
        needs_reimport = cal_file_exists and cal_empty

        if changed or not self._is_static_loaded() or needs_reimport:
            database.import_gtfs_static(self._conn, gtfs_dir, self._network.id)
            self._schedule_cache.clear()
            logger.info("[%s] GTFS static loaded into database", self._network.id)

    def _calendar_count(self) -> int:
        try:
            return self._conn.execute(
                "SELECT count(*) FROM calendar WHERE network_id = ?",
                [self._network.id],
            ).fetchone()[0]
        except Exception:
            return 0

    def _is_static_loaded(self) -> bool:
        st = self._conn.execute(
            "SELECT count(*) FROM stop_times WHERE network_id = ?",
            [self._network.id],
        ).fetchone()[0]
        cd = self._conn.execute(
            "SELECT count(*) FROM calendar_dates WHERE network_id = ?",
            [self._network.id],
        ).fetchone()[0]
        cal = self._calendar_count()
        return st > 0 and (cd > 0 or cal > 0)


# ── Multi-network orchestrator ─────────────────────────────────────────


class MultiCollector:
    """Runs one Collector thread per enabled network on a shared DB connection."""

    def __init__(self, conn: duckdb.DuckDBPyConnection | None = None):
        self._own_conn = conn is None
        self._conn = conn
        self._collectors: list[Collector] = []
        self._threads: list[threading.Thread] = []
        self._running = True

    def stop(self) -> None:
        self._running = False
        for c in self._collectors:
            c.stop()

    def run(self) -> None:
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)

        if self._conn is None:
            self._conn = database.get_connection()

        active = networks.enabled_networks()
        if not active:
            logger.warning("No enabled networks — collector idle")
            return

        logger.info(
            "Starting collectors for %d networks: %s",
            len(active),
            ", ".join(n.id for n in active),
        )

        # Phase 1: Load GTFS static data SEQUENTIALLY to avoid OOM
        # (10 parallel downloads + DB imports can exhaust memory on small VPS)
        for net in active:
            c = Collector(net, self._conn)
            logger.info("[%s] Loading GTFS static data…", net.id)
            c.init_static()
            self._collectors.append(c)

        # Phase 2: Start polling threads (lightweight, safe in parallel)
        for c in self._collectors:
            t = threading.Thread(
                target=c.run, daemon=True, name=f"collector-{c.network.id}"
            )
            self._threads.append(t)
            t.start()

        # Block until shutdown
        try:
            while self._running:
                time.sleep(1)
        finally:
            for c in self._collectors:
                c.stop()
            for t in self._threads:
                t.join(timeout=10)
            if self._own_conn and self._conn:
                self._conn.close()
            logger.info("All collectors stopped")

    def _handle_signal(self, signum, frame):
        logger.info("Received signal %d, shutting down…", signum)
        self.stop()


def main():
    MultiCollector().run()


if __name__ == "__main__":
    main()
