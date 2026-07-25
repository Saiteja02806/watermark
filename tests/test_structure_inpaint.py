from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

WORKER = Path(__file__).resolve().parents[1] / "workers" / "inpainting_worker"
sys.path.insert(0, str(WORKER))

from structure_inpaint import structure_aware_inpaint  # noqa: E402


def test_preserves_vertical_texture_through_small_overlay() -> None:
    height, width = 120, 160
    x = np.arange(width, dtype=np.float32)
    ribs = (145 + 35 * np.sin(x * np.pi / 4)).astype(np.uint8)
    frame = np.repeat(ribs[None, :, None], height, axis=0)
    frame = np.repeat(frame, 3, axis=2)
    clean = frame.copy()
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[50:70, 70:90] = 255
    frame[mask > 0] = 245

    repaired, method = structure_aware_inpaint(frame, mask)

    assert method == "directional_vertical"
    error = np.mean(
        np.abs(
            repaired[mask > 0].astype(np.int16)
            - clean[mask > 0].astype(np.int16)
        )
    )
    assert error < 2.0


def test_returns_unchanged_frame_for_empty_mask() -> None:
    frame = np.full((40, 60, 3), 91, dtype=np.uint8)
    repaired, method = structure_aware_inpaint(
        frame, np.zeros((40, 60), dtype=np.uint8)
    )
    assert method == "unchanged"
    assert np.array_equal(repaired, frame)
