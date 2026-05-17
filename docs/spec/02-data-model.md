# 02 — Модель данных

## 2.1. YAML front matter карточки растения

Базовая схема — `_template.md` из репозитория `trava`. На уровне GrimSprout добавляем **только** одно поле: `last_watered_date`.

```yaml
---
id: string                     # уникальный slug, совпадает с именем файла без .md
status: alive|dead|sold|gifted
common_name: string
botanical_name: string
variety: string

# Таймлайны
purchase_date: YYYY-MM-DD | null
purchase_location: string
age_group: seedling|juvenile|adult

# Профайл ухода
light_req: string
moisture_req: string
humidity_req: int | null       # %
soil_type: string

# Текущее состояние
pot_size_cm: int | null
pot_type: plastic|terracotta|ceramic|self-watering
last_repot_date: YYYY-MM-DD | null
last_fertilized_date: YYYY-MM-DD | null
last_watered_date: YYYY-MM-DD | null    # <-- добавлено GrimSprout

# Метрики
health_score: 1..10
tags: [string]
---
```

Правила записи:
- Поля сохраняем в том же порядке, что в шаблоне; новое поле `last_watered_date` пишем рядом с `last_fertilized_date`.
- Запись атомарная: writer пишет во временный файл рядом и делает `os.replace`.
- Никогда не удаляем поля, которых "не знаем": сохраняем неизменными.

## 2.2. Changelog
Секция `## Журнал изменений (Changelog)` в теле документа. Формат записи:

```
- **YYYY-MM-DD**: текст события (в стиле гробовщика, на русском).
  ![](images/<plant_id>_<timestamp>.jpg)   # опционально, отдельной строкой с отступом
```

- Новые записи вставляются **сверху** списка.
- За один акт изменения — одна запись; вложенная картинка добавляется тем же блоком.

## 2.3. Имя файла и slug
- Имя файла: `<slug>.md`, где `slug` совпадает с `id` во front matter.
- Slug нового растения: транслит `common_name` (lowercase, `_`-разделитель, ASCII) + `_NN`, где `NN` — наименьшее свободное двузначное число среди уже существующих файлов с тем же базовым slug. Пример: `kalateya_01`, `kalateya_02`.

## 2.4. Фото
- Каталог: `<TRAVA_PATH>/images/`.
- Имя: `<plant_id>_<YYYYMMDDThhmmss>.jpg`.
- Сохранение — максимальное качество из Telegram (последний `PhotoSize`).
- Ссылка добавляется в changelog записью текущего действия.

## 2.5. MongoDB-коллекции

### `users`
```
{
  _id: ObjectId,
  tg_id: int,           # unique
  role: "admin"|"editor"|"publisher"|"viewer",
  display_name: string,
  added_by: int | null, # tg_id админа
  added_at: datetime
}
```

### `sessions`
```
{
  _id: ObjectId,
  tg_id: int,           # unique
  current_plant_id: string | null,
  updated_at: datetime
}
```

### `schedules`
```
{
  _id: ObjectId,
  plant_id: string,
  kind: "water"|"fertilize"|"repot",
  interval_days: int,
  next_run_at: datetime,
  owner_tg_id: int,
  active: bool,
  created_at: datetime,
  updated_at: datetime
}
```
Уникальный индекс: `(plant_id, kind, owner_tg_id)`.

### `audit_log`
```
{
  _id: ObjectId,
  ts: datetime,
  tg_id: int,
  action: string,       # access_denied, water, fertilize, repot, observe, create, push, schedule_*, ...
  payload: object,      # произвольные детали запроса
  file: string | null,  # затронутый .md
  commit_sha: string | null
}
```
Индексы: `ts` (desc), `tg_id`, `action`.

### APScheduler jobstore
- Использует ту же MongoDB, отдельная коллекция (`apscheduler_jobs`).
