from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import cv2


ROOT = Path(__file__).resolve().parents[2]
for worker_dir in (
    ROOT / "workers" / "mask_worker",
    ROOT / "workers" / "inpainting_worker",
):
    if str(worker_dir) not in sys.path:
        sys.path.insert(0, str(worker_dir))

from postprocess_masks import postprocess  # noqa: E402
from run_propainter import run_propainter  # noqa: E402
from structure_inpaint import structure_aware_inpaint  # noqa: E402
from validate_output import (  # noqa: E402
    inspect_encoded_video,
    inspect_rendered_frames,
    write_report,
)
from mux_audio import mux_audio  # noqa: E402
from normalize_video import frames_to_h264  # noqa: E402


def emit(**payload: Any) -> None:
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def _resize_mask_for_validation(path: Path, payload: dict[str, Any]) -> Path:
    target_dir = (
        Path(payload["projectPath"]) / "work" / "render_validation_masks"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise ValueError(f"Validation mask cannot be decoded: {path.name}")
    target_size = (int(payload["width"]), int(payload["height"]))
    if (mask.shape[1], mask.shape[0]) != target_size:
        mask = cv2.resize(mask, target_size, interpolation=cv2.INTER_NEAREST)
    if not cv2.imwrite(str(target), mask):
        raise OSError(f"Could not write validation mask {path.name}")
    return target


def opencv_inpaint(
    payload: dict[str, Any],
    mask_paths: list[Path],
) -> tuple[Path, list[Path], list[Path]]:
    frame_paths = sorted(Path(payload["framesPath"]).glob("*.png"))
    output_dir = Path(payload["projectPath"]) / "work" / "inpainted_frames"
    source_dir = Path(payload["projectPath"]) / "work" / "render_source_frames"
    validation_mask_dir = (
        Path(payload["projectPath"]) / "work" / "render_validation_masks"
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    if source_dir.exists():
        shutil.rmtree(source_dir)
    if validation_mask_dir.exists():
        shutil.rmtree(validation_mask_dir)
    output_dir.mkdir(parents=True)
    source_dir.mkdir(parents=True)
    target_size = (int(payload["width"]), int(payload["height"]))
    total = len(frame_paths)
    rendered: list[Path] = []
    validation_sources: list[Path] = []
    method_counts: dict[str, int] = {}
    for index, (frame_path, mask_path) in enumerate(
        zip(frame_paths, mask_paths, strict=True)
    ):
        frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if frame is None or mask is None:
            raise ValueError(f"Frame {index} or its mask cannot be decoded")
        if mask.shape != frame.shape[:2]:
            raise ValueError(f"Mask {index} is not aligned with the working frame")
        if (frame.shape[1], frame.shape[0]) != target_size:
            frame = cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)
            mask = cv2.resize(mask, target_size, interpolation=cv2.INTER_NEAREST)
        source_target = source_dir / f"{index:06d}.png"
        if not cv2.imwrite(str(source_target), frame):
            raise OSError(f"Could not write validation source frame {index}")
        validation_sources.append(source_target)
        if mask.any():
            repaired, method = structure_aware_inpaint(frame, mask)
            method_counts[method] = method_counts.get(method, 0) + 1
        else:
            repaired = frame
            method_counts["unchanged"] = method_counts.get("unchanged", 0) + 1
        target = output_dir / f"{index:06d}.png"
        if not cv2.imwrite(str(target), repaired):
            raise OSError(f"Could not write repaired frame {index}")
        rendered.append(target)
        emit(
            stage="INPAINTING",
            progress=round(8 + 72 * (index + 1) / max(total, 1)),
            currentFrame=index,
            totalFrames=total,
            message=f"Reconstructing frame {index + 1} of {total}",
        )
    silent_output = Path(payload["silentOutput"])
    frames_to_h264(
        payload["ffmpegPath"],
        output_dir / "%06d.png",
        silent_output,
        payload["quality"],
    )
    emit(
        stage="INPAINTING",
        progress=82,
        totalFrames=total,
        message="Structure-aware repair complete",
        repairMethods=method_counts,
    )
    return silent_output, rendered, validation_sources


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    frame_count = int(payload["frameCount"])
    emit(
        stage="INPAINTING",
        progress=2,
        totalFrames=frame_count,
        message="Preparing frame-aligned masks",
    )
    mask_paths = postprocess(
        Path(payload["rawMasksPath"]),
        Path(payload["correctedMasksPath"]),
        Path(payload["finalMasksPath"]),
        frame_count,
        int(payload["maskExpansion"]),
    )
    engine = payload.get("engine", "auto")
    if engine == "auto":
        engine = "opencv"
    rendered_paths: list[Path] = []
    validation_sources: list[Path] = []
    if engine == "propainter":
        emit(
            stage="INPAINTING",
            progress=8,
            totalFrames=frame_count,
            message="ProPainter started",
        )
        propainter_output = run_propainter(payload)
        shutil.copy2(propainter_output, payload["silentOutput"])
        silent_output = Path(payload["silentOutput"])
        emit(
            stage="INPAINTING",
            progress=80,
            totalFrames=frame_count,
            message="ProPainter completed",
        )
    elif engine == "opencv":
        silent_output, rendered_paths, validation_sources = opencv_inpaint(
            payload, mask_paths
        )
    else:
        raise ValueError(f"Unknown inpainting engine: {engine}")
    emit(
        stage="INPAINTING",
        progress=82,
        totalFrames=frame_count,
        message="Checking every repaired frame for damage and flicker",
    )
    validation_masks = [
        _resize_mask_for_validation(path, payload)
        for path in mask_paths
    ]
    if rendered_paths:
        report = inspect_rendered_frames(
            validation_sources,
            rendered_paths,
            validation_masks,
        )
    else:
        report = inspect_encoded_video(
            silent_output,
            sorted(Path(payload["framesPath"]).glob("*.png")),
            validation_masks,
            (int(payload["width"]), int(payload["height"])),
        )
    report["engine"] = engine
    write_report(
        Path(payload["projectPath"]) / "quality_report.json",
        report,
    )
    emit(
        stage="MUXING_AUDIO",
        progress=86,
        totalFrames=frame_count,
        message=(
            "Restoring the original audio"
            if payload["preserveAudio"]
            else "Finalizing the silent video"
        ),
    )
    mux_audio(
        payload["ffmpegPath"],
        silent_output,
        Path(payload["originalVideo"]),
        Path(payload["finalOutput"]),
        bool(payload["preserveAudio"]),
    )
    emit(
        stage="MUXING_AUDIO",
        progress=98,
        totalFrames=frame_count,
        message="Validating the finished MP4",
    )
    emit(type="result", engine=engine, output=payload["finalOutput"])


if __name__ == "__main__":
    main()
