# 03 — Сценарии работы бота

## 3.1. Команды

| Команда | Доступ | Описание |
|---|---|---|
| `/start`, `/help`, `/whoami` | все авторизованные | приветствие, справка, текущая роль |
| `/plants` | editor+ | inline-список растений → выбор контекста |
| `/water`, `/fertilize`, `/repot` | editor+ | прямое действие над текущим растением |
| `/new` | editor+ | создание новой карточки (FSM или быстрый ввод) |
| `/schedule <plant> <kind> <Nd>` | editor+ | создать/обновить расписание |
| `/schedules` | editor+ | список активных расписаний |
| `/snooze <schedule_id> <Nd>` | editor+ | отложить напоминание |
| `/push` | publisher, admin | `git push origin <branch>` |
| `/add_user`, `/set_role`, `/list_users` | admin | управление пользователями |

Свободный текст и фото вне команд направляются в `IntentRouter` → LLM.

## 3.2. Сценарий: наблюдение + фото

```mermaid
sequenceDiagram
    autonumber
    User->>Bot: фото + "Калатея сохнет, появились пятна"
    Bot->>Auth: проверка роли
    Auth-->>Bot: editor (ok)
    Bot->>LLM: text + system prompt
    LLM-->>Bot: JSON {target_file: calathea_01, action: observe, changelog_entry, ...}
    Bot->>PlantRepo: resolve(target_file)
    PlantRepo-->>Bot: путь файла
    Bot->>PhotoStorage: save(file_id, plant_id)
    PhotoStorage-->>Bot: images/calathea_01_<ts>.jpg
    Bot->>PlantRepo: append_changelog(text, photo_rel)
    Bot->>PlantRepo: update_yaml(health_delta, tags)
    Bot->>Git: add + commit("chore(auto): observe calathea_01")
    Git-->>Bot: commit_sha
    Bot->>Audit: log(action=observe)
    Bot-->>User: стилизованный отчёт
```

## 3.3. Сценарий: создание карточки (FSM)

```mermaid
sequenceDiagram
    autonumber
    User->>Bot: /new
    Bot-->>User: "Имя (common_name)?"
    User->>Bot: "Папоротник Нефролепис"
    Bot-->>User: "Латинское название?"
    User->>Bot: "Nephrolepis exaltata"
    Note over Bot: FSM проходит по полям _template.md, любое можно пропустить
    Bot->>PlantRepo: create(slug=paporotnik_02, fields)
    PlantRepo-->>Bot: file_path
    Bot->>Git: add + commit("chore(auto): create paporotnik_02")
    Bot-->>User: "Карточка paporotnik_02 высечена в склепе"
```

Быстрый путь: одним сообщением `создай папоротник нефролепис, куплен в Леруа` → LLM возвращает `action=create` + поля → бот показывает preview YAML → кнопки `Записать / Отмена`.

## 3.4. Сценарий: напоминание и регрессия

```mermaid
sequenceDiagram
    autonumber
    Scheduler->>Bot: due(schedule_id) — calathea_01 water
    Bot-->>User: "Калатея жаждет H₂O" [Полил|Отложить|Отменить|Регрессия]
    User->>Bot: "Регрессия"
    Bot-->>User: "Опиши, что видишь. Можно с фото."
    User->>Bot: "грунт ещё влажен" + фото
    Bot->>PhotoStorage: save
    Bot->>LLM: text + "контекст: регрессия по поливу"
    LLM-->>Bot: JSON {action: observe, reschedule_days: +2, changelog_entry, ...}
    Bot->>Schedules: shift(next_run_at += 2d)
    Bot->>PlantRepo: append_changelog
    Bot->>Git: add + commit("chore(auto): regression calathea_01")
    Bot-->>User: "Напоминание отложено. Записал в журнал."
```

## 3.5. Неавторизованный доступ
- Сообщение игнорируется (silent) либо ответ-заглушка «Доступ запрещён».
- Админу уходит уведомление: `tg_id`, `username`, текст первого сообщения.
- В `audit_log` пишется `action=access_denied`.

## 3.6. Обработка ошибок
- **LLM не вернула валидный JSON** → один retry с напоминанием формата; иначе ответ-заглушка и предложение использовать прямые команды.
- **Растение не найдено** → бот предлагает: создать новое (`/new`) или выбрать из списка.
- **Git: грязное состояние / конфликт** → коммит блокируется, пользователю стилизованное сообщение, в `audit_log` фиксируется ошибка.
- **Ollama недоступен** → стилизованный «склеп закрыт», прямые команды продолжают работать.
