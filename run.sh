#!/usr/bin/env bash
# One-command demo: build the UI, set up Python, seed, serve everything
# on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -d .venv ]; then
  echo ">> creating virtualenv"
  "$PY" -m venv .venv
fi
./.venv/bin/pip install -q -r backend/requirements.txt

if [ ! -f frontend/dist/index.html ]; then
  echo ">> building frontend"
  npm --prefix frontend ci --silent
  npm --prefix frontend run build --silent
fi

echo ">> starting ChargeLens on http://localhost:8000 (first run seeds demo data)"
cd backend
exec ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
