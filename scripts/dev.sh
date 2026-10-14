#!/usr/bin/env bash
set -euo pipefail
RECRUITMENT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RECRUITMENT_ROOT"
if [[ ! -x backend/.venv/bin/python || ! -d frontend/node_modules ]]; then
  printf '%s\n' 'Install dependencies first: (cd backend && uv sync --frozen --extra dev) and (cd frontend && npm ci).'
  exit 1
fi
cleanup() {
  kill "$RECRUITMENT_API_PID" "$RECRUITMENT_WEB_PID" 2>/dev/null || true
  wait "$RECRUITMENT_API_PID" "$RECRUITMENT_WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
(cd backend && exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
RECRUITMENT_API_PID=$!
(cd frontend && export DEV_API_PROXY_TARGET=http://127.0.0.1:8000 && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort) &
RECRUITMENT_WEB_PID=$!
wait -n "$RECRUITMENT_API_PID" "$RECRUITMENT_WEB_PID"
