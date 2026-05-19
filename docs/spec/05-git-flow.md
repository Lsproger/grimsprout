# 05 — Git-конвейер

## 5.0. Рабочая ветка и источник репозитория
- `repository.path` принимает либо локальный путь, либо git URL (SSH/HTTPS).
  URL клонируется в `clone_dir/<repo-name>` (по умолчанию `var/repo/`).
- Бот пишет только в `repository.work_branch` (по умолчанию `grimsprout/auto`).
  Базовая ветка `git_branch` для бота — read-only. См. ADR-0006.
- На старте `repo_bootstrap.ensure_workdir`:
  1. Локальный путь — проверяется, что это git-репо.
  2. URL и клона нет — выполняется `git clone` (без fetch/pull потом).
  3. Создаётся/чекаутится `work_branch` от `origin/<git_branch>`.

## 5.1. Операции
- `add(paths)` — добавление конкретных путей (без `add .`).
- `commit(message)` — выполняется только если рабочее дерево чистое, кроме целевых путей.
- `push(remote, branch)` — отдельная команда `/push`, доступна только `publisher`/`admin`. Всегда пушит `work_branch`.

## 5.2. Сообщения коммитов
Формат:
```
chore(auto): <action> <plant_id>

<changelog_entry, если есть>
GrimSprout: tg_id=<id>
```
Где `<action>` ∈ `water|fertilize|repot|observe|create|regression|schedule`.

## 5.3. Проверки перед коммитом
1. Репозиторий открывается из `repository.path` (`config.yaml`).
2. Если есть unmerged-пути / detached HEAD — коммит блокируется, ошибка эскалируется пользователю и в `audit_log`.
3. Lock-файл `.git/index.lock` — ждать до 2 секунд, потом ошибка.
4. Если в индекс попали посторонние файлы — коммит блокируется, требуется ручное вмешательство.

## 5.4. Push и PR
- `push` использует remote из конфига, ветка — всегда `work_branch`.
- Аутентификация определяется схемой URL:
  - SSH (`git@...`, `ssh://...`) — ssh-agent / `~/.ssh/config` хоста.
  - HTTPS — токен из `$GIT_HTTPS_TOKEN` (имя env-переменной настраиваемый).
    Токен используется только на клоне; в `.git/config` не сохраняется.
- Ошибки push (rejected, auth) — стилизованный ответ + запись в `audit_log`.
- `/pr` открывает GitHub Pull Request из `work_branch` в `git_branch`,
  используя токен из `$GITHUB_TOKEN`. Команда идемпотентна — если такой
  PR уже открыт, возвращается его URL.
- Слияние PR в базовую ветку — только вручную / CI. Бот не мержит и не делает force-push.

## 5.5. Совместная работа с пользователем
- Если пользователь параллельно правит файлы — бот не делает `reset/checkout`. Только `add` своих путей.
- При обнаружении конфликта или dirty-состояния бот ничего не правит и сообщает в чат.
