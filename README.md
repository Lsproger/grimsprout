# GrimSprout

Мрачный Telegram-агент для ухода за домашними растениями. Редактирует Markdown-карточки локального репозитория [`trava`](../trava), хранит фотографии, делает автокоммиты в Git и общается с пользователем через локальную LLM (Ollama). Push в remote — только вручную ролью `publisher`/`admin`.

## Документация
- [Обзор](docs/spec/01-overview.md)
- [Модель данных](docs/spec/02-data-model.md)
- [Сценарии бота](docs/spec/03-bot-flows.md)
- [LLM-контракт](docs/spec/04-llm-contract.md)
- [Git-конвейер](docs/spec/05-git-flow.md)
- [Расписания и регрессия](docs/spec/06-scheduling.md)
- [Роли и авторизация](docs/spec/07-roles-and-auth.md)
- [Конфигурация](docs/spec/08-config.md)
- ADR: [docs/adr/](docs/adr/)
- Исходное ТЗ: [tz.md](tz.md)

## Быстрый старт (локально)
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp config/config.example.yaml config/config.yaml      # отредактируй
cp .env.example .env                                   # положи BOT_TOKEN

# Mongo и Ollama должны быть запущены отдельно
python -m grimsprout
```

## Структура
```
src/grimsprout/   # код бота
  bot/            # aiogram handlers, middlewares, FSM
  core/           # чистые операции: md_parser, changelog, plant_repo, photo_storage, ids
  services/       # git, llm (ollama+intent), photo_analyzer, auth, scheduler, audit
  db/             # motor client + repositories + pydantic models
  utils/          # logging, errors, dates
config/           # config.yaml, prompts/
deploy/           # Dockerfile, docker-compose, LXC-инструкция
docs/             # spec/ + adr/
```

## Этапы реализации
План этапов — в [memories/session/plan.md] (Phase 1–6). Текущее состояние репозитория — каркас (Фаза 0): структура модулей, контракты, конфиг, без бизнес-логики.