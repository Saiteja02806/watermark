from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np


FrameSet = tuple[int, np.ndarray, np.ndarray, np.ndarray]


def _inspect_frame_arrays(frames: Iterable[FrameSet]) -> dict[str, Any]:
    full_black_frames: list[int] = []
    masked_black_ratios: list[float] = []
    boundary_scores: list[float] = []
    inside_changes: list[float] = []
    outside_changes: list[float] = []
    temporal_scores: list[float] = []
    frame_count = 0
    selected_frame_count = 0
    previous_original: np.ndarray | None = None
    previous_rendered: np.ndarray | None = None
    previous_selected: np.ndarray | None = None

    for index, original, rendered, mask in frames:
        frame_count += 1
        if rendered.shape != original.shape or mask.shape != original.shape[:2]:
            raise ValueError(f"Frame {index} dimensions are inconsistent")
        if float(rendered.mean()) < 1.0 and float(original.mean()) >= 1.0:
            full_black_frames.append(index)

        selected = mask >= 128
        absolute_change = np.mean(
            np.abs(
                rendered.astype(np.float32) - original.astype(np.float32)
            ),
            axis=2,
        )
        if selected.any():
            selected_frame_count += 1
            pixels = rendered[selected]
            masked_black_ratios.append(
                float(np.mean(np.max(pixels, axis=1) < 4))
            )
            inside_changes.append(float(np.mean(absolute_change[selected])))
            ring = cv2.dilate(
                selected.astype(np.uint8), np.ones((5, 5), np.uint8)
            ).astype(bool) ^ cv2.erode(
                selected.astype(np.uint8), np.ones((5, 5), np.uint8)
            ).astype(bool)
            if ring.any():
                boundary_scores.append(float(np.mean(absolute_change[ring])))

        outside = ~selected
        if outside.any():
            outside_changes.append(float(np.mean(absolute_change[outside])))

        if (
            previous_original is not None
            and previous_rendered is not None
            and previous_selected is not None
        ):
            temporal_mask = selected | previous_selected
            if temporal_mask.any():
                original_delta = np.mean(
                    np.abs(
                        original.astype(np.float32)
                        - previous_original.astype(np.float32)
                    ),
                    axis=2,
                )
                rendered_delta = np.mean(
                    np.abs(
                        rendered.astype(np.float32)
                        - previous_rendered.astype(np.float32)
                    ),
                    axis=2,
                )
                temporal_scores.append(
                    float(
                        np.mean(
                            np.abs(
                                rendered_delta[temporal_mask]
                                - original_delta[temporal_mask]
                            )
                        )
                    )
                )
        previous_original = original
        previous_rendered = rendered
        previous_selected = selected

    if frame_count == 0:
        raise ValueError("Rendered output contains no decodable frames")
    if full_black_frames:
        raise ValueError(
            f"Rendered output contains black frames: {full_black_frames[:5]}"
        )

    report: dict[str, Any] = {
        "valid": True,
        "frameCount": frame_count,
        "selectedFrameCount": selected_frame_count,
        "maskedBlackRatio": (
            float(np.mean(masked_black_ratios)) if masked_black_ratios else 0.0
        ),
        "boundaryDifference": (
            float(np.mean(boundary_scores)) if boundary_scores else 0.0
        ),
        "flickerScore": (
            float(np.mean(temporal_scores)) if temporal_scores else 0.0
        ),
        "insideMeanAbsoluteChange": (
            float(np.mean(inside_changes)) if inside_changes else 0.0
        ),
        "outsideMeanAbsoluteChange": (
            float(np.mean(outside_changes)) if outside_changes else 0.0
        ),
        "humanReviewRequired": True,
    }
    warnings: list[str] = []
    if selected_frame_count == 0:
        warnings.append(
            "No selected pixels were present in the final repair masks."
        )
    elif report["insideMeanAbsoluteChange"] < 0.5:
        warnings.append(
            "The selected region changed very little; verify that the watermark is gone."
        )
    if report["outsideMeanAbsoluteChange"] > 12.0:
        warnings.append(
            "Large changes were measured outside the selected region."
        )
    if report["boundaryDifference"] > 35.0:
        warnings.append(
            "The repaired boundary differs strongly from the source edge."
        )
    if report["flickerScore"] > 18.0:
        warnings.append(
            "High temporal variation was measured inside the repaired region."
        )
    report["automatedChecksPassed"] = not warnings
    report["qualityWarnings"] = warnings
    return report


def inspect_rendered_frames(
    original_paths: list[Path],
    rendered_paths: list[Path],
    mask_paths: list[Path],
) -> dict[str, Any]:
    if not (
        len(rendered_paths) == len(original_paths) == len(mask_paths)
    ):
        raise ValueError("Rendered frame count does not match the source")

    def frames() -> Iterable[FrameSet]:
        for index, (original_path, rendered_path, mask_path) in enumerate(
            zip(original_paths, rendered_paths, mask_paths, strict=True)
        ):
            original = cv2.imread(str(original_path), cv2.IMREAD_COLOR)
            rendered = cv2.imread(str(rendered_path), cv2.IMREAD_COLOR)
            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if original is None or rendered is None or mask is None:
                raise ValueError(f"Frame {index} or its mask cannot be decoded")
            yield index, original, rendered, mask

    return _inspect_frame_arrays(frames())


def inspect_encoded_video(
    video_path: Path,
    original_paths: list[Path],
    mask_paths: list[Path],
    expected_size: tuple[int, int],
) -> dict[str, Any]:
    if len(original_paths) != len(mask_paths):
        raise ValueError("Validation mask count does not match the source")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError("The encoded ProPainter output could not be opened")
    expected_width, expected_height = expected_size

    def frames() -> Iterable[FrameSet]:
        for index, (original_path, mask_path) in enumerate(
            zip(original_paths, mask_paths, strict=True)
        ):
            decoded, rendered = capture.read()
            if not decoded or rendered is None:
                raise ValueError(
                    f"Encoded output ended at frame {index}; "
                    f"expected {len(original_paths)} frames"
                )
            if (
                rendered.shape[1] != expected_width
                or rendered.shape[0] != expected_height
            ):
                raise ValueError(
                    f"Encoded frame {index} has dimensions "
                    f"{rendered.shape[1]}x{rendered.shape[0]}; expected "
                    f"{expected_width}x{expected_height}"
                )
            original = cv2.imread(str(original_path), cv2.IMREAD_COLOR)
            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if original is None or mask is None:
                raise ValueError(f"Source frame {index} or its mask cannot be decoded")
            if original.shape[:2] != (expected_height, expected_width):
                original = cv2.resize(
                    original,
                    expected_size,
                    interpolation=cv2.INTER_AREA,
                )
            if mask.shape != (expected_height, expected_width):
                mask = cv2.resize(
                    mask,
                    expected_size,
                    interpolation=cv2.INTER_NEAREST,
                )
            yield index, original, rendered, mask
        decoded, _ = capture.read()
        if decoded:
            raise ValueError(
                "Encoded output contains more frames than the working video"
            )

    try:
        report = _inspect_frame_arrays(frames())
    finally:
        capture.release()
    report["encodedOutputInspected"] = True
    return report


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
