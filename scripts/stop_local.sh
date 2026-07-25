#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.server.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No managed background server PID was found."
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped the local Frameclean server."
fi
rm -f "$PID_FILE"

