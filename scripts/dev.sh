#!/usr/bin/env bash
# Start the API and the Vite dev server for local development.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
export PATH="$VENV/bin:$PATH"

API_LOG="${TMPDIR:-/tmp}/proofpatch-api.log"
WEB_LOG="${TMPDIR:-/tmp}/proofpatch-web.log"

cleanup() {
  echo
  echo "[ProofPatch] shutting down..."
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null
  [ -n "${WEB_PID:-}" ] && kill "$WEB_PID" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "[ProofPatch] starting API on http://127.0.0.1:8000 (log: $API_LOG)"
"$VENV/bin/uvicorn" proofpatch_api.main:app --host 127.0.0.1 --port 8000 >"$API_LOG" 2>&1 &
API_PID=$!

if [ -d "$ROOT/apps/web/node_modules" ]; then
  echo "[ProofPatch] starting web dev server on http://127.0.0.1:5173 (log: $WEB_LOG)"
  (cd "$ROOT/apps/web" && npm run dev >"$WEB_LOG" 2>&1) &
  WEB_PID=$!
else
  echo "[ProofPatch] apps/web/node_modules missing - run 'npm install' in apps/web to serve the dashboard."
  echo "[ProofPatch] the built dashboard is still served by the API if apps/web/dist exists."
fi

echo
echo "API:      http://127.0.0.1:8000/health"
echo "Dashboard (dev): http://127.0.0.1:5173"
echo "Dashboard (prod): http://127.0.0.1:8000/"
echo
echo "Press Ctrl+C to stop."
wait
