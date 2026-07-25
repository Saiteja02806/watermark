from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def _centroid(mask: np.ndarray) -> tuple[float, float] | None:
    moments = cv2.moments(mask, binaryImage=True)
    if moments["m00"] == 0:
        return None
    return moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]


def calculate_metrics(
    mask_paths: list[Path],
    scene_cuts: list[int] | None = None,
    confidence_by_frame: dict[int, float] | None = None,
) -> dict[str, Any]:
    scene_cut_set = set(scene_cuts or [])
    confidence_by_frame = confidence_by_frame or {}
    suspicious: set[int] = set()
    frames: list[dict[str, Any]] = []
    previous_area = 0
    previous_centroid: tuple[float, float] | None = None
    for index, mask_path in enumerate(mask_paths):
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            suspicious.add(index)
            frames.append({"frameIndex": index, "reasons": ["missing_mask"]})
            continue
        binary = mask >= 128
        area = int(np.count_nonzero(binary))
        height, width = binary.shape
        centroid = _centroid(binary.astype(np.uint8))
        reasons: list[str] = []
        ratio = None
        movement = None
        if previous_area and area:
            ratio = area / previous_area
            if ratio < 0.35 or ratio > 2.8:
                reasons.append("area_change")
        if previous_centroid and centroid:
            movement = float(
                np.hypot(
                    centroid[0] - previous_centroid[0],
                    centroid[1] - previous_centroid[1],
                )
                / max(np.hypot(width, height), 1)
            )
            if movement > 0.12:
                reasons.append("centre_jump")
        border_contact = bool(
            binary[0, :].any()
            or binary[-1, :].any()
            or binary[:, 0].any()
            or binary[:, -1].any()
        )
        if border_contact and index not in scene_cut_set:
            reasons.append("border_contact")
        if area == 0 and index not in scene_cut_set and previous_area:
            reasons.append("empty_mask")
        confidence = confidence_by_frame.get(index)
        if confidence is not None and confidence < 0.2:
            reasons.append("low_tracking_confidence")
        if index in scene_cut_set:
            reasons.append("scene_cut")
        if reasons:
            suspicious.add(index)
        frames.append(
            {
                "frameIndex": index,
                "area": area,
                "areaRatio": ratio,
                "centroidMovement": movement,
                "borderContact": border_contact,
                "trackingConfidence": confidence,
                "reasons": reasons,
            }
        )
        previous_area = area
        previous_centroid = centroid
    return {
        "suspiciousFrames": sorted(suspicious),
        "sceneCuts": sorted(scene_cut_set),
        "frames": frames,
    }


def write_metrics(
    output_path: Path,
    mask_paths: list[Path],
    scene_cuts: list[int] | None = None,
    confidence_by_frame: dict[int, float] | None = None,
) -> dict[str, Any]:
    metrics = calculate_metrics(mask_paths, scene_cuts, confidence_by_frame)
    output_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics

