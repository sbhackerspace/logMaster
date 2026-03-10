#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

echo ""
echo "[setup] Done. To start the server:"
echo "  source .venv/bin/activate"
echo "  python logMasterServer.py"
