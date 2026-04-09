"""Tests for the collector — focused on the timezone-naive storage invariant.

DuckDB's TIMESTAMP type is timezone-naive: passing a tz-aware datetime causes
silent UTC conversion, which breaks local-time queries (e.g. "departures
around 20:59"). The fix is `.replace(tzinfo=None)` before storing. These
tests guard against regression.
"""

import time
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import duckdb
import pytest

from collector import database, networks
from collector.gtfs_rt import FeedSnapshot, StopUpdate
from collector.main import Collector, _parse_gtfs_time


def _new_collector(conn, network):
    """Build a Collector and prime its safety-flush timer so calling
    _poll_cycle directly doesn't immediately flush+clear the buffer."""
    c = Collector(network, conn)
    c._last_flush = time.monotonic()
    return c


# ── _parse_gtfs_time ─────────────────────────────────────────────────


def test_parse_gtfs_time_normal():
    service_date = datetime(2025, 4, 8, tzinfo=ZoneInfo("Europe/Paris"))
    out = _parse_gtfs_time("08:15:30", service_date)
    assert out.hour == 8
    assert out.minute == 15
    assert out.second == 30
    assert out.tzinfo == ZoneInfo("Europe/Paris")


def test_parse_gtfs_time_post_midnight_overflow():
    """GTFS allows times like 25:03:00 to mean 1:03 next day on same service."""
    service_date = datetime(2025, 4, 8, tzinfo=ZoneInfo("Europe/Paris"))
    out = _parse_gtfs_time("25:03:00", service_date)
    assert out.day == 9
    assert out.hour == 1
    assert out.minute == 3


# ── Buffered observations are timezone-naive ─────────────────────────


@pytest.fixture
def in_memory_conn():
    """A fresh in-memory DuckDB with the schema initialized."""
    conn = duckdb.connect(":memory:")
    database._init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def fake_network():
    return networks.get("ilevia")  # Just need a real Network instance for tz


def _seed_schedule(conn, network_id, trip_id, service_id, route_id, stop_seq):
    """Insert minimal stop_times + trips + active service so the cache resolves."""
    conn.execute(
        "INSERT INTO trips VALUES (?, ?, ?, ?, ?, ?)",
        [network_id, trip_id, route_id, service_id, "TEST_HEADSIGN", 0],
    )
    conn.execute(
        "INSERT INTO stop_times VALUES (?, ?, ?, ?, ?, ?)",
        [network_id, trip_id, "STOP_A", stop_seq, "08:15:00", "08:15:00"],
    )
    today_str = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y%m%d")
    conn.execute(
        "INSERT INTO calendar_dates VALUES (?, ?, ?, ?)",
        [network_id, service_id, today_str, 1],
    )


def test_buffered_observation_is_timezone_naive(in_memory_conn, fake_network):
    """Reproduces the bug: an obs in the buffer must have tzinfo=None on
    observed_at, scheduled_dep, and realtime_dep before being inserted, or
    DuckDB will silently convert to UTC and break local-time queries."""
    _seed_schedule(
        in_memory_conn,
        network_id="ilevia",
        trip_id="TRIP1",
        service_id="SVC1",
        route_id="R1",
        stop_seq=1,
    )

    collector = _new_collector(in_memory_conn, fake_network)

    # Build a snapshot whose departure timestamp is "now" so delay ≈ 0
    now_paris = datetime.now(ZoneInfo("Europe/Paris"))
    today_815 = now_paris.replace(hour=8, minute=15, second=0, microsecond=0)
    snap = FeedSnapshot(
        timestamp=int(today_815.timestamp()),
        stop_updates=[
            StopUpdate(
                trip_id="TRIP1",
                route_id="R1",
                direction_id=0,
                stop_id="STOP_A",
                stop_sequence=1,
                realtime_dep_timestamp=int(today_815.timestamp()),
            )
        ],
    )

    with patch("collector.main.gtfs_rt.fetch", return_value=snap):
        collector._poll_cycle()

    assert ("TRIP1", 1) in collector._buffer
    obs = collector._buffer[("TRIP1", 1)]
    assert obs["observed_at"].tzinfo is None
    assert obs["scheduled_dep"].tzinfo is None
    assert obs["realtime_dep"].tzinfo is None
    assert obs["network_id"] == "ilevia"


