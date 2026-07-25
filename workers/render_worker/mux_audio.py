from __future__ import annotations

import subprocess
from pathlib import Path


def mux_audio(
    ffmpeg_path: str,
    silent_video: Path,
    original_video: Path,
    output: Path,
    preserve_audio: bool,
) -> None:
    command = [ffmpeg_path, "-y", "-i", str(silent_video)]
    if preserve_audio:
        command += [
            "-i",
            str(original_video),
            "-map",
            "0:v:0",
            "-map",
            "1:a?",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
        ]
    else:
        command += ["-map", "0:v:0", "-c:v", "copy", "-an"]
    command += ["-movflags", "+faststart", str(output)]
    completed = subprocess.run(
        command, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError("\n".join(completed.stderr.splitlines()[-10:]))

