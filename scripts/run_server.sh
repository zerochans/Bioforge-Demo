#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ -z "${PYTHON:-}" ]; then
  if [ -x "/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python" ]; then
    PYTHON="/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/python"
  else
    PYTHON="python3"
  fi
fi
HOST="${BIOFORGE_HOST:-0.0.0.0}"
PORT="${BIOFORGE_PORT:-8010}"
if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
  echo "ERROR: port $PORT is already in use. Stop the old server or set BIOFORGE_PORT." >&2
  ss -ltnp "sport = :$PORT" 2>/dev/null || true
  exit 1
fi
exec "$PYTHON" -m uvicorn backend.app_v3:app --host "$HOST" --port "$PORT"