def test_inserted_observation_round_trips_local_time(in_memory_conn, fake_network):
    """End-to-end: a 20:59 local departure must come back as 20:59 from DuckDB,
    not as 19:59 (which would happen if tz-aware data got UTC-converted)."""
    _seed_schedule(
        in_memory_conn,
        network_id="ilevia",
        trip_id="TRIP_LATE",
        service_id="SVC1",
        route_id="R1",
        stop_seq=2,
    )
    # Override the seeded stop_time to 20:59
    in_memory_conn.execute(
        "UPDATE stop_times SET departure_time = '20:59:00' "
        "WHERE network_id = ? AND trip_id = ?",
        ["ilevia", "TRIP_LATE"],
    )

    collector = _new_collector(in_memory_conn, fake_network)

    today_paris = datetime.now(ZoneInfo("Europe/Paris")).replace(
        hour=20, minute=59, second=0, microsecond=0
    )
    snap = FeedSnapshot(
        timestamp=int(today_paris.timestamp()),
        stop_updates=[
            StopUpdate(
                trip_id="TRIP_LATE",
                route_id="R1",
                direction_id=0,
                stop_id="STOP_A",
                stop_sequence=2,
                realtime_dep_timestamp=int(today_paris.timestamp()),
            )
        ],
    )

    with patch("collector.main.gtfs_rt.fetch", return_value=snap):
        collector._poll_cycle()

    # Force a flush
    collector._flush_buffer(dict(collector._buffer))

    row = in_memory_conn.execute(
        "SELECT scheduled_dep, realtime_dep FROM delay_observations "
        "WHERE network_id = ? AND trip_id = ?",
        ["ilevia", "TRIP_LATE"],
    ).fetchone()
    assert row is not None
    sched, rt = row
    assert sched.hour == 20
    assert sched.minute == 59
    assert rt.hour == 20
    assert rt.minute == 59


def test_extreme_delay_is_dropped(in_memory_conn, fake_network):
    """A 2-hour drift means the date is wrong — must be skipped, not stored."""
    _seed_schedule(
        in_memory_conn,
        network_id="ilevia",
        trip_id="TRIP_DRIFT",
        service_id="SVC1",
        route_id="R1",
        stop_seq=3,
    )

    collector = _new_collector(in_memory_conn, fake_network)

    today_815 = datetime.now(ZoneInfo("Europe/Paris")).replace(
        hour=8, minute=15, second=0, microsecond=0
    )
    # Real time is 2 hours later → suspicious drift
    drifted = today_815 + timedelta(hours=2)
    snap = FeedSnapshot(
        timestamp=int(drifted.timestamp()),
        stop_updates=[
            StopUpdate(
                trip_id="TRIP_DRIFT",
                route_id="R1",
                direction_id=0,
                stop_id="STOP_A",
                stop_sequence=1,  # matches seeded stop_time at 08:15
                realtime_dep_timestamp=int(drifted.timestamp()),
            )
        ],
    )

    with patch("collector.main.gtfs_rt.fetch", return_value=snap):
        collector._poll_cycle()

    assert ("TRIP_DRIFT", 1) not in collector._buffer


def test_inactive_service_id_is_skipped(in_memory_conn, fake_network):
    """If a trip's service_id isn't active today, the observation must be
    dropped — guards against the GTFS-RT-emits-summer-trips-in-school-year bug.

    Note: the cache only filters when _active_services is *non-empty*, so we
    must seed at least one OTHER service for today before testing the skip.
    """
    # Trip belongs to SUMMER_SVC
    in_memory_conn.execute(
        "INSERT INTO trips VALUES (?, ?, ?, ?, ?, ?)",
        ["ilevia", "TRIP_OFF", "R1", "SUMMER_SVC", "TEST", 0],
    )
    in_memory_conn.execute(
        "INSERT INTO stop_times VALUES (?, ?, ?, ?, ?, ?)",
        ["ilevia", "TRIP_OFF", "STOP_A", 1, "08:15:00", "08:15:00"],
    )
    # Seed a *different* service as active today, so _active_services is
    # non-empty and the inactive-trip filter actually runs
    today_str = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y%m%d")
    in_memory_conn.execute(
        "INSERT INTO calendar_dates VALUES (?, ?, ?, ?)",
        ["ilevia", "WEEKDAY_SVC", today_str, 1],
    )

    collector = _new_collector(in_memory_conn, fake_network)

    today_815 = datetime.now(ZoneInfo("Europe/Paris")).replace(
        hour=8, minute=15, second=0, microsecond=0
    )
    snap = FeedSnapshot(
        timestamp=int(today_815.timestamp()),
        stop_updates=[
            StopUpdate(
                trip_id="TRIP_OFF",
                route_id="R1",
                direction_id=0,
                stop_id="STOP_A",
                stop_sequence=1,
                realtime_dep_timestamp=int(today_815.timestamp()),
            )
        ],
    )

    with patch("collector.main.gtfs_rt.fetch", return_value=snap):
        collector._poll_cycle()

    assert ("TRIP_OFF", 1) not in collector._buffer
