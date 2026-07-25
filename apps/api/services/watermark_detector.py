from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .project_service import project_service


class WatermarkDetectionError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    label: int
    x: int
    y: int
    width: int
    height: int
    area: int
    score: float


class WatermarkDetector:
    def detect(self, project_id: str, sample_count: int = 24) -> dict[str, Any]:
        project = project_service.get(project_id)
        frame_paths = sorted(project_service.path(project_id, "frames").glob("*.png"))
        if not frame_paths:
            raise WatermarkDetectionError("Normalize the video before auto detection.")

        width = int(project.get("processingWidth") or project.get("width") or 0)
        height = int(project.get("processingHeight") or project.get("height") or 0)
        if width <= 0 or height <= 0:
            first = cv2.imread(str(frame_paths[0]), cv2.IMREAD_COLOR)
            if first is None:
                raise WatermarkDetectionError("The first video frame cannot be decoded.")
            height, width = first.shape[:2]

        sample_indices = self._sample_indices(len(frame_paths), sample_count)
        frames = self._read_frames(frame_paths, sample_indices, width, height)
        if len(frames) < 2:
            raise WatermarkDetectionError("Auto detection needs at least two frames.")

        mask, box, confidence = self._detect_mask(frames)
        area_ratio = float(np.count_nonzero(mask)) / float(width * height)
        if area_ratio < 0.00005:
            raise WatermarkDetectionError("No stable watermark-like region was found.")
        if area_ratio > 0.20:
            raise WatermarkDetectionError(
                "The detected region is too large to treat as a watermark."
            )

        frame_index = sample_indices[0]
        mask_path = project_service.path(
            project_id, "masks", "corrected", f"{frame_index:06d}.png"
        )
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(mask_path), mask):
            raise WatermarkDetectionError("Could not save the detected watermark mask.")

        selection = {
            "frameIndex": frame_index,
            "positivePoints": [],
            "negativePoints": [],
            "box": [float(value) for value in box],
            "manualMaskPath": str(mask_path),
            "autoWatermark": {
                "confidence": round(confidence, 4),
                "areaRatio": round(area_ratio, 6),
                "sampleCount": len(sample_indices),
            },
        }
        project_service.path(project_id, "selection.json").write_text(
            json.dumps(selection, indent=2), encoding="utf-8"
        )
        encoded = base64.b64encode(mask_path.read_bytes()).decode("ascii")
        return {
            "frameIndex": frame_index,
            "box": selection["box"],
            "manualMaskDataUrl": f"data:image/png;base64,{encoded}",
            "confidence": selection["autoWatermark"]["confidence"],
            "areaRatio": selection["autoWatermark"]["areaRatio"],
            "selection": selection,
        }

    @staticmethod
    def _sample_indices(frame_count: int, sample_count: int) -> list[int]:
        count = min(frame_count, sample_count)
        if count <= 1:
            return [0]
        return sorted(
            {
                round(position * (frame_count - 1) / (count - 1))
                for position in range(count)
            }
        )

    @staticmethod
    def _read_frames(
        frame_paths: list[Path],
        sample_indices: list[int],
        width: int,
        height: int,
    ) -> list[np.ndarray]:
        frames: list[np.ndarray] = []
        for index in sample_indices:
            frame = cv2.imread(str(frame_paths[index]), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            frames.append(frame)
        return frames

    def _detect_mask(
        self, frames: list[np.ndarray]
    ) -> tuple[np.ndarray, list[int], float]:
        height, width = frames[0].shape[:2]
        gray_frames = [
            cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (3, 3), 0)
            for frame in frames
        ]
        stack = np.stack(gray_frames).astype(np.float32)
        temporal_std = stack.std(axis=0)
        edge_stack = np.stack(
            [cv2.Canny(gray, 55, 145) > 0 for gray in gray_frames]
        )
        edge_persistence = edge_stack.mean(axis=0)
        static_score = np.clip((32.0 - temporal_std) / 32.0, 0.0, 1.0)
        score = edge_persistence * static_score
        score[edge_persistence < 0.35] = 0

        active = score[score > 0]
        if active.size == 0:
            raise WatermarkDetectionError("No persistent watermark edges were found.")
        threshold = max(0.20, float(np.percentile(active, 70)))
        seed = (score >= threshold).astype(np.uint8) * 255

        join_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (max(5, width // 70), max(3, height // 110)),
        )
        linked = cv2.morphologyEx(seed, cv2.MORPH_CLOSE, join_kernel, iterations=2)
        linked = cv2.dilate(linked, join_kernel, iterations=1)

        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            (linked > 0).astype(np.uint8), 8
        )
        candidates = self._candidates(count, labels, stats, score, width, height)
        if not candidates:
            raise WatermarkDetectionError("No compact watermark-like region was found.")
        best = max(candidates, key=lambda candidate: candidate.score)

        cluster = np.zeros((height, width), dtype=np.uint8)
        zone = self._expanded_box(
            best.x,
            best.y,
            best.x + best.width,
            best.y + best.height,
            width,
            height,
        )
        for candidate in candidates:
            center_x = candidate.x + candidate.width / 2
            center_y = candidate.y + candidate.height / 2
            if (
                candidate is best
                or (
                    zone[0] <= center_x <= zone[2]
                    and zone[1] <= center_y <= zone[3]
                    and candidate.score >= best.score * 0.45
                )
            ):
                cluster[labels == candidate.label] = 255

        final = cv2.bitwise_and(cv2.dilate(seed, join_kernel, iterations=1), cluster)
        final = cv2.dilate(
            final,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
            iterations=1,
        )
        final = cv2.morphologyEx(
            final,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        )
        box = self._mask_box(final)
        confidence = min(0.99, max(0.0, best.score * 1.8))
        return final, box, confidence

    @staticmethod
    def _candidates(
        count: int,
        labels: np.ndarray,
        stats: np.ndarray,
        score: np.ndarray,
        width: int,
        height: int,
    ) -> list[Candidate]:
        frame_area = width * height
        candidates: list[Candidate] = []
        for label in range(1, count):
            x, y, component_width, component_height, area = [
                int(value) for value in stats[label]
            ]
            area_ratio = area / frame_area
            if (
                area_ratio < 0.00025
                or area_ratio > 0.14
                or component_width < 8
                or component_height < 6
            ):
                continue
            component = labels == label
            component_score = float(score[component].mean())
            edge_density = float(np.count_nonzero(score[component] > 0)) / area
            margin_prior = WatermarkDetector._location_prior(
                x, y, component_width, component_height, width, height
            )
            candidate_score = (
                component_score * 0.62 + edge_density * 0.25 + margin_prior * 0.13
            )
            if candidate_score <= 0.05:
                continue
            candidates.append(
                Candidate(
                    label=label,
                    x=x,
                    y=y,
                    width=component_width,
                    height=component_height,
                    area=area,
                    score=candidate_score,
                )
            )
        return candidates

    @staticmethod
    def _location_prior(
        x: int,
        y: int,
        component_width: int,
        component_height: int,
        width: int,
        height: int,
    ) -> float:
        center_x = (x + component_width / 2) / width
        center_y = (y + component_height / 2) / height
        near_x_edge = center_x < 0.28 or center_x > 0.72
        near_y_edge = center_y < 0.28 or center_y > 0.72
        centered = 0.38 <= center_x <= 0.62 and 0.38 <= center_y <= 0.62
        if near_x_edge and near_y_edge:
            return 1.0
        if near_x_edge or near_y_edge:
            return 0.75
        if centered:
            return 0.45
        return 0.25

    @staticmethod
    def _expanded_box(
        x1: int, y1: int, x2: int, y2: int, width: int, height: int
    ) -> tuple[int, int, int, int]:
        pad_x = max(24, round(width * 0.10), x2 - x1)
        pad_y = max(16, round(height * 0.06), y2 - y1)
        return (
            max(0, x1 - pad_x),
            max(0, y1 - pad_y),
            min(width - 1, x2 + pad_x),
            min(height - 1, y2 + pad_y),
        )

    @staticmethod
    def _mask_box(mask: np.ndarray) -> list[int]:
        points = cv2.findNonZero((mask >= 128).astype(np.uint8))
        if points is None:
            raise WatermarkDetectionError("The detected watermark mask is empty.")
        x, y, width, height = cv2.boundingRect(points)
        return [x, y, x + width - 1, y + height - 1]


watermark_detector = WatermarkDetector()
