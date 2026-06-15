#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
PORT="${PORT:-8080}"

mkdir -p "$DATA_DIR"

# Build the seed.db (deterministic) and copy it to state.db only if state.db is missing.
# This preserves user state across container restarts.
cd /app/backend
python -m app.seed.builder --ensure

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --log-level "${JP_LOG_LEVEL:-info}"
