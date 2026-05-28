"""High-level plant repository operations on `trava/*.md` files."""

from __future__ import annotations

import re
from pathlib import Path

from rapidfuzz import fuzz, process

from grimsprout.core import md_parser

_CHANGELOG_ENTRY_RE = re.compile(r"^- \*\*(\d{4}-\d{2}-\d{2})\*\*:(.+)$")


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


def build_repo_summary(repo_path: Path, changelog_lines: int = 3) -> str:
    """Build a compact text summary of the plant collection for LLM system context.

    Each plant gets one header line (id, name, status, health) plus up to
    *changelog_lines* most-recent changelog entries from its .md body.

    Example output::

        Коллекция (2 растения):
        - calathea_01 "Калатея" alive h=7.5
          2026-05-15: Обрезка по нематодам...
          2026-05-10: Полив с микроэлементами.
        - areca_01 "Арека" alive h=8.0
          2026-05-20: Полив. Листья в норме.
    """
    plants = list_plants(repo_path)
    if not plants:
        return "Коллекция пуста."

    lines: list[str] = [
        f"Коллекция ({len(plants)} растени{'е' if len(plants) == 1 else 'я' if len(plants) < 5 else 'й'}):"
    ]  # noqa: E501
    for p in plants:
        health = f"h={p['health_score']}" if p["health_score"] is not None else "h=?"
        header = f'- {p["id"]} "{p["common_name"] or p["id"]}" {p["status"]} {health}'
        lines.append(header)

        # Extract recent changelog entries from markdown body
        card = read_card(repo_path, p["id"])
        if card:
            _, body = card
            entries = _extract_changelog_entries(body, changelog_lines)
            for entry in entries:
                lines.append(f"  {entry}")

    return "\n".join(lines)


def _extract_changelog_entries(body: str, max_entries: int) -> list[str]:
    """Extract the first *max_entries* changelog lines from markdown body."""
    entries: list[str] = []
    in_changelog = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("## ") and "changelog" in line.lower() or "журнал" in line.lower():
            in_changelog = True
            continue
        if in_changelog and line.startswith("## "):
            break  # next section
        if in_changelog and line.startswith("- **"):
            m = _CHANGELOG_ENTRY_RE.match(line)
            if m:
                date_str, text = m.group(1), m.group(2).strip()
                # Truncate long entries
                if len(text) > 120:
                    text = text[:117] + "..."
                entries.append(f"{date_str}: {text}")
                if len(entries) >= max_entries:
                    break
    return entries
