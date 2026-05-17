# 08 — Конфигурация

## 8.1. Источники
- `config/config.yaml` — основная конфигурация (не коммитим, есть `config.example.yaml`).
- `.env` — секреты (BOT_TOKEN, MONGO_URI).
- Переменные окружения переопределяют YAML.

## 8.2. Схема `config.yaml`
```yaml
telegram:
  token_env: "BOT_TOKEN"
  bootstrap_admin_tg_id: 123456789
  parse_mode: "HTML"

repository:
  path: "/opt/data/trava"
  images_dir: "images"
  template_file: "_template.md"
  git_remote: "origin"
  git_branch: "master"

mongo:
  uri_env: "MONGO_URI"
  database: "grimsprout"

llm:
  provider: "ollama"
  base_url: "http://localhost:11434"
  model: "llama3"
  temperature: 0.1
  timeout_sec: 30
  system_prompt_file: "config/prompts/system_undertaker.md"
  intent_schema_file: "config/prompts/intent_schema.json"

scheduling:
  timezone: "Europe/Warsaw"
  default_snooze_days: 1

logging:
  level: "INFO"
  json: false
```

## 8.3. `.env`
```
BOT_TOKEN=...
MONGO_URI=mongodb://localhost:27017
```

## 8.4. Загрузка
- `pydantic-settings` + кастомный YAML-loader.
- Все пути — абсолютные на этапе загрузки.
- Валидация: `repository.path` существует и является git-репо.
