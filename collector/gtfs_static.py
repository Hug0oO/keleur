import hashlib
import io
import logging
import shutil
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from . import config
from .networks import Network

logger = logging.getLogger(__name__)


def download_and_extract(network: Network, force: bool = False) -> tuple[Path, bool]:
    """Download a network's GTFS static zip if changed.

    Returns (extract_dir, changed). Each network gets its own subdirectory
    under data/gtfs_static/ so feeds don't clobber each other.
    """
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    network_data_dir = config.DATA_DIR / "gtfs" / network.id
    network_data_dir.mkdir(parents=True, exist_ok=True)

    zip_path = network_data_dir / "gtfs_static.zip"
    hash_file = network_data_dir / "gtfs_static.sha256"
    extract_dir = config.GTFS_STATIC_DIR / network.id

    logger.info("[%s] Downloading GTFS static from %s", network.id, network.gtfs_static_url)
    req = Request(network.gtfs_static_url)
    req.add_header("User-Agent", "Keleur/1.0 (transport data collector)")
    with urlopen(req, timeout=config.REQUEST_TIMEOUT_SECONDS) as resp:
        data = resp.read()

    new_hash = hashlib.sha256(data).hexdigest()

    # Check if content changed
    if not force and hash_file.exists() and hash_file.read_text().strip() == new_hash:
        logger.info("[%s] GTFS static unchanged (hash %s…)", network.id, new_hash[:12])
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

    logger.info(
        "[%s] GTFS static updated (hash %s…), extracted to %s",
        network.id,
        new_hash[:12],
        extract_dir,
    )
    return extract_dir, True
