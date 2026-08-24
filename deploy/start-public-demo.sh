#!/bin/sh
set -eu

/opt/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!

cleanup() {
  kill "$api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd /app/frontend
HOSTNAME=0.0.0.0 exec node server.js
