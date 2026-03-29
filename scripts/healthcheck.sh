#!/usr/bin/env bash
# Health check: vérifie que le collecteur a écrit des données récemment.
# Exit 0 = OK, Exit 1 = problème.
# Usage: ./scripts/healthcheck.sh [max_age_minutes]

set -euo pipefail

MAX_AGE_MIN=${1:-10}
DB_PATH="${KELEUR_DB_PATH:-data/keleur.duckdb}"

if [ ! -f "$DB_PATH" ]; then
    echo "FAIL: database not found at $DB_PATH"
    exit 1
fi

LAST_OBS=$(python3 -c "
import duckdb
conn = duckdb.connect('$DB_PATH', read_only=True)
row = conn.execute('''
    SELECT max(observed_at) FROM delay_observations
''').fetchone()
if row[0] is None:
    print('NONE')
else:
    print(row[0].isoformat())
")

if [ "$LAST_OBS" = "NONE" ]; then
    echo "WARN: no observations yet"
    exit 1
fi

AGE_OK=$(python3 -c "
from datetime import datetime, timedelta, timezone
last = datetime.fromisoformat('$LAST_OBS')
if last.tzinfo is None:
    last = last.replace(tzinfo=timezone.utc)
age = datetime.now(timezone.utc) - last
print('OK' if age < timedelta(minutes=$MAX_AGE_MIN) else 'STALE')
")

if [ "$AGE_OK" = "OK" ]; then
    echo "OK: last observation at $LAST_OBS"
    exit 0
else
    echo "FAIL: last observation at $LAST_OBS (older than ${MAX_AGE_MIN}min)"
    exit 1
fi
