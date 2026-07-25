from __future__ import annotations

import cv2
import numpy as np


def structure_aware_inpaint(
    frame: np.ndarray, mask: np.ndarray
) -> tuple[np.ndarray, str]:
    """Repair small masks while preserving strongly directional local texture.

    OpenCV's radial inpainting is a useful general fallback, but it creates
    visible star/X patterns over regular ribs, slats, or horizontal bands.
    For small components with a strong local gradient orientation, interpolate
    along the texture direction instead.
    """

    binary = (mask >= 128).astype(np.uint8)
    if not binary.any():
        return frame.copy(), "unchanged"

    repaired = cv2.inpaint(frame, binary * 255, 4, cv2.INPAINT_TELEA)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gradient_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    gradient_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    methods: set[str] = set()
    frame_area = frame.shape[0] * frame.shape[1]

    for component_id in range(1, component_count):
        x, y, width, height, area = [
            int(value) for value in stats[component_id]
        ]
        component = labels == component_id
        if (
            area > frame_area * 0.04
            or width > frame.shape[1] * 0.25
            or height > frame.shape[0] * 0.25
        ):
            methods.add("telea")
            continue

        ring_size = max(7, min(21, round(max(width, height) * 0.45)))
        if ring_size % 2 == 0:
            ring_size += 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (ring_size, ring_size)
        )
        ring = cv2.dilate(component.astype(np.uint8), kernel).astype(bool)
        ring &= ~component
        if not ring.any():
            methods.add("telea")
            continue

        mean_x = float(np.mean(gradient_x[ring]))
        mean_y = float(np.mean(gradient_y[ring]))
        if mean_x > max(1.0, mean_y) * 1.6:
            _interpolate_vertically(frame, repaired, component, x, width)
            methods.add("directional_vertical")
        elif mean_y > max(1.0, mean_x) * 1.6:
            _interpolate_horizontally(frame, repaired, component, y, height)
            methods.add("directional_horizontal")
        else:
            methods.add("telea")

    return repaired, "+".join(sorted(methods)) or "telea"


def _interpolate_vertically(
    source: np.ndarray,
    target: np.ndarray,
    component: np.ndarray,
    x_start: int,
    width: int,
) -> None:
    for x in range(x_start, x_start + width):
        selected = np.flatnonzero(component[:, x])
        if selected.size == 0:
            continue
        for start, end in _contiguous_runs(selected):
            top = _sample_vertical(source, component, x, start - 1, -1)
            bottom = _sample_vertical(source, component, x, end + 1, 1)
            if top is None or bottom is None:
                continue
            span = max(1, end - start + 2)
            for y in range(start, end + 1):
                blend = (y - start + 1) / span
                target[y, x] = np.clip(
                    top * (1.0 - blend) + bottom * blend, 0, 255
                ).astype(np.uint8)


def _interpolate_horizontally(
    source: np.ndarray,
    target: np.ndarray,
    component: np.ndarray,
    y_start: int,
    height: int,
) -> None:
    for y in range(y_start, y_start + height):
        selected = np.flatnonzero(component[y, :])
        if selected.size == 0:
            continue
        for start, end in _contiguous_runs(selected):
            left = _sample_horizontal(source, component, y, start - 1, -1)
            right = _sample_horizontal(source, component, y, end + 1, 1)
            if left is None or right is None:
                continue
            span = max(1, end - start + 2)
            for x in range(start, end + 1):
                blend = (x - start + 1) / span
                target[y, x] = np.clip(
                    left * (1.0 - blend) + right * blend, 0, 255
                ).astype(np.uint8)


def _sample_vertical(
    source: np.ndarray,
    component: np.ndarray,
    x: int,
    start: int,
    direction: int,
) -> np.ndarray | None:
    samples: list[np.ndarray] = []
    y = start
    while 0 <= y < source.shape[0] and len(samples) < 3:
        if not component[y, x]:
            samples.append(source[y, x].astype(np.float32))
        y += direction
    return np.mean(samples, axis=0) if samples else None


def _sample_horizontal(
    source: np.ndarray,
    component: np.ndarray,
    y: int,
    start: int,
    direction: int,
) -> np.ndarray | None:
    samples: list[np.ndarray] = []
    x = start
    while 0 <= x < source.shape[1] and len(samples) < 3:
        if not component[y, x]:
            samples.append(source[y, x].astype(np.float32))
        x += direction
    return np.mean(samples, axis=0) if samples else None


def _contiguous_runs(indices: np.ndarray) -> list[tuple[int, int]]:
    if indices.size == 0:
        return []
    breaks = np.where(np.diff(indices) > 1)[0]
    starts = np.concatenate(([0], breaks + 1))
    ends = np.concatenate((breaks, [indices.size - 1]))
    return [(int(indices[start]), int(indices[end])) for start, end in zip(starts, ends)]

