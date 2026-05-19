"""Tests for grimsprout.core.plant_repo."""
from __future__ import annotations

from pathlib import Path

from grimsprout.core import plant_repo


def test_list_plants_skips_template_and_readme(tmp_trava: Path) -> None:
    plants = plant_repo.list_plants(tmp_trava)
    ids = {p["id"] for p in plants}

    assert "areca_01" in ids
    assert "calathea_01" in ids
    # Underscored and README files are excluded.
    assert "_template" not in ids
    assert not any(p["file"].name.lower().startswith("readme") for p in plants)


def test_list_plants_tolerates_broken_yaml(tmp_trava: Path) -> None:
    # Sanity: fixture really has a broken file.
    assert (tmp_trava / "broken_yaml.md").exists()
    plants = plant_repo.list_plants(tmp_trava)
    ids = {p["id"] for p in plants}
    # Broken file is silently skipped; healthy ones are still listed.
    assert "areca_01" in ids
    assert "calathea_01" in ids


def test_list_plants_returns_expected_fields(tmp_trava: Path) -> None:
    plants = plant_repo.list_plants(tmp_trava)
    areca = next(p for p in plants if p["id"] == "areca_01")
    assert areca["common_name"] == "Пальма Арека"
    assert areca["status"] == "alive"
    assert areca["health_score"] == 7.5


def test_find_exact_id(tmp_trava: Path) -> None:
    result = plant_repo.find(tmp_trava, "areca_01")
    assert result is not None
    assert result.name == "areca_01.md"


def test_find_fuzzy_by_common_name(tmp_trava: Path) -> None:
    # "Калатея" with a typo still matches via rapidfuzz.
    result = plant_repo.find(tmp_trava, "калатея")
    assert result is not None
    assert result.stem == "calathea_01"


def test_find_returns_none_for_unknown(tmp_trava: Path) -> None:
    assert plant_repo.find(tmp_trava, "nonexistent_plant") is None
    assert plant_repo.find(tmp_trava, "") is None
    assert plant_repo.find(tmp_trava, "   ") is None


def test_read_card_existing(tmp_trava: Path) -> None:
    result = plant_repo.read_card(tmp_trava, "areca_01")
    assert result is not None
    yaml_data, body = result
    assert yaml_data["id"] == "areca_01"
    assert "Пальма Арека" in body


def test_read_card_missing(tmp_trava: Path) -> None:
    assert plant_repo.read_card(tmp_trava, "no_such") is None
