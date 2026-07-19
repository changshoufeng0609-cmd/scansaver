#!/bin/bash
# One-command dev/demo startup: backend + ngrok tunnel.
# Usage:  ./start.sh        (Ctrl-C stops both)
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "no .venv — run: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

trap 'kill 0' EXIT

.venv/bin/uvicorn backend.main:app --reload --port 8000 &
sleep 1
ngrok http --url=enlisted-edition-graveness.ngrok-free.dev 8000 --log stdout > /tmp/ngrok.log &
sleep 2

echo ""
echo "─────────────────────────────────────────────"
echo "  dashboard:  http://localhost:8000"
echo "  public:     https://enlisted-edition-graveness.ngrok-free.dev"
echo "  Ctrl-C to stop both."
echo "─────────────────────────────────────────────"
wait
