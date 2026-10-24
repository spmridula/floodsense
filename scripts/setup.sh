#!/usr/bin/env bash
# One-time setup (macOS/Linux). Requires Python 3.11+ and Node 20+.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --quiet --upgrade pip
backend/.venv/bin/python -m pip install --quiet -r backend/requirements.txt
[ -f .env ] || cp .env.example .env
(cd backend && .venv/bin/python -m app.cli init-db)
(cd frontend && npm ci)
echo "Setup complete. Run scripts/dev.sh"
