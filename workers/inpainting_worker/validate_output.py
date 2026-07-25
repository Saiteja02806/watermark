from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def inspect_rendered_frames(
    original_paths: list[Path],
    rendered_paths: list[Path],
    mask_paths: list[Path],
) -> dict[str, Any]:
    if len(rendered_paths) != len(original_paths):
        raise ValueError("Rendered frame count does not match the source")
    full_black_frames: list[int] = []
    masked_black_ratios: list[float] = []
    boundary_scores: list[float] = []
    repaired_means: list[float] = []
    for index, (original_path, rendered_path, mask_path) in enumerate(
        zip(original_paths, rendered_paths, mask_paths, strict=True)
    ):
        original = cv2.imread(str(original_path), cv2.IMREAD_COLOR)
        rendered = cv2.imread(str(rendered_path), cv2.IMREAD_COLOR)
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if original is None or rendered is None or mask is None:
            raise ValueError(f"Frame {index} or its mask cannot be decoded")
        if rendered.shape != original.shape or mask.shape != original.shape[:2]:
            raise ValueError(f"Frame {index} dimensions are inconsistent")
        if float(rendered.mean()) < 1.0 and float(original.mean()) >= 1.0:
            full_black_frames.append(index)
        selected = mask >= 128
        if selected.any():
            pixels = rendered[selected]
            masked_black_ratios.append(float(np.mean(np.max(pixels, axis=1) < 4)))
            repaired_means.append(float(np.mean(pixels)))
            ring = cv2.dilate(
                selected.astype(np.uint8), np.ones((5, 5), np.uint8)
            ).astype(bool) ^ cv2.erode(
                selected.astype(np.uint8), np.ones((5, 5), np.uint8)
            ).astype(bool)
            if ring.any():
                boundary_scores.append(
                    float(
                        np.mean(
                            np.abs(
                                rendered[ring].astype(np.float32)
                                - original[ring].astype(np.float32)
                            )
                        )
                    )
                )
    if full_black_frames:
        raise ValueError(
            f"Rendered output contains black frames: {full_black_frames[:5]}"
        )
    flicker_score = (
        float(np.mean(np.abs(np.diff(repaired_means)))) if len(repaired_means) > 1 else 0.0
    )
    return {
        "valid": True,
        "frameCount": len(rendered_paths),
        "maskedBlackRatio": (
            float(np.mean(masked_black_ratios)) if masked_black_ratios else 0.0
        ),
        "boundaryDifference": (
            float(np.mean(boundary_scores)) if boundary_scores else 0.0
        ),
        "flickerScore": flicker_score,
        "humanReviewRequired": True,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

