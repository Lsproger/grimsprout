"""Tests for grimsprout.core.ids."""

from __future__ import annotations

from pathlib import Path

import pytest

from grimsprout.core import ids


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Папоротник", "paporotnik"),
        ("Пальма Арека", "palma_areka"),
        ("Hydrangea  Macrophylla", "hydrangea_macrophylla"),
        ("  trim me  ", "trim_me"),
        ("dash-and_under", "dash_and_under"),
        ("Ёлка", "yolka"),
        ("Щука", "schuka"),
        ("", "plant"),
        ("***", "plant"),
        ("ЪЬ", "plant"),  # both translit to empty string
    ],
)
def test_slugify(raw: str, expected: str) -> None:
    assert ids.slugify(raw) == expected


def test_next_slug_starts_at_01(tmp_path: Path) -> None:
    assert ids.next_slug(tmp_path, "areca") == "areca_01"


def test_next_slug_picks_lowest_free(tmp_path: Path) -> None:
    (tmp_path / "areca_01.md").write_text("", encoding="utf-8")
    (tmp_path / "areca_02.md").write_text("", encoding="utf-8")
    (tmp_path / "areca_04.md").write_text("", encoding="utf-8")
    # Other bases must not interfere.
    (tmp_path / "calathea_01.md").write_text("", encoding="utf-8")

    assert ids.next_slug(tmp_path, "areca") == "areca_03"


def test_next_slug_raises_when_full(tmp_path: Path) -> None:
    for i in range(1, 100):
        (tmp_path / f"areca_{i:02d}.md").write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError):
        ids.next_slug(tmp_path, "areca")
