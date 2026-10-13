#!/usr/bin/env bash
set -euo pipefail
RECRUITMENT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Keep caches in a writable, ignored directory, including in managed cloud tasks.
export UV_CACHE_DIR="${UV_CACHE_DIR:-$RECRUITMENT_ROOT/.cache/uv}"
export npm_config_cache="${npm_config_cache:-$RECRUITMENT_ROOT/.cache/npm}"
cd "$RECRUITMENT_ROOT/backend"
uv sync --frozen --extra dev --extra e2e
cd "$RECRUITMENT_ROOT/frontend"
npm ci --no-audit --no-fund
