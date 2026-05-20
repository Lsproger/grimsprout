"""Tests for grimsprout.core.md_parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from grimsprout.core import md_parser


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_read_roundtrip_preserves_keys_and_body(tmp_path: Path) -> None:
    src = tmp_path / "card.md"
    _write(
        src,
        "---\nid: areca_01\ncommon_name: Пальма\ntags:\n  - a\n  - b\n---\n# Заголовок\n\nТекст.\n",
    )

    yaml_data, body = md_parser.read(src)

    assert yaml_data["id"] == "areca_01"
    assert yaml_data["common_name"] == "Пальма"
    assert yaml_data["tags"] == ["a", "b"]
    assert body.startswith("# Заголовок")
    assert "Текст." in body


def test_write_preserves_key_order(tmp_path: Path) -> None:
    dst = tmp_path / "out.md"
    md_parser.write(
        dst,
        {"id": "x", "status": "alive", "common_name": "n"},
        "# body\n",
    )

    text = dst.read_text(encoding="utf-8")
    # YAML keys must appear in the order they were inserted.
    id_pos = text.index("id:")
    status_pos = text.index("status:")
    name_pos = text.index("common_name:")
    assert id_pos < status_pos < name_pos


def test_write_unicode_is_not_escaped(tmp_path: Path) -> None:
    dst = tmp_path / "out.md"
    md_parser.write(dst, {"common_name": "Пальма"}, "Тело\n")
    text = dst.read_text(encoding="utf-8")
    assert "Пальма" in text
    assert "\\u" not in text


def test_update_yaml_updates_existing_inplace(tmp_path: Path) -> None:
    src = tmp_path / "card.md"
    _write(
        src,
        "---\nid: x\nstatus: alive\ncommon_name: old\n---\n# body\n",
    )

    md_parser.update_yaml(src, {"status": "dead"})

    yaml_data, body = md_parser.read(src)
    assert yaml_data == {"id": "x", "status": "dead", "common_name": "old"}
    assert "# body" in body
    # Existing key stayed in its place — id is still the first key.
    text = src.read_text(encoding="utf-8")
    assert text.index("id:") < text.index("status:") < text.index("common_name:")


def test_update_yaml_appends_new_keys_at_end(tmp_path: Path) -> None:
    src = tmp_path / "card.md"
    _write(src, "---\nid: x\nstatus: alive\n---\n# body\n")

    md_parser.update_yaml(src, {"last_repot_date": "2026-05-01"})

    text = src.read_text(encoding="utf-8")
    assert text.index("status:") < text.index("last_repot_date:")


def test_atomic_write_leaves_no_tmp(tmp_path: Path) -> None:
    dst = tmp_path / "out.md"
    md_parser.atomic_write_text(dst, "hello\n")
    assert dst.read_text(encoding="utf-8") == "hello\n"
    assert not (tmp_path / "out.md.tmp").exists()


def test_read_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        md_parser.read(tmp_path / "nope.md")
