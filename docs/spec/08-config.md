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
  # Either a local path or a git URL (git@host:owner/repo.git, https://..., ssh://...).
  # If a URL is given, the repo is cloned into clone_dir/<repo-name> on startup.
  path: "/opt/data/trava"
  images_dir: "images"
  template_file: "_template.md"
  git_remote: "origin"
  git_branch: "master"           # base branch; bot never writes to it directly
  work_branch: "grimsprout/auto"  # bot-only branch; all auto-commits land here
  clone_dir: "var/repo"           # relative to project root; used when path is a URL
  https_token_env: "GIT_HTTPS_TOKEN"  # env var for HTTPS clone/push auth
  github_token_env: "GITHUB_TOKEN"    # env var for /pr (GitHub API)

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
