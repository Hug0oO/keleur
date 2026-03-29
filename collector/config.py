import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DB_PATH = DATA_DIR / "keleur.duckdb"
GTFS_STATIC_DIR = DATA_DIR / "gtfs_static"

# GTFS endpoints
GTFS_RT_URL = "https://proxy.transport.data.gouv.fr/resource/ilevia-lille-gtfs-rt"
GTFS_STATIC_URL = "https://media.ilevia.fr/opendata/gtfs.zip"

# Collector settings
POLL_INTERVAL_SECONDS = int(os.environ.get("KELEUR_POLL_INTERVAL", "30"))
STATIC_REFRESH_SECONDS = int(os.environ.get("KELEUR_STATIC_REFRESH", "86400"))  # 24h
SAFETY_FLUSH_SECONDS = int(os.environ.get("KELEUR_FLUSH_INTERVAL", "600"))  # 10 min

# Timezone
TIMEZONE = "Europe/Paris"

# Network
REQUEST_TIMEOUT_SECONDS = 15
