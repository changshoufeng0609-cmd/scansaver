#!/bin/bash
# One-command local development startup: backend + dashboard.
# Usage:  ./start.sh        (Ctrl-C stops both)
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "no .venv — run: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "dashboard: http://localhost:8000"
exec .venv/bin/uvicorn backend.main:app --reload --port 8000
