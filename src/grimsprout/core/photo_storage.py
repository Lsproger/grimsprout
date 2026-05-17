"""Photo storage: save Telegram photo bytes to <repo>/images/<plant_id>_<ts>.jpg.

TODO(phase-2):
- save(repo_path, images_dir, plant_id, data: bytes) -> rel_path: str
"""
from __future__ import annotations

from pathlib import Path


def save(repo_path: Path, images_dir: str, plant_id: str, data: bytes) -> str:
    raise NotImplementedError("phase-2")
