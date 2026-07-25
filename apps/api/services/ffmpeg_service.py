from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from ..config import settings


class MediaToolUnavailableError(RuntimeError):
    pass


class MediaProcessError(RuntimeError):
    pass


ProgressCallback = Callable[[int, str], None]


def _fraction(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator) if float(denominator) else 0.0
    return float(value)


class FFmpegService:
    def ensure_available(self) -> tuple[Path, Path]:
        ffmpeg = settings.ffmpeg_path
        ffprobe = settings.ffprobe_path
        if not ffmpeg or not ffprobe:
            raise MediaToolUnavailableError(
                "FFmpeg and FFprobe are required. Run the setup script or set "
                "FFMPEG_PATH and FFPROBE_PATH."
            )
        return ffmpeg, ffprobe

    def probe(self, media_path: Path) -> dict[str, Any]:
        _, ffprobe = self.ensure_available()
        completed = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            creationflags=self._creation_flags(),
        )
        if completed.returncode:
            raise MediaProcessError(
                (completed.stderr or "FFprobe could not inspect this video.").strip()
            )
        payload = json.loads(completed.stdout)
        video_stream = next(
            (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
            None,
        )
        if not video_stream:
            raise MediaProcessError("The uploaded file does not contain a video stream.")
        audio_streams = [
            stream
            for stream in payload.get("streams", [])
            if stream.get("codec_type") == "audio"
        ]
        rotation = 0
        for side_data in video_stream.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = int(side_data["rotation"])
        rotation = int(video_stream.get("tags", {}).get("rotate", rotation) or 0)
        duration = float(
            video_stream.get("duration")
            or payload.get("format", {}).get("duration")
            or 0
        )
        avg_fps = _fraction(video_stream.get("avg_frame_rate"))
        real_fps = _fraction(video_stream.get("r_frame_rate"))
        frame_count = int(video_stream.get("nb_frames") or 0)
        if not frame_count and duration and avg_fps:
            frame_count = round(duration * avg_fps)
        return {
            "width": int(video_stream.get("width") or 0),
            "height": int(video_stream.get("height") or 0),
            "fps": avg_fps or real_fps,
            "rFrameRate": real_fps,
            "frameCount": frame_count,
            "durationSeconds": duration,
            "rotation": rotation,
            "videoCodec": video_stream.get("codec_name"),
            "pixelFormat": video_stream.get("pix_fmt"),
            "hasAudio": bool(audio_streams),
            "audioCodec": audio_streams[0].get("codec_name") if audio_streams else None,
            "variableFrameRate": bool(
                avg_fps and real_fps and abs(avg_fps - real_fps) > 0.01
            ),
        }

    def normalize(
        self,
        source: Path,
        project_dir: Path,
        cancel_event: threading.Event,
        progress: ProgressCallback,
    ) -> dict[str, Any]:
        ffmpeg, _ = self.ensure_available()
        source_meta = self.probe(source)
        duration = source_meta["durationSeconds"]
        if duration <= 0:
            raise MediaProcessError("The video duration could not be determined.")
        if duration > settings.max_duration_seconds + 0.1:
            raise MediaProcessError(
                f"This first release accepts videos up to "
                f"{settings.max_duration_seconds:g} seconds."
            )

        width, height = source_meta["width"], source_meta["height"]
        if abs(source_meta["rotation"]) in {90, 270}:
            width, height = height, width
        processing_width, processing_height = self._fit_dimensions(
            width, height, settings.processing_long_edge
        )
        proxy_width, proxy_height = self._fit_dimensions(
            width, height, settings.proxy_long_edge
        )
        normalized = project_dir / "normalized.mp4"
        proxy = project_dir / "proxy.mp4"
        frames_dir = project_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        progress(8, "Inspecting video streams")
        self._run(
            [
                str(ffmpeg),
                "-y",
                "-i",
                str(source),
                "-vf",
                f"fps=30,scale={processing_width}:{processing_height}:flags=lanczos",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(normalized),
            ],
            cancel_event,
        )
        progress(42, "Created the constant-frame-rate working video")
        self._run(
            [
                str(ffmpeg),
                "-y",
                "-i",
                str(normalized),
                "-vf",
                f"scale={proxy_width}:{proxy_height}:flags=lanczos",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "25",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(proxy),
            ],
            cancel_event,
        )
        progress(62, "Created the editor proxy")
        self._run(
            [
                str(ffmpeg),
                "-y",
                "-i",
                str(normalized),
                "-start_number",
                "0",
                "-vsync",
                "0",
                str(frames_dir / "%06d.png"),
            ],
            cancel_event,
        )
        progress(90, "Extracted frame-aligned images")
        normalized_meta = self.probe(normalized)
        frame_count = len(list(frames_dir.glob("*.png")))
        normalized_meta.update(
            {
                "frameCount": frame_count,
                "processingWidth": normalized_meta["width"],
                "processingHeight": normalized_meta["height"],
                "sourceWidth": source_meta["width"],
                "sourceHeight": source_meta["height"],
                "sourceFps": source_meta["fps"],
                "sourceRotation": source_meta["rotation"],
                "sourceVariableFrameRate": source_meta["variableFrameRate"],
                "hasAudio": source_meta["hasAudio"],
            }
        )
        return normalized_meta

    def mux_audio(
        self,
        silent_video: Path,
        original: Path,
        output: Path,
        preserve_audio: bool,
        cancel_event: threading.Event,
    ) -> None:
        ffmpeg, _ = self.ensure_available()
        args = [
            str(ffmpeg),
            "-y",
            "-i",
            str(silent_video),
        ]
        if preserve_audio:
            args += [
                "-i",
                str(original),
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
            args += ["-map", "0:v:0", "-c:v", "copy", "-an"]
        args += ["-movflags", "+faststart", str(output)]
        self._run(args, cancel_event)

    def frames_to_video(
        self,
        frames_pattern: Path,
        output: Path,
        cancel_event: threading.Event,
    ) -> None:
        ffmpeg, _ = self.ensure_available()
        self._run(
            [
                str(ffmpeg),
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
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ],
            cancel_event,
        )

    def validate_output(
        self, output: Path, expected: dict[str, Any]
    ) -> dict[str, Any]:
        if not output.is_file() or output.stat().st_size == 0:
            raise MediaProcessError("The output video is missing or empty.")
        metadata = self.probe(output)
        if metadata["durationSeconds"] <= 0:
            raise MediaProcessError("The output video has a zero duration.")
        expected_duration = float(expected.get("durationSeconds") or 0)
        if expected_duration and abs(metadata["durationSeconds"] - expected_duration) > 0.25:
            raise MediaProcessError("The output duration does not match the working video.")
        if (
            metadata["width"] != int(expected.get("processingWidth") or metadata["width"])
            or metadata["height"]
            != int(expected.get("processingHeight") or metadata["height"])
        ):
            raise MediaProcessError("The output resolution does not match the working video.")
        expected_frames = int(expected.get("frameCount") or 0)
        if expected_frames and abs(metadata["frameCount"] - expected_frames) > 1:
            raise MediaProcessError("The output frame count differs from the working video.")
        return metadata

    def _run(self, args: list[str], cancel_event: threading.Event) -> None:
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as log:
            process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=log,
                text=True,
                creationflags=self._creation_flags(),
            )
            while process.poll() is None:
                if cancel_event.wait(0.1):
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise InterruptedError("Processing was cancelled")
            if process.returncode:
                log.seek(0)
                lines = [
                    line for line in log.read().strip().splitlines() if line.strip()
                ]
                detail = "\n".join(lines[-8:]) if lines else "FFmpeg failed."
                raise MediaProcessError(detail)

    @staticmethod
    def _fit_dimensions(width: int, height: int, long_edge: int) -> tuple[int, int]:
        if width <= 0 or height <= 0:
            raise MediaProcessError("The video has invalid dimensions.")
        scale = min(1.0, long_edge / max(width, height))
        fitted_width = max(2, math.floor(width * scale / 2) * 2)
        fitted_height = max(2, math.floor(height * scale / 2) * 2)
        return fitted_width, fitted_height

    @staticmethod
    def _creation_flags() -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


ffmpeg_service = FFmpegService()
