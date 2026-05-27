"""Tests for grimsprout.core.changelog."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from grimsprout.core import changelog, md_parser


def _make_card(path: Path, body: str) -> None:
    md_parser.write(path, {"id": "x", "status": "alive"}, body)


def test_append_entry_inserts_at_top_of_changelog(tmp_path: Path) -> None:
    card = tmp_path / "card.md"
    _make_card(
        card,
        "## Журнал изменений (Changelog)\n\n- **2026-05-15**: Старая запись.\n",
    )

    changelog.append_entry(card, date(2026, 5, 18), "Новая запись.")

    _, body = md_parser.read(card)
    new_idx = body.index("Новая запись.")
    old_idx = body.index("Старая запись.")
    assert new_idx < old_idx
    assert "- **2026-05-18**: Новая запись." in body


def test_append_entry_with_photo_adds_image_line(tmp_path: Path) -> None:
    card = tmp_path / "card.md"
    _make_card(card, "## Журнал изменений (Changelog)\n\n")

    changelog.append_entry(card, date(2026, 5, 18), "С фото.", photo_rels=["images/x/abc.jpg"])

    _, body = md_parser.read(card)
    assert "- **2026-05-18**: С фото." in body
    assert "  ![](images/x/abc.jpg)" in body


def test_append_entry_with_multiple_photos(tmp_path: Path) -> None:
    card = tmp_path / "card.md"
    _make_card(card, "## Журнал изменений (Changelog)\n\n")

    changelog.append_entry(
        card,
        date(2026, 5, 27),
        "Три фото.",
        photo_rels=["images/p_1.jpg", "images/p_2.jpg", "images/p_3.jpg"],
    )

    _, body = md_parser.read(card)
    assert "- **2026-05-27**: Три фото." in body
    assert "  ![](images/p_1.jpg)" in body
    assert "  ![](images/p_2.jpg)" in body
    assert "  ![](images/p_3.jpg)" in body


def test_append_entry_creates_section_when_missing(tmp_path: Path) -> None:
    card = tmp_path / "card.md"
    _make_card(card, "# Заголовок\n\nТолько заметки, журнала нет.\n")

    changelog.append_entry(card, date(2026, 5, 18), "Первая запись.")

    _, body = md_parser.read(card)
    assert changelog.CHANGELOG_HEADING in body
    # Section appended at the end.
    assert body.index("Только заметки") < body.index(changelog.CHANGELOG_HEADING)
    assert "Первая запись." in body


def test_append_entry_leaves_file_parseable(tmp_path: Path) -> None:
    """The whole file must remain a valid frontmatter document after appending."""
    card = tmp_path / "card.md"
    _make_card(card, "## Журнал изменений (Changelog)\n\n- **2026-05-01**: x\n")

    changelog.append_entry(card, date(2026, 5, 18), "y")

    yaml_data, body = md_parser.read(card)
    assert yaml_data["id"] == "x"
    # Both entries are present and in the expected order.
    assert body.index("**2026-05-18**: y") < body.index("**2026-05-01**: x")


def test_append_entry_strips_input_whitespace(tmp_path: Path) -> None:
    card = tmp_path / "card.md"
    _make_card(card, "## Журнал изменений (Changelog)\n\n")

    changelog.append_entry(card, date(2026, 5, 18), "   текст с пробелами   ")

    _, body = md_parser.read(card)
    assert "- **2026-05-18**: текст с пробелами" in body
    assert "пробелами   \n" not in body
