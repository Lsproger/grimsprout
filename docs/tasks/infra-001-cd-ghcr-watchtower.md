# CI/CD: автообновление через GHCR + Watchtower

**Фаза**: infra
**Статус**: done
**Приоритет**: high
**Зависимости**: нет

## Описание
Настроить автоматический деплой бота после мержа в `master`:
1. CI собирает Docker-образ и пушит в GitHub Container Registry (GHCR)
2. На LXC (Proxmox) запущен Watchtower, который периодически проверяет GHCR и подтягивает новый образ

Это позволит обновлять бота без SSH на сервер — достаточно замержить PR.

## Архитектура

```mermaid
graph LR
    A[Merge в master] --> B[GitHub Actions: build & push]
    B --> C[ghcr.io/lsproger/grimsprout:latest]
    C --> D[Watchtower на LXC]
    D --> E[docker compose up -d]
```

## Критерии готовности
- [x] В CI добавлена джоба `build-and-push` (только на `master`, после успешных lint+test)
- [x] Образ пушится в `ghcr.io/lsproger/grimsprout:latest` + тег с SHA коммита
- [x] `docker-compose.yaml` на сервере использует образ из GHCR вместо локального build
- [x] Watchtower запущен как сервис, проверяет обновления каждые 5 минут
- [x] Watchtower аутентифицирован в GHCR (PAT с `read:packages`)
- [x] Первый деплой через GHCR прошёл успешно

## Заметки

### CI workflow (добавить в `.github/workflows/ci.yml` или отдельный `cd.yml`):
```yaml
build-and-push:
  if: github.ref == 'refs/heads/master' && github.event_name == 'push'
  needs: [lint, test]
  runs-on: ubuntu-latest
  permissions:
    packages: write
  steps:
    - uses: actions/checkout@v6
    - uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    - uses: docker/build-push-action@v6
      with:
        context: .
        file: deploy/Dockerfile
        push: true
        tags: |
          ghcr.io/lsproger/grimsprout:latest
          ghcr.io/lsproger/grimsprout:${{ github.sha }}
```

### На LXC (одноразовая настройка):
```bash
# docker-compose.yaml на сервере — заменить build на image:
#   bot:
#     image: ghcr.io/lsproger/grimsprout:latest

# Watchtower:
docker run -d \
  --name watchtower \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e WATCHTOWER_POLL_INTERVAL=300 \
  -e WATCHTOWER_CLEANUP=true \
  containrrr/watchtower
```

### Аутентификация Watchtower в GHCR:
```bash
# ~/.docker/config.json (или через env)
echo "ghp_YOUR_TOKEN" | docker login ghcr.io -u lsproger --password-stdin
# Watchtower подхватит из /root/.docker/config.json если монтируешь:
# -v /root/.docker/config.json:/config.json
```

### Zero-downtime не нужен
Polling-бот — перезапуск занимает ~2 секунды, сообщения не теряются (Telegram буферизирует).
