#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python ]]; then
  echo "API environment is missing. Create .venv and install apps/api/requirements.txt." >&2
  exit 1
fi

if [[ ! -f apps/web/dist/index.html ]]; then
  npm run build
fi

exec .venv/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

