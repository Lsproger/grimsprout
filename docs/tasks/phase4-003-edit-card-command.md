# Команда `/edit` — редактирование полей карточки растения

**Фаза**: 4
**Статус**: backlog
**Приоритет**: high
**Зависимости**: нет (md_parser.update_yaml уже реализован)

## Описание

Пользователь хочет менять произвольные поля карточки растения через Telegram — без необходимости вручную править markdown-файл и делать коммит.

Сейчас бот умеет обновлять только три date-поля через `/water`, `/fertilize`, `/repot`. Все остальные метаданные (горшок, здоровье, теги, статус, описание) можно изменить только через git напрямую.

**Зачем**: Без этой фичи пользователь вынужден SSH на сервер / правит файл в git для простых вещей вроде «пересадил в горшок 21 см» или «здоровье теперь 9».

**Кто**: editor+

**Что**: Команда `/edit <поле> <значение>` или интерактивный режим (inline-кнопки с выбором поля).

## Сценарии использования

### 1. Inline-режим: `/edit` без аргументов
```
User: /edit
Bot: ✏️ Редактирование: areca_01
     Выбери поле:
     [Горшок] [Здоровье] [Статус] [Теги] [Заметки] [Другое…]

User: нажимает [Горшок]
Bot: 🏺 Текущее: 17 см, plastic
     Введи новый размер (см):
User: 21
Bot: Тип горшка? [plastic] [terracotta] [ceramic] [self-watering]
User: нажимает [terracotta]
Bot: ✅ areca_01: pot_size_cm=21, pot_type=terracotta
     Коммит: abc123def0
```

### 2. Быстрый режим: `/edit поле значение`
```
User: /edit health_score 9
Bot: ✅ areca_01: health_score = 9
     Коммит: abc123def0

User: /edit status dead
Bot: ✅ areca_01: status = dead ☠️
     Коммит: abc123def0

User: /edit tags +вредители -требуется_пересадка
Bot: ✅ areca_01: tags = [пальма, после_обрезки, вредители]
     Коммит: abc123def0
```

### 3. Через LLM (Фаза 3)
```
User: "Пересадил ареку в керамику 21 см"
LLM → intent: {action: edit, target: areca_01, patch: {pot_size_cm: 21, pot_type: ceramic}}
→ тот же apply-патч → коммит
```

## Редактируемые поля

| Поле | Тип | Валидация | Пример |
|------|-----|-----------|--------|
| `status` | enum | alive, dead, sold, gifted | `/edit status dead` |
| `common_name` | str | не пусто | `/edit common_name "Арека Пальма"` |
| `botanical_name` | str | — | `/edit botanical_name "Dypsis lutescens"` |
| `pot_size_cm` | int | 1–100 | `/edit pot_size_cm 21` |
| `pot_type` | enum | plastic, terracotta, ceramic, self-watering | `/edit pot_type ceramic` |
| `health_score` | float | 1.0–10.0 | `/edit health_score 9` |
| `tags` | list | +tag / -tag синтаксис | `/edit tags +вредители -пальма` |
| `light_req` | str | — | `/edit light_req "полутень"` |
| `moisture_req` | str | — | — |
| `humidity_req` | int | 0–100 | `/edit humidity_req 70` |
| `soil_type` | str | — | — |
| `age_group` | enum | seedling, juvenile, adult | `/edit age_group juvenile` |
| `purchase_location` | str | — | — |

## Требования

### Функциональные
- Работает с текущим растением из сессии или с аргументом (`/edit --plant calathea_01 ...`)
- Быстрый режим: `/edit <field> <value>` — однострочное обновление
- Интерактивный режим: `/edit` → inline-кнопки → ввод значения (FSM)
- Валидация значений по типу поля (enum, числовой диапазон)
- Теги: поддержка `+tag` (добавить) и `-tag` (удалить) — не перезатирать весь список
- После обновления: `update_yaml()` → changelog entry → `git add` → `git commit`
- Changelog entry: `✏️ Обновлено: {field} → {new_value}`

### Нефункциональные
- Минимальная роль: `editor`
- Атомарность: один коммит на одну правку (или batch если несколько полей за раз)
- Dirty repo guard (как в actions.py)

## Критерии готовности
- [ ] Handler `/edit` зарегистрирован в `bot/handlers/`
- [ ] Быстрый режим: `/edit <field> <value>` работает для всех полей из таблицы
- [ ] Интерактивный режим: FSM с inline-кнопками для выбора поля
- [ ] Валидация: enum-поля отклоняют невалидные значения, числа проверяются на диапазон
- [ ] Теги: `+tag`/`-tag` синтаксис работает корректно
- [ ] Каждое изменение → changelog entry + git commit
- [ ] Dirty repo → понятное сообщение пользователю
- [ ] Аудит-лог записывается

## Заметки

### Что уже готово
- `md_parser.update_yaml(path, patch)` — патчит произвольные YAML-поля
- `changelog.append_entry(path, date, text)` — добавляет запись
- `git_service.add()` + `git_service.commit()` — коммит
- `_resolve_plant_id()` в actions.py — резолв растения (переиспользовать/вынести в shared)
- Паттерн из actions.py: update → changelog → git → audit — переиспользовать

### Архитектурные решения
- `_resolve_plant_id()` вынести из `actions.py` в `bot/utils.py` или `core/` для переиспользования
- Валидация: простой dict `FIELD_VALIDATORS` с типами и допустимыми значениями
- FSM для интерактивного режима: `EditState.choosing_field` → `EditState.entering_value`
- Batch-edit (несколько полей): рассмотреть позже, начать с single-field

### Интеграция с LLM (Фаза 3)
В `intent_schema.json` — action `edit` с полем `patch: {}`. LLM сможет из фразы «горшок теперь 21 см керамика» сгенерировать `{pot_size_cm: 21, pot_type: "ceramic"}` → тот же handler.
