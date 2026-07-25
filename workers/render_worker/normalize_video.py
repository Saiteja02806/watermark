from __future__ import annotations

import subprocess
import threading
from pathlib import Path


def frames_to_h264(
    ffmpeg_path: str,
    frames_pattern: Path,
    output: Path,
    quality: str,
) -> None:
    crf = {"fast": "22", "balanced": "18", "high": "16"}[quality]
    preset = {"fast": "veryfast", "balanced": "medium", "high": "slow"}[quality]
    completed = subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-framerate",
            "30",
            "-start_number",
            "0",
            "-i",
            str(frames_pattern),
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
        raise RuntimeError("\n".join(completed.stderr.splitlines()[-10:]))

