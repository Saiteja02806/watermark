from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any


CHUNK_CORE_FRAMES = 10
CHUNK_CONTEXT_FRAMES = 1


def _env_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None:
        return None
    return int(value)


def propainter_chunk_sizes() -> tuple[int, int]:
    """Choose a conservative outer chunk size from VRAM or explicit settings."""
    configured_core = _env_int("LVC_PROPAINTER_CHUNK_CORE_FRAMES")
    configured_context = _env_int("LVC_PROPAINTER_CHUNK_CONTEXT_FRAMES")
    if configured_core is not None:
        core = max(4, configured_core)
    else:
        core = CHUNK_CORE_FRAMES
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            total_mib = int(result.stdout.splitlines()[0].strip())
            if total_mib >= 22_000:
                core = 48
            elif total_mib >= 14_000:
                core = 16
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            pass
    context = (
        max(0, configured_context)
        if configured_context is not None
        else (
            4
            if core >= 48
            else 2 if core > CHUNK_CORE_FRAMES else CHUNK_CONTEXT_FRAMES
        )
    )
    return core, context


def propainter_preset(quality: str) -> tuple[int, int, int]:
    """Return neighbor, reference-stride, and sub-video settings for 6 GB GPUs."""
    presets = {
        "fast": (4, 24, 8),
        "balanced": (4, 20, 10),
        "high": (4, 16, 10),
    }
    neighbor, stride, subvideo = presets.get(quality, presets["balanced"])
    return (
        _env_int("LVC_PROPAINTER_NEIGHBOR_LENGTH") or neighbor,
        _env_int("LVC_PROPAINTER_REF_STRIDE") or stride,
        _env_int("LVC_PROPAINTER_SUBVIDEO_LENGTH") or subvideo,
    )


def _worker_environment(payload: dict[str, Any]) -> dict[str, str]:
    return {
        **os.environ,
        "CUDA_MODULE_LOADING": "LAZY",
        "MPLCONFIGDIR": str(
            Path(payload["projectPath"]) / "work" / "matplotlib"
        ),
        "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:128",
    }


def _invoke_propainter(
    payload: dict[str, Any],
    video: Path,
    masks: Path,
    output: Path,
    *,
    save_frames: bool,
) -> None:
    repository = Path(payload["propainterRepo"])
    script = repository / "inference_propainter.py"
    neighbor, stride, subvideo = propainter_preset(
        payload.get("quality", "balanced")
    )
    command = shlex.split(
        payload["propainterPython"], posix=os.name != "nt"
    )
    command += [
        str(script),
        "--video",
        str(video),
        "--mask",
        str(masks),
        "--output",
        str(output),
        "--width",
        str(payload["width"]),
        "--height",
        str(payload["height"]),
        "--save_fps",
        str(round(float(payload.get("fps") or 30))),
        "--fp16",
        "--neighbor_length",
        str(neighbor),
        "--ref_stride",
        str(stride),
        "--subvideo_length",
        str(subvideo),
    ]
    if save_frames:
        command.append("--save_frames")
    completed = subprocess.run(
        command,
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=_worker_environment(payload),
    )
    if completed.returncode:
        detail = "\n".join(
            (completed.stderr or completed.stdout).splitlines()[-16:]
        )
        raise RuntimeError(detail or "ProPainter failed")


