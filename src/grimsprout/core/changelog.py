"""Changelog operations on plant cards.

The changelog section is identified by the heading
`## Журнал изменений (Changelog)`. New entries are inserted directly after the
heading (newest on top). Photo links are placed on the following indented line.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from grimsprout.core import md_parser

CHANGELOG_HEADING = "## Журнал изменений (Changelog)"


def _format_entry(on: date, text: str, photo_rel: str | None) -> str:
    text = text.strip()
    line = f"- **{on.isoformat()}**: {text}"
    if photo_rel:
        line += f"\n  ![]({photo_rel})"
    return line


def _split_lines_preserve(body: str) -> list[str]:
    return body.splitlines()


def append_entry(path: Path, on: date, text: str, photo_rel: str | None = None) -> None:
    """Insert a new changelog entry at the top of the list, preserving formatting."""
    yaml_data, body = md_parser.read(path)
    entry = _format_entry(on, text, photo_rel)
    lines = _split_lines_preserve(body)

    # Find the heading line
    heading_re = re.compile(
        r"^\s*##\s+\u0416\u0443\u0440\u043d\u0430\u043b\s+\u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0439\b"
    )
    heading_idx: int | None = None
    for i, ln in enumerate(lines):
        if heading_re.match(ln):
            heading_idx = i
            break

    if heading_idx is None:
        # Append heading + entry to the end of the body
        sep = "" if body.endswith("\n") else "\n"
        new_body = body + f"{sep}\n{CHANGELOG_HEADING}\n\n{entry}\n"
    else:
        # Insert entry right after the heading (skipping blank lines), as the new first item.
        insert_at = heading_idx + 1
        # Skip exactly one blank line if present (canonical style in trava cards).
        if insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        new_lines = lines[:insert_at] + [entry] + lines[insert_at:]
        new_body = "\n".join(new_lines)
        if body.endswith("\n"):
            new_body += "\n"

    md_parser.write(path, yaml_data, new_body)
