import hashlib
import io
import logging
import shutil
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from . import config

logger = logging.getLogger(__name__)


def download_and_extract(force: bool = False) -> tuple[Path, bool]:
    """Download GTFS static zip if changed. Returns (extract_dir, changed)."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = config.DATA_DIR / "gtfs_static.zip"
    extract_dir = config.GTFS_STATIC_DIR

    logger.info("Downloading GTFS static from %s", config.GTFS_STATIC_URL)
    req = Request(config.GTFS_STATIC_URL)
    req.add_header("User-Agent", "Keleur/1.0 (transport data collector)")
    with urlopen(req, timeout=config.REQUEST_TIMEOUT_SECONDS) as resp:
        data = resp.read()

    new_hash = hashlib.sha256(data).hexdigest()

    # Check if content changed
    hash_file = config.DATA_DIR / "gtfs_static.sha256"
    if not force and hash_file.exists() and hash_file.read_text().strip() == new_hash:
        logger.info("GTFS static unchanged (hash %s…)", new_hash[:12])
        return extract_dir, False

    # Extract
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(extract_dir)

    # Save zip and hash
    zip_path.write_bytes(data)
    hash_file.write_text(new_hash)

    logger.info("GTFS static updated (hash %s…), extracted to %s", new_hash[:12], extract_dir)
    return extract_dir, True
