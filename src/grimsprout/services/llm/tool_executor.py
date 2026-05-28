"""Tool executor: dispatches LLM tool calls to actual plant-card operations.

This module replaces `_apply_intent()` from llm_router.py.
Each public function takes the tool arguments + execution context and returns
a human-readable result string (shown to the user or fed back to the LLM).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from grimsprout.config import AppConfig
from grimsprout.core import changelog, md_parser, plant_repo
from grimsprout.db.models import User
from grimsprout.services import audit as audit_svc
from grimsprout.services import git_service
from grimsprout.utils.errors import DirtyRepoError, GrimSproutError

_DATE_FIELDS: dict[str, str] = {
    "water": "last_watered_date",
    "fertilize": "last_fertilized_date",
    "repot": "last_repot_date",
}


async def execute_tool(
    name: str,
    args: dict,
    *,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
) -> str:
    """Dispatch a tool call by name and return a result string.

    Raises GrimSproutError / DirtyRepoError on failure — caller is responsible
    for catching and formatting the error message.
    """
    repo_path = cfg.repository.require_local_path()

    if name in ("water", "fertilize", "repot"):
        return await _apply_date_action(name, args, repo_path=repo_path, cfg=cfg, db=db, user=user)

    if name == "observe":
        return await _apply_observe(args, repo_path=repo_path, cfg=cfg, db=db, user=user)

    if name == "get_plant_details":
        return _get_plant_details(args, repo_path=repo_path)

    if name == "create_plant":
        return _create_plant_hint(args)

    logger.warning("execute_tool: unknown tool name={}", name)
    return f"Неизвестный инструмент: {name}"


# ---------------------------------------------------------------------------
# Internal handlers
# ---------------------------------------------------------------------------


async def _apply_date_action(
    action: str,
    args: dict,
    *,
    repo_path: Path,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
) -> str:
    """Handle water / fertilize / repot for one or more plants."""
    raw_ids: list[str] = args.get("plant_ids", [])
    plant_ids = _resolve_plant_ids(raw_ids, repo_path)

    if not plant_ids:
        return f"Растения не найдены для действия «{action}»."

    today = date.today()
    field = _DATE_FIELDS[action]
    results: list[str] = []

    for plant_id in plant_ids:
        path = repo_path / f"{plant_id}.md"
        if not path.exists():
            results.append(f"⚠️ <code>{plant_id}</code>: файл не найден")
            continue
        try:
            md_parser.update_yaml(path, {field: today.isoformat()})
            entry = _default_changelog_entry(action)
            changelog.append_entry(path, today, entry)
            git_service.add(repo_path, [path])
            sha = git_service.commit(
                repo_path,
                f"chore(auto): {action} {plant_id}\n\n{entry}\nGrimSprout: tg_id={user.tg_id}, tool={action}",
            )
            await audit_svc.record(
                db,
                tg_id=user.tg_id,
                action=f"llm:{action}",
                payload={"plant_id": plant_id},
                file=f"{plant_id}.md",
                commit_sha=sha,
            )
            results.append(f"✅ <code>{plant_id}</code> ({sha[:8]})")
        except DirtyRepoError:
            raise
        except GrimSproutError as exc:
            results.append(f"❌ <code>{plant_id}</code>: {exc}")

    header = f"<b>{action}</b> · {today.isoformat()}"
    return header + "\n" + "\n".join(results)


async def _apply_observe(
    args: dict,
    *,
    repo_path: Path,
    cfg: AppConfig,
    db: AsyncIOMotorDatabase,
    user: User,
) -> str:
    """Handle observe: write a free-form note to a single plant's changelog."""
    plant_id: str = args.get("plant_id", "")
    note: str = (args.get("note") or "Наблюдение зафиксировано.").strip()

    # Try fuzzy resolution
    resolved_path = plant_repo.find(repo_path, plant_id)
    if resolved_path is None:
        return f"Растение «{plant_id}» не найдено."
    plant_id = resolved_path.stem

    today = date.today()
    path = repo_path / f"{plant_id}.md"
    changelog.append_entry(path, today, note)
    git_service.add(repo_path, [path])
    sha = git_service.commit(
        repo_path,
        f"chore(auto): observe {plant_id}\n\n{note}\nGrimSprout: tg_id={user.tg_id}, tool=observe",
    )
    await audit_svc.record(
        db,
        tg_id=user.tg_id,
        action="llm:observe",
        payload={"plant_id": plant_id},
        file=f"{plant_id}.md",
        commit_sha=sha,
    )
    return f"✅ <code>{plant_id}</code>: {note}\nКоммит: <code>{sha[:8]}</code>"


def _get_plant_details(args: dict, *, repo_path: Path) -> str:
    """Return formatted plant card (YAML + recent changelog) as a string."""
    plant_id: str = args.get("plant_id", "")
    resolved_path = plant_repo.find(repo_path, plant_id)
    if resolved_path is None:
        return f"Растение «{plant_id}» не найдено."
    plant_id = resolved_path.stem

    card = plant_repo.read_card(repo_path, plant_id)
    if card is None:
        return f"Карточка «{plant_id}» не найдена."

    yaml_data, body = card
    lines: list[str] = [f"=== {plant_id} ==="]
    for key, val in yaml_data.items():
        lines.append(f"{key}: {val}")
    # Include raw body (changelog section)
    lines.append("")
    lines.append(body.strip())
    return "\n".join(lines)


def _create_plant_hint(args: dict) -> str:
    """Return a hint to use /new, pre-filling common_name."""
    common_name = args.get("common_name", "")
    botanical = args.get("botanical_name", "")
    hint = "Для создания карточки используй /new"
    if common_name:
        hint += f" — растение: «{common_name}»"
    if botanical:
        hint += f" ({botanical})"
    hint += "."
    return hint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_plant_ids(raw_ids: list[str], repo_path: Path) -> list[str]:
    """Expand [\"all\"] to every plant ID; validate others via fuzzy find."""
    if not raw_ids:
        return []
    if raw_ids == ["all"] or (len(raw_ids) == 1 and raw_ids[0].lower() == "all"):
        return [p["id"] for p in plant_repo.list_plants(repo_path)]

    resolved: list[str] = []
    for raw in raw_ids:
        path = plant_repo.find(repo_path, raw)
        if path:
            resolved.append(path.stem)
        else:
            logger.warning("_resolve_plant_ids: no match for '{}'", raw)
    return resolved


def _default_changelog_entry(action: str) -> str:
    defaults = {
        "water": "Влага дана. Корни получили своё — до следующего ритуала.",
        "fertilize": "Удобрение внесено. Питательный раствор принят.",
        "repot": "Пересадка выполнена. Новый субстрат, новый сосуд.",
    }
    return defaults.get(action, f"Действие: {action}.")
