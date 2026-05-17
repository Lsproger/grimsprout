"""High-level plant repository operations on `trava/*.md` files."""
from __future__ import annotations

from pathlib import Path

from rapidfuzz import fuzz, process

from grimsprout.core import md_parser


def _is_plant_file(path: Path) -> bool:
    name = path.name
    if not name.endswith(".md"):
        return False
    if name.startswith("_") or name.lower().startswith("readme"):
        return False
    return True


def list_plants(repo_path: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(repo_path.glob("*.md")):
        if not _is_plant_file(p):
            continue
        try:
            yaml_data, _ = md_parser.read(p)
        except Exception:
            continue
        out.append(
            {
                "id": yaml_data.get("id") or p.stem,
                "file": p,
                "common_name": yaml_data.get("common_name") or "",
                "status": yaml_data.get("status") or "",
                "health_score": yaml_data.get("health_score"),
            }
        )
    return out


def find(repo_path: Path, query: str) -> Path | None:
    q = (query or "").strip()
    if not q:
        return None
    candidates = list_plants(repo_path)
    # 1) exact id
    for c in candidates:
        if c["id"] == q:
            return c["file"]
    # 2) exact file stem
    for c in candidates:
        if c["file"].stem == q:
            return c["file"]
    # 3) fuzzy common_name (single best >= 80)
    names = {c["common_name"]: c["file"] for c in candidates if c["common_name"]}
    if names:
        match = process.extractOne(q, list(names.keys()), scorer=fuzz.WRatio)
        if match and match[1] >= 80:
            return names[match[0]]
    return None


def read_card(repo_path: Path, plant_id: str) -> tuple[dict, str] | None:
    path = repo_path / f"{plant_id}.md"
    if not path.exists():
        return None
    return md_parser.read(path)
