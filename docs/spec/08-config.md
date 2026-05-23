# 08 — Конфигурация

## 8.1. Источники
- `config/config.yaml` — основная конфигурация (не коммитим, есть `config.example.yaml`).
- `.env` — секреты (токены, URI).
- `GRIMSPROUT_ENV` — переменная окружения для выбора активного профиля.

## 8.2. Env-профили

`config.yaml` поддерживает именованные профили (`local`, `prod` и любые другие). Активный профиль задаётся верхнеуровневым ключом `env:` или переменной окружения `GRIMSPROUT_ENV` (она имеет приоритет над файлом).

```bash
# Переключение без правки файла:
GRIMSPROUT_ENV=prod python -m grimsprout
```

Механизм: загрузчик проходит по каждой секции. Если секция содержит под-ключ с именем активного профиля, его поля мержатся поверх «плоских» (общих) полей секции. Секции без под-ключа передаются без изменений — это обеспечивает полную обратную совместимость со старыми плоскими конфигами.

## 8.3. Схема `config.yaml`
```yaml
# Активный профиль. Переопределяется GRIMSPROUT_ENV.
env: local

telegram:
  bootstrap_admin_tg_id: 123456789  # общее поле
  parse_mode: "HTML"                 # общее поле
  local:
    token_env: "BOT_TOKEN_DEV"       # имя переменной в .env для dev-бота
  prod:
    token_env: "BOT_TOKEN"           # имя переменной в .env для prod-бота

repository:
  # Общие поля (одинаковы для всех профилей)
  images_dir: "images"
  template_file: "_template.md"
  git_remote: "origin"
  git_branch: "master"
  work_branch: "grimsprout/auto"
  clone_dir: "var/repo"
  local:
    path: "var/repo/trava"           # локальный checkout
    https_token_env: "GIT_HTTPS_TOKEN"
    github_token_env: "GITHUB_TOKEN"
  prod:
    path: "https://github.com/owner/trava.git"  # клонируется при старте
    https_token_env: "GIT_HTTPS_TOKEN"
    github_token_env: "GITHUB_TOKEN"

mongo:
  local:
    uri_env: "MONGO_URI"
    database: "grimsprout_dev"
  prod:
    uri_env: "MONGO_URI"
    database: "grimsprout"

llm:
  # Общие поля
  provider: "ollama"
  temperature: 0.1
  timeout_sec: 30
  system_prompt_file: "config/prompts/system_undertaker.md"
  intent_schema_file: "config/prompts/intent_schema.json"
  local:
    base_url: "http://localhost:11434"
    model: "llama3"
  prod:
    base_url: "http://ollama.yourdomain.com:11434"
    model: "llama3"

scheduling:
  timezone: "Europe/Warsaw"          # нет профилей — плоская секция
  default_snooze_days: 1

logging:
  local:
    level: "DEBUG"
    json: false
  prod:
    level: "INFO"
    json: false
```

## 8.4. `.env`
```
# dev-бот
BOT_TOKEN_DEV=...
# prod-бот
BOT_TOKEN=...
# MongoDB
MONGO_URI=mongodb://localhost:27017
```

В одном `.env` можно держать переменные для всех профилей — активный профиль определяет, какие имена читаются.

## 8.5. Загрузка
- Загрузчик: `config.load_config()` → `_resolve_env(raw)` → `AppConfig.model_validate(resolved)`.
- `_resolve_env` разрешает профиль и мержит поля перед Pydantic-валидацией; модели данных не знают о профилях.
- Все пути — абсолютные на этапе загрузки.
- Валидация: `repository.path` существует и является git-репо.
