#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/logmaster/server"
SERVICE_FILE="logMasterServer.service"
SERVICE_NAME="logMasterServer"

cd "$SCRIPT_DIR"

# ── 1. Python venv ────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "[setup] Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
echo "[setup] Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# ── 2. .env file ─────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo "[setup] Copying .env.example → .env"
  cp .env.example .env
  echo "[setup] IMPORTANT: Edit .env and fill in the following before running:"
  echo "   AUTHENTIK_BASE_URL"
  echo "   AUTHENTIK_CLIENT_ID"
  echo "   AUTHENTIK_CLIENT_SECRET"
  echo "   LOG_API_SHARED_SECRET  (must match the daemon's value)"
  echo "   APP_SECRET_KEY"
else
  echo "[setup] .env already exists, skipping copy."
fi

# ── 3. Install systemd service (requires root) ───────────────────────────────
if [[ "${1:-}" == "--install-service" ]]; then
  if [[ $EUID -ne 0 ]]; then
    echo "[error] --install-service must be run as root (sudo ./setup.sh --install-service)"
    exit 1
  fi

  echo "[setup] Creating logmaster user/group (if not exists)..."
  id -u logmaster &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin logmaster

  echo "[setup] Copying files to $INSTALL_DIR..."
  mkdir -p "$INSTALL_DIR"
  rsync -a --exclude='.git' "$SCRIPT_DIR/" "$INSTALL_DIR/"
  chown -R logmaster:logmaster "$INSTALL_DIR"

  echo "[setup] Installing systemd service..."
  cp "$SCRIPT_DIR/$SERVICE_FILE" "/etc/systemd/system/$SERVICE_FILE"
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME"
  systemctl restart "$SERVICE_NAME"
  systemctl status "$SERVICE_NAME" --no-pager

  echo ""
  echo "[setup] Service installed and started."
  echo "  Logs: journalctl -u $SERVICE_NAME -f"
else
  echo ""
  echo "[setup] Done. To start the server manually:"
  echo "  source .venv/bin/activate && python server.py"
  echo ""
  echo "  To install as a systemd service (Linux only):"
  echo "  sudo ./setup.sh --install-service"
fi
