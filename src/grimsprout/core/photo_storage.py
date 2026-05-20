"""Photo storage: save Telegram photo bytes to <repo>/images/<plant_id>_<ts>.jpg."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def save(repo_path: Path, images_dir: str, plant_id: str, data: bytes) -> str:
    """Save photo bytes and return the repo-relative path (e.g. images/areca_01_20260520_143012.jpg)."""
    images_path = repo_path / images_dir
    images_path.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"{plant_id}_{ts}.jpg"
    dest = images_path / filename

    # Handle multiple photos within the same second (e.g. album)
    seq = 1
    while dest.exists():
        seq += 1
        filename = f"{plant_id}_{ts}_{seq}.jpg"
        dest = images_path / filename

    dest.write_bytes(data)

    return f"{images_dir}/{filename}"
