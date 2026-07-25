from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def histogram_similarity(previous: np.ndarray, current: np.ndarray) -> float:
    previous_hsv = cv2.cvtColor(previous, cv2.COLOR_BGR2HSV)
    current_hsv = cv2.cvtColor(current, cv2.COLOR_BGR2HSV)
    previous_hist = cv2.calcHist([previous_hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    current_hist = cv2.calcHist([current_hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(previous_hist, previous_hist)
    cv2.normalize(current_hist, current_hist)
    return float(
        cv2.compareHist(previous_hist, current_hist, cv2.HISTCMP_CORREL)
    )


def detect_scene_cuts(frame_paths: list[Path], threshold: float = 0.18) -> list[int]:
    cuts: list[int] = []
    previous = None
    for index, frame_path in enumerate(frame_paths):
        frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        if frame is None:
            continue
        small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
        if previous is not None and histogram_similarity(previous, small) < threshold:
            cuts.append(index)
        previous = small
    return cuts

