import logging
from dataclasses import dataclass
from urllib.request import Request, urlopen

from google.transit import gtfs_realtime_pb2

from . import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StopUpdate:
    trip_id: str
    route_id: str
    direction_id: int
    stop_id: str
    stop_sequence: int
    realtime_dep_timestamp: int  # POSIX timestamp


@dataclass(frozen=True, slots=True)
class FeedSnapshot:
    timestamp: int  # Feed-level POSIX timestamp
    stop_updates: list[StopUpdate]


def fetch() -> FeedSnapshot:
    """Fetch and parse GTFS-RT feed. Raises on network/parse errors."""
    req = Request(config.GTFS_RT_URL)
    req.add_header("User-Agent", "Keleur/1.0 (transport data collector)")

    with urlopen(req, timeout=config.REQUEST_TIMEOUT_SECONDS) as resp:
        data = resp.read()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)

    updates = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip_id = tu.trip.trip_id
        route_id = tu.trip.route_id
        direction_id = tu.trip.direction_id

        for stu in tu.stop_time_update:
            # Use departure time (arrival is not provided by Ilévia)
            if not stu.HasField("departure") or stu.departure.time == 0:
                continue
            updates.append(
                StopUpdate(
                    trip_id=trip_id,
                    route_id=route_id,
                    direction_id=direction_id,
                    stop_id=stu.stop_id,
                    stop_sequence=stu.stop_sequence,
                    realtime_dep_timestamp=stu.departure.time,
                )
            )

    logger.debug(
        "Fetched feed ts=%d: %d entities, %d stop_updates",
        feed.header.timestamp,
        len(feed.entity),
        len(updates),
    )
    return FeedSnapshot(timestamp=feed.header.timestamp, stop_updates=updates)
