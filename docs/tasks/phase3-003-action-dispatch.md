# Phase 3C: Action Dispatch from Intent

**Фаза**: 3
**Статус**: done
**Приоритет**: high
**Зависимости**: phase3-001, phase3-002
**Блокирует**: нет (но Phase 4 info/edit расширят dispatch)

## Описание

Реализовать dispatch-логику: из распарсенного `Intent` выполнить соответствующее действие над карточкой растения (update YAML, changelog, git commit, audit).

Это часть `llm_router.py`, но выделена в отдельный таск т.к. содержит бизнес-логику действий.

## Требования

### Dispatch по action

| action | Логика |
|--------|--------|
| `water` | `update_yaml({last_watered_date: today})` → changelog(`intent.changelog_entry`) → git commit → audit |
| `fertilize` | `update_yaml({last_fertilized_date: today})` → changelog → git commit → audit |
| `repot` | `update_yaml({last_repot_date: today})` → changelog → git commit → audit |
| `observe` | changelog(`intent.changelog_entry`) → apply health_delta → apply tags → git commit → audit |
| `create` | Reply: "Для создания карточки используй /new" (defer Phase 4) |
| `unknown` | Handled in phase3-002 (suggest commands) |

### Apply health_delta (если не None)
```python
current = yaml_data.get("health_score", 5.0)
new_score = max(1.0, min(10.0, current + intent.health_delta))
update_yaml(path, {"health_score": new_score})
```

### Apply tags (если tags_add или tags_remove не пустые)
```python
current_tags = yaml_data.get("tags", [])
new_tags = [t for t in current_tags if t not in intent.tags_remove]
for t in intent.tags_add:
    if t not in new_tags:
        new_tags.append(t)
update_yaml(path, {"tags": new_tags})
```

### Changelog entry
- Использовать `intent.changelog_entry` (сгенерирован LLM в стиле «гробовщика»)
- Если `changelog_entry` is None → не добавлять запись (но yaml-поля всё равно обновить)

### Git commit message
```
chore(auto): {action} {plant_id}

{intent.changelog_entry or action_text}
GrimSprout: tg_id={user.tg_id}, llm={cfg.llm.model}
```

### Ответ пользователю
```
✅ {plant_id}: {intent.changelog_entry}
Коммит: {sha[:10]}
```
Если был health_delta: добавить `❤️ Здоровье: {old} → {new}`
Если были tags: добавить `🏷 Теги: {new_tags}`

### Shared helper: вынести resolve logic
Вынести `_resolve_plant_id` из actions.py в общее место (или создать лёгкий аналог для LLM router):
```python
async def resolve_plant(
    repo_path: Path,
    db: AsyncIOMotorDatabase,
    tg_id: int,
    target_file: str | None,
) -> str | None:
```

## Критерии готовности
- [ ] water/fertilize/repot через LLM → обновляет date-поле + changelog + commit
- [ ] observe → changelog + health_delta + tags + commit
- [ ] create → reply с подсказкой /new
- [ ] health_delta корректно clamp'ится [1, 10]
- [ ] tags_add/tags_remove работают без перезаписи
- [ ] Commit message содержит action, plant_id, llm model
- [ ] Audit записывается с payload {action, plant_id, intent}
- [ ] DirtyRepoError → graceful message
- [ ] Тесты: mock git_service + plant_repo, verify yaml patch + commit

## Файлы
- `src/grimsprout/bot/handlers/llm_router.py` — dispatch section
- `src/grimsprout/core/plant_repo.py` — `read_card()`, `find()`
- `src/grimsprout/core/md_parser.py` — `update_yaml()`
- `src/grimsprout/core/changelog.py` — `append_entry()`
- `src/grimsprout/services/git_service.py` — `add()`, `commit()`
- `src/grimsprout/services/audit.py` — `record()`
- `tests/unit/test_llm_router.py` — dispatch tests

## Заметки

### Пример полного flow
```
User: "Калатея подсыхает, кончики коричневые, влажность надо поднять"

LLM returns:
{
  "target_file": "calathea_01",
  "action": "observe",
  "health_delta": -1,
  "tags_add": ["сухость"],
  "tags_remove": [],
  "changelog_entry": "Зафиксировано усыхание кончиков — симптом низкой влажности. Рекомендуется увлажнитель.",
  "needs_photo": false,
  "confidence": 0.9,
  "clarification": null,
  "create_fields": null,
  "reschedule_days": null
}

Bot applies:
1. changelog.append_entry(path, today, "Зафиксировано усыхание...")
2. health_score: 7.5 → 6.5
3. tags: [..., "сухость"]
4. git add + commit
5. Reply: "✅ calathea_01: Зафиксировано усыхание кончиков...
   ❤️ Здоровье: 7.5 → 6.5
   🏷 Теги: [..., сухость]
   Коммит: abc123def0"
```

### Будущее расширение (Phase 4)
- `action: info` → вызов форматтера из phase4-002
- `action: edit` → вызов patch-логики из phase4-003
- Добавить эти actions в `intent_parser.Action` literal и `intent_schema.json`
