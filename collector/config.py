"""Global collector settings.

Network-specific settings (GTFS feed URLs, timezone, branding) live in
collector/networks.py. This file only holds infrastructure-level config
that applies to every network.
"""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "keleur.duckdb"
GTFS_STATIC_DIR = DATA_DIR / "gtfs_static"  # parent dir; per-network subdirs

# Collector loop settings
POLL_INTERVAL_SECONDS = int(os.environ.get("KELEUR_POLL_INTERVAL", "30"))
STATIC_REFRESH_SECONDS = int(os.environ.get("KELEUR_STATIC_REFRESH", "86400"))  # 24h
SAFETY_FLUSH_SECONDS = int(os.environ.get("KELEUR_FLUSH_INTERVAL", "600"))  # 10 min

# Network
REQUEST_TIMEOUT_SECONDS = 15

# Default fallback timezone (almost all French networks share this)
DEFAULT_TIMEZONE = "Europe/Paris"
