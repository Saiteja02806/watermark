from __future__ import annotations

import base64
import json
import os
import urllib.request


port = os.getenv("LVC_PORT", "8000")
request = urllib.request.Request(f"http://127.0.0.1:{port}/api/health")
if os.getenv("LVC_REMOTE_ACCESS", "").lower() in {"1", "true", "yes", "on"}:
    username = os.getenv("LVC_USERNAME", "frameclean")
    password = os.getenv("LVC_PASSWORD", "")
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    request.add_header("Authorization", f"Basic {token}")

with urllib.request.urlopen(request, timeout=5) as response:
    payload = json.load(response)
if payload.get("status") != "ok":
    raise SystemExit(1)
