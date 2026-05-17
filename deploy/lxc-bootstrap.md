# LXC bootstrap

Краткий чек-лист развёртывания в LXC-контейнере (Debian/Ubuntu):

1. Установить системные пакеты:
   ```bash
   apt-get update && apt-get install -y python3.11 python3.11-venv git ca-certificates
   ```
2. Установить MongoDB (либо запустить отдельным контейнером) и убедиться, что доступен по `MONGO_URI`.
3. Клонировать `grimsprout` и `trava` в `/opt/`:
   ```bash
   git clone <grimsprout-url> /opt/grimsprout
   git clone <trava-url> /opt/data/trava
   ```
4. Создать venv и установить зависимости:
   ```bash
   cd /opt/grimsprout
   python3.11 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
5. Скопировать `config/config.example.yaml` → `config/config.yaml`, заполнить.
6. Создать `.env` с `BOT_TOKEN` и `MONGO_URI`.
7. Установить Ollama на хосте/в соседнем контейнере и проверить:
   ```bash
   curl http://localhost:11434/api/tags
   ```
8. systemd-юнит (`/etc/systemd/system/grimsprout.service`):
   ```ini
   [Unit]
   Description=GrimSprout bot
   After=network-online.target
   [Service]
   WorkingDirectory=/opt/grimsprout
   EnvironmentFile=/opt/grimsprout/.env
   ExecStart=/opt/grimsprout/.venv/bin/python -m grimsprout
   Restart=always
   [Install]
   WantedBy=multi-user.target
   ```
9. `systemctl enable --now grimsprout`.
