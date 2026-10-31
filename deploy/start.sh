#!/bin/bash
# Runs the API (container-internal) and the public web server; exits if either stops,
# so the host restarts the whole container.
set -u
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 &
api=$!
( cd web && exec node node_modules/next/dist/bin/next start --port "${PORT:-10000}" ) &
web=$!
trap 'kill "$api" "$web" 2>/dev/null' TERM INT
wait -n "$api" "$web"
status=$?
kill "$api" "$web" 2>/dev/null
exit "$status"
