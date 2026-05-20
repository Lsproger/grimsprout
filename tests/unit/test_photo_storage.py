"""Tests for grimsprout.core.photo_storage."""
from __future__ import annotations

from pathlib import Path

from grimsprout.core import photo_storage


def test_save_creates_file_in_images_dir(tmp_path: Path) -> None:
    data = b"\xff\xd8\xff\xe0fake-jpeg-data"
    rel = photo_storage.save(tmp_path, "images", "areca_01", data)

    assert rel.startswith("images/areca_01_")
    assert rel.endswith(".jpg")
    saved = tmp_path / rel
    assert saved.exists()
    assert saved.read_bytes() == data


def test_save_creates_images_dir_if_missing(tmp_path: Path) -> None:
    images_dir = tmp_path / "images"
    assert not images_dir.exists()

    photo_storage.save(tmp_path, "images", "test_01", b"data")

    assert images_dir.is_dir()


def test_save_returns_relative_path_with_forward_slash(tmp_path: Path) -> None:
    rel = photo_storage.save(tmp_path, "images", "palm_01", b"x")

    assert "/" in rel
    assert "\\" not in rel


def test_save_different_plant_ids_produce_different_files(tmp_path: Path) -> None:
    r1 = photo_storage.save(tmp_path, "images", "areca_01", b"a")
    r2 = photo_storage.save(tmp_path, "images", "calathea_01", b"b")

    assert r1 != r2
    assert "areca_01" in r1
    assert "calathea_01" in r2


def test_save_custom_images_subdir(tmp_path: Path) -> None:
    rel = photo_storage.save(tmp_path, "photos/raw", "fern_01", b"data")

    assert rel.startswith("photos/raw/fern_01_")
    assert (tmp_path / rel).exists()


def test_save_multiple_same_second_produces_unique_files(tmp_path: Path) -> None:
    """Album scenario: multiple saves within the same second get _2, _3 suffixes."""
    r1 = photo_storage.save(tmp_path, "images", "palm_01", b"photo1")
    r2 = photo_storage.save(tmp_path, "images", "palm_01", b"photo2")
    r3 = photo_storage.save(tmp_path, "images", "palm_01", b"photo3")

    assert r1 != r2 != r3
    assert (tmp_path / r1).read_bytes() == b"photo1"
    assert (tmp_path / r2).read_bytes() == b"photo2"
    assert (tmp_path / r3).read_bytes() == b"photo3"
    assert "_2.jpg" in r2
    assert "_3.jpg" in r3
