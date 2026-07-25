from __future__ import annotations

import sys
from pathlib import Path


SAM_WORKER = Path(__file__).resolve().parents[1] / "sam2_worker"
if str(SAM_WORKER) not in sys.path:
    sys.path.insert(0, str(SAM_WORKER))

from scene_detection import detect_scene_cuts, histogram_similarity  # noqa: E402,F401

