# Phase 3E: confirm_commits gate для LLM-роутера

**Фаза**: 3
**Статус**: done
**Приоритет**: high
**Зависимости**: phase3-003, phase2 (commit confirmation)

## Описание

`llm_router._apply_intent()` содержит собственный `git_service.commit()` напрямую — минуя флаг `cfg.repository.confirm_commits`, который был реализован для прямых команд (`/water`, `/fertilize`, `/repot`).

Это значит: даже при `confirm_commits: true` в конфиге, коммит от LLM прилетает **без подтверждения**. Именно это было на скриншоте (auto-commit `last_watered_date` пришёл из LLM-пути).

## Решение

### Вариант A — Reuse `_execute_action` из actions.py (предпочтительный)

Вынести `_execute_action` и `_compute_action` из `bot/handlers/actions.py` в `services/action_executor.py` (или аналогичный модуль), чтобы оба handler-а (прямые команды и LLM) использовали один код.

LLM-путь отличается тем, что применяет `health_delta`, `tags`, и пишет произвольный `changelog_entry` — поэтому либо:
- Расширить `ActionPayload` для LLM-специфичных полей (`health_delta`, `tags_add`, `tags_remove`, `changelog_entry`), или
- Оставить `_apply_intent` как есть, но добавить confirmation gate по аналогии с actions.py.

### Вариант B — Inline gate в `handle_free_text` (быстрее)

Аналогично actions.py: если `cfg.repository.confirm_commits` and action is mutating:
1. Сохранить `intent` + `plant_id` в FSM data (`ActionConfirmFSM.waiting`)
2. Показать preview с `confirm_keyboard()`
3. На подтверждение — вызвать `_apply_intent`

Preview-сообщение для LLM-пути:
```
⏳ Подтвердить?
🌿 Растение: <code>{plant_id}</code>
🤖 Действие: {intent.action} (LLM, confidence={intent.confidence:.0%})
📋 {intent.changelog_entry}
📅 Дата: <code>{today}</code>
```

**Мутирующие действия:** `water`, `fertilize`, `repot`, `observe` (если есть changelog_entry или health_delta).  
**Немутирующие** (gate не нужен): `query`, `unknown`, `create`.

### Рекомендация

Начать с **Варианта B** (быстрее, изолировано). Рефакторинг в services/ сделать позже как tech-debt таск.

## Критерии готовности
- [ ] При `confirm_commits: true` LLM-мутирующие действия показывают preview + кнопки до коммита
- [ ] При `confirm_commits: false` поведение не меняется (регрессия)
- [ ] Отмена через ❌ не коммитит ничего
- [ ] FSM state корректно очищается при подтверждении и отмене
- [ ] `make check` зелёный

## Заметки
- Таск `phase3-004` (action=query) должен быть реализован параллельно или раньше, иначе "query"-запросы тоже будут показывать confirmation dialog
- Confidence 0.9 для "observe" при запросе "какие у меня растения?" → confirmation dialog не поможет если action неверный; оба таска нужны
