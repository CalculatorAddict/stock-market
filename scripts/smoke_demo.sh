#!/usr/bin/env bash
set -euo pipefail

# Minimal end-to-end smoke demo

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_FILE="/tmp/stock-smoke.log"
OUT_FILE="/tmp/stock-smoke.json"

# Refuse to run if another process already owns the demo port.
EXISTING_PID="$(lsof -t -iTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$EXISTING_PID" ]; then
  echo "Refusing to run smoke demo: port 8000 is already in use by PID $EXISTING_PID."
  echo "Stop that process first or run the demo on a different port."
  exit 1
fi

echo "Creating/updating virtual environment with uv..."
[ -d ".venv" ] || uv venv
source .venv/bin/activate
uv sync

echo "Running tests..."
if ! pytest -q; then
  echo "Tests failed (continuing smoke demo)"
fi

echo "Starting FastAPI server..."
uvicorn app:app --host 127.0.0.1 --port 8000 > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  rm -f "$OUT_FILE" "$LOG_FILE"
}
trap cleanup EXIT

echo "Waiting for server readiness..."
READY=false
for _ in {1..15}; do
  if curl -sSf http://127.0.0.1:8000/api/get_best?ticker=AAPL > "$OUT_FILE"; then
    READY=true
    break
  fi
  sleep 1
done

if [ "$READY" = false ]; then
  echo "Server failed to start. Logs:"
  cat "$LOG_FILE"
  exit 1
fi

echo "Smoke response (GET /api/get_best):"
cat "$OUT_FILE" | jq . 2>/dev/null || cat "$OUT_FILE"
echo
echo "Smoke demo completed."
