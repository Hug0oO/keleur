"""Registry of supported transit networks.

Each network has:
  - id: stable short identifier used as DB key and URL parameter
  - name: human-readable display name
  - operator: the actual transit operator
  - city: primary city
  - region: French region
  - timezone: IANA timezone (almost always Europe/Paris)
  - gtfs_rt_url: live TripUpdate feed (GTFS-Realtime protobuf)
  - gtfs_static_url: static GTFS zip
  - color: brand color for UI accents (CSS hex without #)
  - school_zone: French school holiday zone ("A", "B", or "C")
  - enabled: whether the collector should poll this network at startup

Adding a network = appending an entry. The collector spawns one polling
thread per enabled network and writes observations tagged with `network_id`.

URLs sourced from transport.data.gouv.fr and validated end-to-end:
each GTFS-RT URL must return parseable protobuf with TripUpdate entities,
and each static URL must return a zip containing stops/trips/stop_times.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Network:
    id: str
    name: str
    operator: str
    city: str
    region: str
    timezone: str
    gtfs_rt_url: str
    gtfs_static_url: str
    color: str
    school_zone: str  # French school holiday zone: "A", "B", or "C"
    enabled: bool = False


# ── Registry ──────────────────────────────────────────────────────────
#
# All entries below have been validated end-to-end:
#   - GTFS-RT feed returns >0 TripUpdate entities (parseable protobuf)
#   - Static GTFS zip downloads and contains stops/trips/stop_times.txt
#
# If a feed becomes unreachable, set enabled=False rather than removing —
# the API gracefully reports per-network health via /api/health.

NETWORKS: list[Network] = [
    Network(
        id="ilevia",
        name="Ilévia",
        operator="Keolis Lille",
        city="Lille",
        region="Hauts-de-France",
        timezone="Europe/Paris",
        gtfs_rt_url="https://proxy.transport.data.gouv.fr/resource/ilevia-lille-gtfs-rt",
        gtfs_static_url="https://media.ilevia.fr/opendata/gtfs.zip",
        color="e2001a",
        school_zone="B",
        enabled=True,
    ),
    Network(
        id="tbm",
        name="TBM",
        operator="Keolis Bordeaux",
        city="Bordeaux",
        region="Nouvelle-Aquitaine",
        timezone="Europe/Paris",
        gtfs_rt_url="https://bdx.mecatran.com/utw/ws/gtfsfeed/realtime/bordeaux?apiKey=opendata-bordeaux-metropole-flux-gtfs-rt",
        gtfs_static_url="https://bdx.mecatran.com/utw/ws/gtfsfeed/static/bordeaux?apiKey=opendata-bordeaux-metropole-flux-gtfs-rt",
        color="003d7c",
        school_zone="A",
        enabled=True,
    ),
    Network(
        id="rla",
        name="Lignes d'Azur",
        operator="Régie Ligne d'Azur",
        city="Nice",
        region="Provence-Alpes-Côte d'Azur",
        timezone="Europe/Paris",
        gtfs_rt_url="https://ara-api.enroute.mobi/rla/gtfs/trip-updates",
        gtfs_static_url="https://chouette.enroute.mobi/api/v1/datas/OpendataRLA/gtfs.zip",
        color="e30613",
        school_zone="B",
        enabled=True,
    ),
    Network(
        id="tisseo",
        name="Tisséo",
        operator="Tisséo Voyageurs",
        city="Toulouse",
        region="Occitanie",
        timezone="Europe/Paris",
        gtfs_rt_url="https://api.tisseo.fr/opendata/gtfsrt/GtfsRt.pb",
        gtfs_static_url="https://data.toulouse-metropole.fr/explore/dataset/tisseo-gtfs/files/fc1dda89077cf37e4f7521760e0ef4e9/download/",
        color="00a3e0",
        school_zone="C",
        enabled=True,
    ),
    Network(
        id="star",
        name="STAR",
        operator="Keolis Rennes",
        city="Rennes",
        region="Bretagne",
        timezone="Europe/Paris",
        gtfs_rt_url="https://proxy.transport.data.gouv.fr/resource/star-rennes-integration-gtfs-rt-trip-update",
        gtfs_static_url="https://eu.ftp.opendatasoft.com/star/gtfs/GTFS_STAR_BUS_METRO_EN_COURS.zip",
        color="d40f14",
        school_zone="B",
        enabled=True,
    ),
    Network(
        id="tam",
        name="TaM",
        operator="TaM Montpellier",
        city="Montpellier",
        region="Occitanie",
        timezone="Europe/Paris",
        gtfs_rt_url="https://data.montpellier3m.fr/GTFS/Urbain/TripUpdate.pb",
        gtfs_static_url="https://data.montpellier3m.fr/sites/default/files/ressources/TAM_MMM_GTFS.zip",
        color="e6007e",
        school_zone="C",
        enabled=True,
    ),
    Network(
        id="mistral",
        name="Mistral",
        operator="RD Toulon Provence Méditerranée",
        city="Toulon",
        region="Provence-Alpes-Côte d'Azur",
        timezone="Europe/Paris",
        gtfs_rt_url="https://feed-rdtpm-toulon.ratpdev.com/TripUpdate/GTFS-RT",
        gtfs_static_url="https://s3.eu-west-1.amazonaws.com/files.orchestra.ratpdev.com/networks/rd-toulon/exports/gtfs-complet.zip",
        color="0066b3",
        school_zone="B",
        enabled=True,
    ),
    Network(
        id="stas",
        name="STAS",
        operator="Transdev Saint-Étienne",
        city="Saint-Étienne",
        region="Auvergne-Rhône-Alpes",
        timezone="Europe/Paris",
        gtfs_rt_url="https://api.saint-etienne-metropole.fr/stas/api/horraires_tc/GTFS-RT.pb",
        gtfs_static_url="https://api.saint-etienne-metropole.fr/stas/api/horraires_tc/GTFS.aspx",
        color="00a651",
        school_zone="A",
        enabled=True,
    ),
    Network(
        id="astuce",
        name="Astuce",
        operator="Transdev Rouen",
        city="Rouen",
        region="Normandie",
        timezone="Europe/Paris",
        gtfs_rt_url="https://gtfs.bus-tracker.fr/gtfs-rt/tcar/trip-updates",
        gtfs_static_url="https://api.mrn.cityway.fr/dataflow/offre-tc/download?provider=ASTUCE&dataFormat=gtfs&dataProfil=ASTUCE",
        color="ed1c24",
        school_zone="B",
        enabled=False,  # RT feed uses different trip_ids than static GTFS
    ),
    Network(
        id="citura",
        name="Citura",
        operator="Transdev Reims",
        city="Reims",
        region="Grand Est",
        timezone="Europe/Paris",
        gtfs_rt_url="https://proxy.transport.data.gouv.fr/resource/fluo-citura-reims-gtfs-rt",
        gtfs_static_url="https://api.grandest2.cityway.fr/exs/GTFS?Key=OPENDATA&OperatorCode=REI",
        color="ffcc00",
        school_zone="B",
        enabled=True,
    ),
]

_BY_ID = {n.id: n for n in NETWORKS}


def get(network_id: str) -> Network | None:
    return _BY_ID.get(network_id)


def all_networks() -> list[Network]:
    return list(NETWORKS)


def enabled_networks() -> list[Network]:
    return [n for n in NETWORKS if n.enabled]


def default_network() -> Network:
    """Return the first enabled network, used as fallback when none specified."""
    enabled = enabled_networks()
    if enabled:
        return enabled[0]
    return NETWORKS[0]
