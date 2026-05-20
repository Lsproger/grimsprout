# GrimSprout

[![CI](https://github.com/Lsproger/grimsprout/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Lsproger/grimsprout/actions/workflows/ci.yml)

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
Подробный план — в [docs/plan.md](docs/plan.md).

Текущее состояние: **Фаза 2 завершена** (Git-модуль + фото), следующая — Фаза 3 (LLM-интеграция).

## Тесты

```bash
pip install -r requirements-dev.txt

# Линт + тесты (одной командой):
make check

# Или по отдельности:
make lint
make test
make fmt          # авто-форматирование

# Полный прогон, включая интеграцию с Mongo:
docker run --rm -d -p 27017:27017 --name grimsprout-mongo mongo:7
MONGO_TEST_URI=mongodb://localhost:27017 pytest -q
```

Покрытие считается по `src/grimsprout` (см. `pyproject.toml`). В CI обязательное минимальное покрытие — 75%.

## CI и защита `master`

Каждый push и PR прогоняются через [.github/workflows/ci.yml](.github/workflows/ci.yml): джоба **lint** (ruff) и матричная **test** (Python 3.11 и 3.12) с поднятым контейнером `mongo:7`.

Чтобы master действительно сливался только на зелёных билдах, **один раз вручную** включи branch protection:

1. GitHub → репозиторий → **Settings → Branches → Add branch protection rule**.
2. Branch name pattern: `master`.
3. Включить:
   - **Require a pull request before merging** (без обязательного ревью, если работаешь один — на твой выбор).
   - **Require status checks to pass before merging** → **Require branches to be up to date** → выбрать обязательные чеки:
     - `Lint (ruff)`
     - `Test (Python 3.11)`
     - `Test (Python 3.12)`
   - **Require conversation resolution before merging** (опционально).
   - **Do not allow bypassing the above settings** (важно, иначе админ-пуш в master их обходит).
4. Отдельно отключить **Allow force pushes** и **Allow deletions** для `master`.

Эти чеки сделают кнопку *Merge pull request* неактивной, пока CI красный.
