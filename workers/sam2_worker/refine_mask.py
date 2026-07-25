from __future__ import annotations

import cv2
import numpy as np


def apply_point_corrections(
    mask: np.ndarray,
    positive_points: list[list[float]],
    negative_points: list[list[float]],
    radius: int | None = None,
) -> np.ndarray:
    refined = (mask >= 128).astype(np.uint8) * 255
    height, width = refined.shape
    radius = radius or max(6, round(min(width, height) * 0.025))
    for x, y in positive_points:
        cv2.circle(refined, (round(x), round(y)), radius, 255, -1)
    for x, y in negative_points:
        cv2.circle(refined, (round(x), round(y)), radius, 0, -1)
    return refined

