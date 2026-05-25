# Этапы реализации GrimSprout

## Фаза 0 — Каркас ✅
- Структура модулей, контракты, конфиг
- MongoDB (motor) + pydantic models
- CI (GitHub Actions: lint + test matrix)

## Фаза 1 — Базовый фреймворк ✅
- aiogram 3.x бот, Dispatcher, polling
- Auth middleware (MongoDB user lookup, роли)
- Команды: `/start`, `/help`, `/whoami`, `/plants`, `/water`, `/fertilize`, `/repot`
- Inline-клавиатура выбора растения
- Сессии (`current_plant_id`)
- Аудит-лог всех действий
- Администрирование: `/add_user`, `/set_role`, `/list_users`

## Фаза 2 — Git-модуль ✅
- GitPython: `add`, `commit`, lock-wait, dirty-repo guard
- Автокоммит при `/water`, `/fertilize`, `/repot`
- `/push` — отправка work-ветки в remote
- `/pr` — создание GitHub PR (REST API, идемпотентно)
- Markdown-парсинг (YAML front matter + changelog)
- `repo_bootstrap` — clone/checkout work-branch при старте
- **Photo storage** — сохранение фото из Telegram в `images/`, дедупликация при альбомах
- Photo handler — download → save → changelog → git commit

## Инфраструктура ✅
- CI: lint (ruff) + test (pytest, coverage ≥75%) на push/PR
- CD: `build-and-push` джоба → `ghcr.io/lsproger/grimsprout:latest` + SHA-тег
- LXC (Proxmox): `docker-compose.prod.yaml` с bot + Watchtower
- Watchtower: авто-pull каждые 5 мин, аутентификация через `/root/.docker/config.json`
- Zero-downtime не требуется (polling-бот, Telegram буферизирует)

## Фаза 3 — Интеграция LLM ✅
- [x] `ollama_client.py` — async chat через httpx (`phase3-001`)
- [x] `llm_router.py` — handler свободного текста → LLM → ветвление (`phase3-002`)
- [x] Action dispatch — Intent → update YAML + changelog + git commit (`phase3-003`)
- [x] System prompt + schema (`config/prompts/`)
- [x] `intent_parser.py` — pydantic model + `parse()`
- [x] Сопоставление сущностей: fuzzy find + session fallback (`phase3-002`)
- [x] LLM query action — `/query` команда (`phase3-004`)
- [x] Confirm gate — запрос подтверждения перед мутацией (`phase3-005`)
- [x] Confidence threshold — порог уверенности LLM (`phase3-006`)

## Фаза 4 — Полировка и расширения 🔜
- [x] `/info` — просмотр карточки растения (YAML + последние changelog)
- [x] `/edit` — редактирование полей карточки (quick mode + interactive FSM, 12 полей)
- [x] `/new` — FSM-создание новой карточки
- [x] LLM performance stats — логирование `tokens_per_sec` / `eval_count` в INFO; флаг `llm.show_perf_stats` для вывода футера `⚡ N tok/s · M tok` в ответах бота
- [ ] Обработка edge-cases: LLM не вернула JSON, git lock timeout
- [ ] Фирменная «загробная» стилистика ответов

## Фаза 5 — Gemini Bridge (внешний агент → GrimSprout)
Пользователь ведёт глубокий анализ в Gemini (с доступом к репозиторию `trava`),
затем передаёт результат в бот для применения к карточкам / changelog / задачам.

- [ ] Принять структурированный вывод Gemini (JSON или Markdown) через Telegram-сообщение
- [ ] Разбор payload: определить тип операции (обновление карточки / запись в changelog / задача)
- [ ] Применить изменения через существующий Action dispatch (phase3-003)
- [ ] Подтверждение перед записью (через существующий confirm gate)
- [ ] Опционально: webhook / Telegram-пересылка как триггер (без Telegram-интеграции на стороне Gemini)

> **Зависимости:** Фаза 4 (команды `/edit`, `/info`)
> **Не входит в MVP**

## Фаза 6 — Планировщик напоминаний
- [ ] `scheduler_service.py` — APScheduler + MongoDB jobstore, напоминания о поливе/удобрении/пересадке
- [ ] `/schedule [plant_id] <kind> <interval_days>` — создать/обновить расписание
- [ ] `/snooze [plant_id] [kind]` — отложить на `default_snooze_days`

> **Зависимости:** Фаза 4 + Фаза 5 (Gemini Bridge)

## Фаза 7 — PhotoAnalyzer (post-MVP)
- [ ] LLM vision — описание фото растения по снимку
- [ ] Автоматическое добавление описания в changelog при загрузке фото
- [ ] Определение заболеваний / состояния листьев

> **Не входит в MVP**
