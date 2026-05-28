"""Unit tests for grimsprout.services.llm.tool_executor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grimsprout.services.llm import tool_executor


def _make_cfg(repo_path: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.repository.require_local_path.return_value = repo_path
    return cfg


def _make_user(tg_id: int = 42) -> MagicMock:
    user = MagicMock()
    user.tg_id = tg_id
    return user


# ---------------------------------------------------------------------------
# _resolve_plant_ids
# ---------------------------------------------------------------------------


def test_resolve_plant_ids_all(tmp_trava: Path) -> None:
    ids = tool_executor._resolve_plant_ids(["all"], tmp_trava)
    assert "areca_01" in ids
    assert "calathea_01" in ids


def test_resolve_plant_ids_exact(tmp_trava: Path) -> None:
    ids = tool_executor._resolve_plant_ids(["areca_01"], tmp_trava)
    assert ids == ["areca_01"]


def test_resolve_plant_ids_fuzzy(tmp_trava: Path) -> None:
    ids = tool_executor._resolve_plant_ids(["арека"], tmp_trava)
    assert "areca_01" in ids


def test_resolve_plant_ids_unknown_skipped(tmp_trava: Path) -> None:
    ids = tool_executor._resolve_plant_ids(["does_not_exist"], tmp_trava)
    assert ids == []


def test_resolve_plant_ids_empty(tmp_trava: Path) -> None:
    assert tool_executor._resolve_plant_ids([], tmp_trava) == []


# ---------------------------------------------------------------------------
# execute_tool — create_plant (no git, read-only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_create_plant(tmp_trava: Path) -> None:
    cfg = _make_cfg(tmp_trava)
    user = _make_user()
    db = AsyncMock()

    result = await tool_executor.execute_tool(
        "create_plant",
        {"common_name": "Плющ", "botanical_name": "Hedera helix"},
        cfg=cfg,
        db=db,
        user=user,
    )
    assert "/new" in result
    assert "Плющ" in result


# ---------------------------------------------------------------------------
# execute_tool — get_plant_details (no git, read-only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_get_plant_details_existing(tmp_trava: Path) -> None:
    cfg = _make_cfg(tmp_trava)
    user = _make_user()
    db = AsyncMock()

    result = await tool_executor.execute_tool(
        "get_plant_details",
        {"plant_id": "areca_01"},
        cfg=cfg,
        db=db,
        user=user,
    )
    assert "areca_01" in result
    assert "alive" in result


@pytest.mark.asyncio
async def test_execute_tool_get_plant_details_missing(tmp_trava: Path) -> None:
    cfg = _make_cfg(tmp_trava)
    user = _make_user()
    db = AsyncMock()

    result = await tool_executor.execute_tool(
        "get_plant_details",
        {"plant_id": "no_such_plant"},
        cfg=cfg,
        db=db,
        user=user,
    )
    assert "не найден" in result


# ---------------------------------------------------------------------------
# execute_tool — water (git write)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_water_single_plant(tmp_trava: Path, tmp_git_repo: Path) -> None:
    """water a single plant — expect YAML and changelog updated."""
    import shutil

    # Copy fixture into a git repo
    import git as gitlib

    shutil.copy(tmp_trava / "areca_01.md", tmp_git_repo / "areca_01.md")
    repo = gitlib.Repo(tmp_git_repo)
    repo.index.add(["areca_01.md"])
    repo.index.commit("init")

    cfg = _make_cfg(tmp_git_repo)
    user = _make_user()
    db = AsyncMock()

    with patch("grimsprout.services.llm.tool_executor.audit_svc.record", new_callable=AsyncMock):
        result = await tool_executor.execute_tool(
            "water",
            {"plant_ids": ["areca_01"]},
            cfg=cfg,
            db=db,
            user=user,
        )

    assert "areca_01" in result
    assert "✅" in result
    # Check YAML was updated
    from grimsprout.core import md_parser

    yaml_data, _ = md_parser.read(tmp_git_repo / "areca_01.md")
    from datetime import date

    assert yaml_data.get("last_watered_date") == date.today().isoformat()


# ---------------------------------------------------------------------------
# execute_tool — unknown tool name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_unknown(tmp_trava: Path) -> None:
    cfg = _make_cfg(tmp_trava)
    user = _make_user()
    db = AsyncMock()

    result = await tool_executor.execute_tool(
        "nonexistent_tool",
        {},
        cfg=cfg,
        db=db,
        user=user,
    )
    assert "Неизвестный" in result
