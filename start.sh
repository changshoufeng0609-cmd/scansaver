#!/bin/bash
# One-command dev/demo startup: backend + ngrok tunnel.
# Usage:  ./start.sh        (Ctrl-C stops both)
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "no .venv — run: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

trap 'kill 0' EXIT

# Reuse the reserved ngrok domain from .env (PUBLIC_BASE_URL) if set.
DOMAIN=$(grep -E "^PUBLIC_BASE_URL=" .env 2>/dev/null | sed -E 's|^PUBLIC_BASE_URL=https?://||; s|/$||')

.venv/bin/uvicorn backend.main:app --reload --port 8000 &
sleep 1
if [ -n "$DOMAIN" ]; then
  ngrok http --url="$DOMAIN" 8000 --log stdout > /tmp/ngrok.log &
else
  ngrok http 8000 --log stdout > /tmp/ngrok.log &
fi
sleep 2

echo ""
echo "─────────────────────────────────────────────"
echo "  dashboard:  http://localhost:8000"
echo "  public:     https://${DOMAIN:-\(random ngrok URL — see /tmp/ngrok.log\)}"
echo "  Ctrl-C to stop both."
echo "─────────────────────────────────────────────"
wait
