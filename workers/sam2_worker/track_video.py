from __future__ import annotations

import argparse
import gc
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from .refine_mask import apply_point_corrections
    from .scene_detection import detect_scene_cuts, histogram_similarity
except ImportError:  # Direct worker-script execution.
    from refine_mask import apply_point_corrections
    from scene_detection import detect_scene_cuts, histogram_similarity


ROOT = Path(__file__).resolve().parents[2]
MASK_WORKER = ROOT / "workers" / "mask_worker"
if str(MASK_WORKER) not in sys.path:
    sys.path.insert(0, str(MASK_WORKER))
from mask_metrics import write_metrics  # noqa: E402


def emit(**payload: Any) -> None:
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def normalize_sam_mask(mask_array: np.ndarray) -> np.ndarray:
    """Collapse SAM's object/channel axes into an OpenCV-compatible mask."""
    source_shape = tuple(mask_array.shape)
    mask = np.asarray(mask_array).squeeze()
    if mask.ndim != 2:
        raise ValueError(
            f"SAM 2 returned an unsupported mask shape {source_shape}"
        )
    return mask.astype(np.uint8) * 255


def initial_mask(payload: dict[str, Any], frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    manual_path = payload.get("manualMaskPath")
    if manual_path:
        mask = cv2.imread(str(manual_path), cv2.IMREAD_GRAYSCALE)
        if mask is None or mask.shape != (height, width):
            raise ValueError("The manual mask is missing or has incorrect dimensions")
        return (mask >= 128).astype(np.uint8) * 255

    mask = np.zeros((height, width), dtype=np.uint8)
    box = payload.get("box")
    if box:
        x1, y1, x2, y2 = [int(round(value)) for value in box]
        x1, x2 = sorted((max(0, x1), min(width - 1, x2)))
        y1, y2 = sorted((max(0, y1), min(height - 1, y2)))
        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
    radius = max(10, round(min(width, height) * 0.035))
    for x, y in payload.get("positivePoints", []):
        cv2.circle(mask, (round(x), round(y)), radius, 255, -1)
    for x, y in payload.get("negativePoints", []):
        cv2.circle(mask, (round(x), round(y)), radius, 0, -1)
    if not mask.any():
        raise ValueError("Tracking requires a box, positive point, or manual mask")
    return mask


def _bounded_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    points = cv2.findNonZero((mask >= 128).astype(np.uint8))
    if points is None:
        raise ValueError("The initial mask is empty")
    return cv2.boundingRect(points)


def _translate_mask(mask: np.ndarray, dx: float, dy: float) -> np.ndarray:
    transform = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(
        mask,
        transform,
        (mask.shape[1], mask.shape[0]),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def run_opencv(
    payload: dict[str, Any], frame_paths: list[Path], masks_dir: Path
) -> tuple[dict[int, float], list[int]]:
    initial_index = int(payload["initialFrame"])
    initial_frame = cv2.imread(str(frame_paths[initial_index]), cv2.IMREAD_COLOR)
    if initial_frame is None:
        raise ValueError("The selected frame cannot be decoded")
    base_mask = initial_mask(payload, initial_frame)
    x, y, width, height = _bounded_box(base_mask)
    template = cv2.cvtColor(
        initial_frame[y : y + height, x : x + width], cv2.COLOR_BGR2GRAY
    )
    if template.size == 0:
        raise ValueError("The selected region is outside the video frame")
    cv2.imwrite(str(masks_dir / f"{initial_index:06d}.png"), base_mask)
    confidence: dict[int, float] = {initial_index: 1.0}
    scene_cuts = detect_scene_cuts(frame_paths)
    scene_cut_set = set(scene_cuts)
    direction = payload.get("direction", "both")
    sequences: list[list[int]] = []
    if direction in {"forward", "both"}:
        sequences.append(list(range(initial_index + 1, len(frame_paths))))
    if direction in {"backward", "both"}:
        sequences.append(list(range(initial_index - 1, -1, -1)))

    total_steps = sum(len(sequence) for sequence in sequences) or 1
    completed = 0
    for sequence in sequences:
        previous_frame = initial_frame
        previous_mask = base_mask
        previous_x, previous_y, previous_w, previous_h = x, y, width, height
        stopped_at_cut = False
        for frame_index in sequence:
            frame = cv2.imread(str(frame_paths[frame_index]), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError(f"Frame {frame_index} cannot be decoded")
            crossed_cut = (
                frame_index in scene_cut_set
                if frame_index > initial_index
                else frame_index + 1 in scene_cut_set
            )
            similarity = histogram_similarity(
                cv2.resize(previous_frame, (160, 90), interpolation=cv2.INTER_AREA),
                cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA),
            )
            if crossed_cut or similarity < 0.18:
                stopped_at_cut = True
            if stopped_at_cut:
                tracked = np.zeros_like(base_mask)
                score = 0.0
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                search_pad_x = max(24, round(previous_w * 1.0))
                search_pad_y = max(24, round(previous_h * 1.0))
                left = max(0, previous_x - search_pad_x)
                top = max(0, previous_y - search_pad_y)
                right = min(gray.shape[1], previous_x + previous_w + search_pad_x)
                bottom = min(gray.shape[0], previous_y + previous_h + search_pad_y)
                search = gray[top:bottom, left:right]
                active_template = cv2.cvtColor(
                    previous_frame[
                        previous_y : previous_y + previous_h,
                        previous_x : previous_x + previous_w,
                    ],
                    cv2.COLOR_BGR2GRAY,
                )
                if (
                    active_template.size == 0
                    or search.shape[0] < active_template.shape[0]
                    or search.shape[1] < active_template.shape[1]
                ):
                    active_template = template
                response = cv2.matchTemplate(
                    search, active_template, cv2.TM_CCOEFF_NORMED
                )
                _, score, _, location = cv2.minMaxLoc(response)
                new_x = left + location[0]
                new_y = top + location[1]
                tracked = _translate_mask(
                    previous_mask, new_x - previous_x, new_y - previous_y
                )
                previous_x, previous_y = new_x, new_y
                previous_w, previous_h = active_template.shape[1], active_template.shape[0]
            cv2.imwrite(str(masks_dir / f"{frame_index:06d}.png"), tracked)
            confidence[frame_index] = float(score)
            previous_frame = frame
            previous_mask = tracked
            completed += 1
            emit(
                stage="GENERATING_MASKS",
                progress=round(5 + 88 * completed / total_steps),
                currentFrame=frame_index,
                totalFrames=len(frame_paths),
                message=f"Tracking frame {frame_index + 1} of {len(frame_paths)}",
            )

    for index in range(len(frame_paths)):
        target = masks_dir / f"{index:06d}.png"
        if not target.exists():
            cv2.imwrite(str(target), np.zeros_like(base_mask))
            confidence[index] = 0.0
    return confidence, scene_cuts


def run_fixed(
    payload: dict[str, Any], frame_paths: list[Path], masks_dir: Path
) -> tuple[dict[int, float], list[int]]:
    initial_index = int(payload["initialFrame"])
    initial_frame = cv2.imread(str(frame_paths[initial_index]), cv2.IMREAD_COLOR)
    if initial_frame is None:
        raise ValueError("The selected frame cannot be decoded")
    mask = initial_mask(payload, initial_frame)
    confidence: dict[int, float] = {}
    for index in range(len(frame_paths)):
        if not cv2.imwrite(str(masks_dir / f"{index:06d}.png"), mask):
            raise OSError(f"Could not write fixed mask for frame {index}")
        confidence[index] = 1.0
        if index % 8 == 0 or index == len(frame_paths) - 1:
            emit(
                stage="GENERATING_MASKS",
                progress=round(5 + 88 * (index + 1) / len(frame_paths)),
                currentFrame=index,
                totalFrames=len(frame_paths),
                message=f"Applying the fixed overlay mask to frame {index + 1}",
            )
    return confidence, detect_scene_cuts(frame_paths)


def run_sam2(
    payload: dict[str, Any], frame_paths: list[Path], masks_dir: Path
) -> tuple[dict[int, float], list[int]]:
    checkpoint = Path(payload["sam2Checkpoint"])
    if not checkpoint.is_file():
        raise FileNotFoundError(f"SAM 2 checkpoint not found: {checkpoint}")
    vendor = ROOT / "vendor" / "sam2"
    if not vendor.is_dir():
        raise FileNotFoundError(f"SAM 2 repository not found: {vendor}")
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    import torch
    from sam2.build_sam import build_sam2_video_predictor

    sam_frames = Path(payload["projectPath"]) / "work" / "sam_frames"
    if sam_frames.exists():
        shutil.rmtree(sam_frames)
    sam_frames.mkdir(parents=True)
    for index, source in enumerate(frame_paths):
        frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if frame is None or not cv2.imwrite(
            str(sam_frames / f"{index:06d}.jpg"),
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 95],
        ):
            raise ValueError(f"Could not prepare frame {index} for SAM 2")
    predictor = build_sam2_video_predictor(
        payload["sam2Config"], str(checkpoint), device="cuda"
    )
    state = predictor.init_state(
        video_path=str(sam_frames), offload_video_to_cpu=True
    )
    initial_index = int(payload["initialFrame"])
    points = np.array(
        payload.get("positivePoints", []) + payload.get("negativePoints", []),
        dtype=np.float32,
    )
    labels = np.array(
        [1] * len(payload.get("positivePoints", []))
        + [0] * len(payload.get("negativePoints", [])),
        dtype=np.int32,
    )
    box = (
        np.array(payload["box"], dtype=np.float32)
        if payload.get("box") is not None
        else None
    )
    manual_path = payload.get("manualMaskPath")
    confidence: dict[int, float] = {}
    scene_cuts = detect_scene_cuts(frame_paths)
    try:
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            if manual_path:
                mask = cv2.imread(manual_path, cv2.IMREAD_GRAYSCALE)
                predictor.add_new_mask(
                    inference_state=state,
                    frame_idx=initial_index,
                    obj_id=int(payload.get("objectId", 1)),
                    mask=mask >= 128,
                )
            else:
                predictor.add_new_points_or_box(
                    inference_state=state,
                    frame_idx=initial_index,
                    obj_id=int(payload.get("objectId", 1)),
                    points=points if points.size else None,
                    labels=labels if labels.size else None,
                    box=box,
                )
            direction = payload.get("direction", "both")
            directions = []
            if direction in {"forward", "both"}:
                directions.append(False)
            if direction in {"backward", "both"}:
                directions.append(True)
            completed = 0
            total = max(1, len(frame_paths) * len(directions))
            for reverse in directions:
                for frame_index, _, mask_logits in predictor.propagate_in_video(
                    state,
                    start_frame_idx=initial_index,
                    reverse=reverse,
                ):
                    # SAM 2 video logits are commonly shaped [objects, 1, H, W].
                    # OpenCV only accepts a 2-D mask here, so remove all singleton
                    # object/channel axes before encoding the PNG.
                    mask_array = (
                        (mask_logits[0] > 0)
                        .detach()
                        .cpu()
                        .numpy()
                    )
                    mask = normalize_sam_mask(mask_array)
                    cv2.imwrite(
                        str(masks_dir / f"{frame_index:06d}.png"),
                        mask,
                    )
                    confidence[frame_index] = 1.0
                    completed += 1
                    emit(
                        stage="GENERATING_MASKS",
                        progress=round(5 + 88 * completed / total),
                        currentFrame=frame_index,
                        totalFrames=len(frame_paths),
                        message=f"SAM 2 propagated frame {frame_index + 1}",
                    )
    finally:
        del predictor
        gc.collect()
        torch.cuda.empty_cache()
    sample = cv2.imread(str(frame_paths[0]), cv2.IMREAD_GRAYSCALE)
    for index in range(len(frame_paths)):
        target = masks_dir / f"{index:06d}.png"
        if not target.exists():
            cv2.imwrite(str(target), np.zeros_like(sample))
            confidence[index] = 0.0
    return confidence, scene_cuts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    frames_dir = Path(payload["framesPath"])
    masks_dir = Path(payload["masksPath"])
    frame_paths = sorted(frames_dir.glob("*.png"))
    if not frame_paths:
        raise FileNotFoundError("No extracted frames are available")
    if not 0 <= int(payload["initialFrame"]) < len(frame_paths):
        raise ValueError("The selected frame is out of range")
    masks_dir.mkdir(parents=True, exist_ok=True)
    for stale in masks_dir.glob("*.png"):
        stale.unlink()
    engine = payload.get("engine", "auto")
    if engine == "auto":
        engine = (
            "sam2"
            if Path(payload["sam2Checkpoint"]).is_file()
            and (ROOT / "vendor" / "sam2").is_dir()
            else "opencv"
        )
    emit(
        stage="GENERATING_MASKS",
        progress=2,
        currentFrame=int(payload["initialFrame"]),
        totalFrames=len(frame_paths),
        message=(
            "Loading SAM 2.1"
            if engine == "sam2"
            else "Starting local motion tracking"
        ),
    )
    if engine == "sam2":
        confidence, scene_cuts = run_sam2(payload, frame_paths, masks_dir)
    elif engine == "fixed":
        confidence, scene_cuts = run_fixed(payload, frame_paths, masks_dir)
    elif engine == "opencv":
        confidence, scene_cuts = run_opencv(payload, frame_paths, masks_dir)
    else:
        raise ValueError(f"Unknown tracking engine: {engine}")
    mask_paths = [masks_dir / f"{index:06d}.png" for index in range(len(frame_paths))]
    metrics = write_metrics(
        Path(payload["projectPath"]) / "mask_metrics.json",
        mask_paths,
        scene_cuts,
        confidence,
    )
    emit(
        stage="READY_FOR_MASK_REVIEW",
        progress=98,
        totalFrames=len(frame_paths),
        message=f"Tracking complete · {len(metrics['suspiciousFrames'])} frames need review",
    )
    emit(
        type="result",
        engine=engine,
        masks=len(mask_paths),
        suspiciousFrames=metrics["suspiciousFrames"],
    )


if __name__ == "__main__":
    main()
