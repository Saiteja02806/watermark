from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from workers.inpainting_worker.validate_output import inspect_encoded_video


def _make_sequence(
    root: Path,
    *,
    source_frames: int,
    encoded_frames: int,
) -> tuple[Path, list[Path], list[Path]]:
    source_dir = root / "source"
    mask_dir = root / "masks"
    source_dir.mkdir()
    mask_dir.mkdir()
    source_paths: list[Path] = []
    mask_paths: list[Path] = []
    clean = np.full((48, 64, 3), (72, 104, 136), dtype=np.uint8)
    for index in range(source_frames):
        source = clean.copy()
        cv2.rectangle(source, (44, 30), (55, 41), (245, 245, 245), -1)
        mask = np.zeros((48, 64), dtype=np.uint8)
        cv2.rectangle(mask, (42, 28), (57, 43), 255, -1)
        source_path = source_dir / f"{index:06d}.png"
        mask_path = mask_dir / f"{index:06d}.png"
        assert cv2.imwrite(str(source_path), source)
        assert cv2.imwrite(str(mask_path), mask)
        source_paths.append(source_path)
        mask_paths.append(mask_path)

    video_path = root / "repaired.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10,
        (64, 48),
    )
    assert writer.isOpened()
    for _ in range(encoded_frames):
        writer.write(clean)
    writer.release()
    return video_path, source_paths, mask_paths


def test_encoded_video_is_decoded_and_compared_frame_by_frame(
    tmp_path: Path,
) -> None:
    video, sources, masks = _make_sequence(
        tmp_path,
        source_frames=6,
        encoded_frames=6,
    )

    report = inspect_encoded_video(video, sources, masks, (64, 48))

    assert report["valid"] is True
    assert report["encodedOutputInspected"] is True
    assert report["frameCount"] == 6
    assert report["selectedFrameCount"] == 6
    assert (
        report["insideMeanAbsoluteChange"]
        > report["outsideMeanAbsoluteChange"]
    )
    assert report["flickerScore"] < 1.0


def test_encoded_video_rejects_missing_frames(tmp_path: Path) -> None:
    video, sources, masks = _make_sequence(
        tmp_path,
        source_frames=6,
        encoded_frames=5,
    )

    with pytest.raises(ValueError, match="ended at frame 5"):
        inspect_encoded_video(video, sources, masks, (64, 48))
