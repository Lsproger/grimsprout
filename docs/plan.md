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

## Фаза 3 — Интеграция LLM 🔜
- [ ] `ollama_client.py` — async chat через httpx
- [ ] `intent_parser.py` — парсинг JSON-интента из ответа LLM
- [ ] `llm_router.py` — handler свободного текста → LLM → действие
- [ ] System prompt (config/prompts/system_undertaker.md)
- [ ] Сопоставление сущностей из LLM с файлами растений

## Фаза 4 — Полировка и расширения
- [ ] `scheduler_service.py` — APScheduler, напоминания о поливе
- [ ] `/new` — FSM-создание новой карточки
- [ ] `/schedule`, `/snooze` — управление расписаниями
- [ ] PhotoAnalyzer (LLM vision для описания фото)
- [ ] Обработка edge-cases: LLM не вернула JSON, git lock timeout
- [ ] Фирменная «загробная» стилистика ответов