def _encode_frames(
    payload: dict[str, Any],
    frames: Path,
    output: Path,
) -> None:
    quality = payload.get("quality", "balanced")
    preset, crf = {
        "fast": ("veryfast", "20"),
        "balanced": ("medium", "18"),
        "high": ("slow", "16"),
    }.get(quality, ("medium", "18"))
    completed = subprocess.run(
        [
            str(payload["ffmpegPath"]),
            "-y",
            "-framerate",
            str(float(payload.get("fps") or 30)),
            "-start_number",
            "0",
            "-i",
            str(frames / "%06d.png"),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            crf,
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        detail = "\n".join(
            (completed.stderr or completed.stdout).splitlines()[-12:]
        )
        raise RuntimeError(detail or "Could not encode ProPainter frames")


def _normalize_single_output(
    payload: dict[str, Any],
    output: Path,
) -> Path:
    exact_output = output.with_name("inpaint_out_exact.mp4")
    completed = subprocess.run(
        [
            str(payload["ffmpegPath"]),
            "-y",
            "-i",
            str(output),
            "-vf",
            (
                f"scale={int(payload['width'])}:{int(payload['height'])}"
                ":flags=lanczos"
            ),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(exact_output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        detail = "\n".join(
            (completed.stderr or completed.stdout).splitlines()[-12:]
        )
        raise RuntimeError(detail or "Could not normalize ProPainter output")
    return exact_output


def _run_chunked(payload: dict[str, Any], save_root: Path) -> Path:
    frame_paths = sorted(Path(payload["framesPath"]).glob("*.png"))
    mask_paths = sorted(Path(payload["finalMasksPath"]).glob("*.png"))
    if not frame_paths or len(frame_paths) != len(mask_paths):
        raise ValueError("ProPainter frames and masks are not aligned")

    chunk_root = save_root / "chunks"
    combined_frames = save_root / "combined_frames"
    chunk_root.mkdir(parents=True)
    combined_frames.mkdir(parents=True)
    total = len(frame_paths)
    chunk_core_frames, chunk_context_frames = propainter_chunk_sizes()

    for core_start in range(0, total, chunk_core_frames):
        core_end = min(total, core_start + chunk_core_frames)
        input_start = max(0, core_start - chunk_context_frames)
        input_end = min(total, core_end + chunk_context_frames)
        chunk_name = f"{core_start:06d}-{core_end - 1:06d}"
        chunk_dir = chunk_root / chunk_name
        chunk_frames = chunk_dir / "input_frames"
        chunk_masks = chunk_dir / "input_masks"
        chunk_output = chunk_dir / "output"
        chunk_frames.mkdir(parents=True)
        chunk_masks.mkdir(parents=True)

        for local_index, source_index in enumerate(
            range(input_start, input_end)
        ):
            name = f"{local_index:06d}.png"
            shutil.copy2(frame_paths[source_index], chunk_frames / name)
            shutil.copy2(mask_paths[source_index], chunk_masks / name)

        _invoke_propainter(
            payload,
            chunk_frames,
            chunk_masks,
            chunk_output,
            save_frames=True,
        )
        rendered = sorted(chunk_output.rglob("*.png"))
        expected_count = input_end - input_start
        if len(rendered) != expected_count:
            raise RuntimeError(
                f"ProPainter chunk {chunk_name} produced "
                f"{len(rendered)} of {expected_count} frames"
            )

        keep_start = core_start - input_start
        keep_end = keep_start + (core_end - core_start)
        for local_index in range(keep_start, keep_end):
            global_index = input_start + local_index
            shutil.copy2(
                rendered[local_index],
                combined_frames / f"{global_index:06d}.png",
            )

        print(
            json.dumps(
                {
                    "stage": "INPAINTING",
                    "progress": round(8 + 70 * core_end / total),
                    "currentFrame": core_end - 1,
                    "totalFrames": total,
                    "message": (
                        f"ProPainter reconstructed frames 1–{core_end} "
                        f"of {total}"
                    ),
                },
                separators=(",", ":"),
            ),
            flush=True,
        )

    combined = sorted(combined_frames.glob("*.png"))
    if len(combined) != total:
        raise RuntimeError(
            f"ProPainter assembled {len(combined)} of {total} frames"
        )
    output = save_root / "inpaint_out_exact.mp4"
    _encode_frames(payload, combined_frames, output)
    return output


def run_propainter(payload: dict[str, Any]) -> Path:
    repository = Path(payload["propainterRepo"])
    script = repository / "inference_propainter.py"
    if not script.is_file():
        raise FileNotFoundError(
            "ProPainter is not installed. Run scripts/install_models.sh first."
        )
    save_root = Path(payload["projectPath"]) / "work" / "propainter_result"
    if save_root.exists():
        shutil.rmtree(save_root)
    save_root.mkdir(parents=True)

    frame_count = int(payload.get("frameCount") or 0)
    frames_path = Path(payload.get("framesPath") or "")
    chunk_core_frames, _ = propainter_chunk_sizes()
    if frame_count > chunk_core_frames and frames_path.is_dir():
        return _run_chunked(payload, save_root)

    _invoke_propainter(
        payload,
        Path(payload["normalizedVideo"]),
        Path(payload["finalMasksPath"]),
        save_root,
        save_frames=False,
    )
    outputs = sorted(
        save_root.rglob("inpaint_out.mp4"),
        key=lambda path: path.stat().st_mtime,
    )
    if not outputs:
        raise FileNotFoundError("ProPainter did not create an MP4 output")
    return _normalize_single_output(payload, outputs[-1])
