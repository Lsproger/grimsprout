"""Slug/id helpers: cyrillic → ASCII transliteration + auto-increment NN."""
from __future__ import annotations

from pathlib import Path


_TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(name: str) -> str:
    name = (name or "").strip().lower()
    out: list[str] = []
    for ch in name:
        if ch in _TRANSLIT_MAP:
            out.append(_TRANSLIT_MAP[ch])
        elif ch.isalnum() and ord(ch) < 128:
            out.append(ch)
        elif ch.isspace() or ch in "-_":
            out.append("_")
    slug = "".join(out)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "plant"


def next_slug(repo_path: Path, base: str) -> str:
    """Return base_NN with smallest free 2-digit suffix among repo .md files."""
    existing = {p.stem for p in repo_path.glob(f"{base}_*.md")}
    for i in range(1, 100):
        candidate = f"{base}_{i:02d}"
        if candidate not in existing:
            return candidate
    raise RuntimeError(f"no free slug slot for base={base}")
