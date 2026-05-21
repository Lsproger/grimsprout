#!/usr/bin/env bash
# First-time server setup for GrimSprout on LXC.
# Run as root on the target host.
set -euo pipefail

INSTALL_DIR="/opt/grimsprout"
COMPOSE_URL="https://raw.githubusercontent.com/Lsproger/grimsprout/master/deploy/docker-compose.prod.yaml"

echo "=== GrimSprout server setup ==="

# 1. Create directories
mkdir -p "$INSTALL_DIR/config"
echo "[✓] Created $INSTALL_DIR/config"

# 2. Download production compose
curl -fsSL "$COMPOSE_URL" -o "$INSTALL_DIR/docker-compose.yaml"
echo "[✓] Downloaded docker-compose.yaml"

# 3. Prompt for config
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  cat > "$INSTALL_DIR/.env" <<'EOF'
BOT_TOKEN=
MONGO_URI=mongodb://mongo:27017
GIT_HTTPS_TOKEN=
GITHUB_TOKEN=
EOF
  echo "[!] Created $INSTALL_DIR/.env — fill in BOT_TOKEN and tokens"
else
  echo "[✓] .env already exists, skipping"
fi

if [[ ! -f "$INSTALL_DIR/config/config.yaml" ]]; then
  echo "[!] Copy your config.yaml to $INSTALL_DIR/config/config.yaml"
  echo "    Template: https://github.com/Lsproger/grimsprout/blob/master/config/config.example.yaml"
else
  echo "[✓] config.yaml already exists"
fi

# 4. Docker login to GHCR
echo ""
echo "=== Docker login to GHCR ==="
echo "You need a GitHub PAT with 'read:packages' scope."
echo "Create one at: https://github.com/settings/tokens?type=beta"
echo ""
if [[ -z "${GH_USER:-}" ]]; then
  read -rp "GitHub username [lsproger]: " GH_USER </dev/tty
fi
GH_USER="${GH_USER:-lsproger}"
if [[ -z "${GH_TOKEN:-}" ]]; then
  read -rsp "GitHub PAT (read:packages): " GH_TOKEN </dev/tty
  echo ""
fi
echo "$GH_TOKEN" | docker login ghcr.io -u "$GH_USER" --password-stdin
echo "[✓] Logged in to ghcr.io"

# 5. Start services
echo ""
echo "=== Starting services ==="
cd "$INSTALL_DIR"
docker compose up -d
echo ""
echo "[✓] Done! Check with:"
echo "    docker compose -f $INSTALL_DIR/docker-compose.yaml logs -f bot"
