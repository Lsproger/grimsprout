# ADR 0005 — Задел под MCP-сервер (вне MVP)

## Контекст
Может потребоваться выставить операции бота как MCP-инструменты, чтобы их вызывал внешний LLM-агент (или сам Copilot).

## Решение
Заранее изолируем pure-операции в `src/grimsprout/core/` и часть `services/` (`git_service`, `plant_repo`, `photo_storage`, `changelog`) — без зависимости от aiogram/MongoDB. Адаптер MCP появится отдельным модулем (не в MVP).

## Будущие tools (предварительно)
- `list_plants() -> [{id, common_name, status}]`
- `read_card(plant_id) -> {yaml, changelog_md}`
- `update_yaml(plant_id, patch)`
- `append_changelog(plant_id, text, photo_path?)`
- `save_photo(plant_id, bytes) -> rel_path`
- `git_commit(message, paths) -> sha`
- `git_push(remote, branch)`

## Последствия
- `core/*` пишется без обращений к Telegram/Mongo.
- Логика авторизации и аудита остаётся в `services/` и `bot/` — MCP получит свой слой авторизации.
