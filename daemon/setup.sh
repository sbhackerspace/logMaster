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
  echo "[setup] IMPORTANT: Edit .env and set LOG_API_SHARED_SECRET before running."
else
  echo "[setup] .env already exists, skipping copy."
fi

# ── 3. Verify journalctl is available ────────────────────────────────────────
if ! command -v journalctl &>/dev/null; then
  echo "[warn] journalctl not found. The daemon requires a systemd-based Linux host."
fi

echo ""
echo "[setup] Done. To start the daemon:"
echo "  source .venv/bin/activate"
echo "  python logMasterDaemon.py"
