#!/usr/bin/env bash
set -euo pipefail

export LVC_DATA_DIR="${LVC_DATA_DIR:-/workspace/frameclean-data}"
export LVC_BIND_HOST="${LVC_BIND_HOST:-0.0.0.0}"
export LVC_PORT="${LVC_PORT:-8000}"

if [[ -z "${LVC_SAM2_PYTHON:-}" ]] \
  && command -v conda >/dev/null 2>&1 \
  && conda run -n sam2 python --version >/dev/null 2>&1; then
  export LVC_SAM2_PYTHON="conda run -n sam2 python"
fi

if [[ -z "${LVC_PROPAINTER_PYTHON:-}" ]] \
  && command -v conda >/dev/null 2>&1 \
  && conda run -n propainter python --version >/dev/null 2>&1; then
  export LVC_PROPAINTER_PYTHON="conda run -n propainter python"
fi

mkdir -p "$LVC_DATA_DIR" "${MPLCONFIGDIR:-/tmp/matplotlib}"

exec python -m uvicorn apps.api.main:app \
  --host "$LVC_BIND_HOST" \
  --port "$LVC_PORT" \
  --proxy-headers \
  --forwarded-allow-ips="*"
