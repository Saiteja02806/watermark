from __future__ import annotations

import os
import platform
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_binary(env_name: str, executable: str, candidates: list[Path]) -> Path | None:
    configured = os.getenv(env_name)
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_file():
            return path

    discovered = shutil.which(executable)
    if discovered:
        return Path(discovered).resolve()

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _binary_architecture(machine: str | None = None) -> str:
    normalized = (machine or platform.machine()).strip().lower()
    if normalized in {"x86_64", "amd64"}:
        return "x64"
    if normalized in {"x86", "i386", "i686"}:
        return "ia32"
    if normalized in {"arm64", "aarch64"}:
        return "arm64"
    return normalized


def _ffmpeg_candidates(
    root_dir: Path, platform_name: str | None = None
) -> list[Path]:
    current_platform = (platform_name or sys.platform).lower()
    filename = "ffmpeg.exe" if current_platform.startswith("win") else "ffmpeg"
    return [root_dir / "node_modules" / "ffmpeg-static" / filename]


def _ffprobe_candidates(
    root_dir: Path,
    platform_name: str | None = None,
    machine: str | None = None,
) -> list[Path]:
    current_platform = (platform_name or sys.platform).lower()
    architecture = _binary_architecture(machine)
    if current_platform.startswith("win"):
        operating_system = "win32"
        filename = "ffprobe.exe"
    elif current_platform == "darwin":
        operating_system = "darwin"
        filename = "ffprobe"
    else:
        operating_system = "linux"
        filename = "ffprobe"
    return [
        root_dir
        / "node_modules"
        / "ffprobe-static"
        / "bin"
        / operating_system
        / architecture
        / filename
    ]


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    data_dir: Path = Path(os.getenv("LVC_DATA_DIR", str(ROOT_DIR / "data"))).resolve()
    max_upload_bytes: int = int(os.getenv("LVC_MAX_UPLOAD_BYTES", str(1024 * 1024 * 1024)))
    max_batch_videos: int = int(os.getenv("LVC_MAX_BATCH_VIDEOS", "20"))
    max_duration_seconds: float = float(os.getenv("LVC_MAX_DURATION_SECONDS", "15"))
    processing_long_edge: int = int(os.getenv("LVC_PROCESSING_LONG_EDGE", "720"))
    proxy_long_edge: int = int(os.getenv("LVC_PROXY_LONG_EDGE", "480"))
    tracker_engine: str = os.getenv("LVC_TRACKER_ENGINE", "auto").lower()
    inpainting_engine: str = os.getenv("LVC_INPAINTING_ENGINE", "auto").lower()
    bind_host: str = os.getenv("LVC_BIND_HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", os.getenv("LVC_PORT", "8000")))
    remote_access: bool = _env_bool("LVC_REMOTE_ACCESS")
    access_username: str = os.getenv("LVC_USERNAME", "frameclean")
    access_password: str = os.getenv("LVC_PASSWORD", "")
    sam2_python: str = os.getenv(
        "LVC_SAM2_PYTHON",
        str(
            ROOT_DIR
            / ".sam2-venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        ),
    )
    propainter_python: str = os.getenv(
        "LVC_PROPAINTER_PYTHON",
        str(
            ROOT_DIR
            / ".propainter-venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        ),
    )
    sam2_checkpoint: Path = Path(
        os.getenv(
            "LVC_SAM2_CHECKPOINT",
            str(ROOT_DIR / "models" / "sam2" / "sam2.1_hiera_small.pt"),
        )
    ).resolve()
    sam2_config: str = os.getenv(
        "LVC_SAM2_CONFIG", "configs/sam2.1/sam2.1_hiera_s.yaml"
    )
    propainter_repo: Path = Path(
        os.getenv("LVC_PROPAINTER_REPO", str(ROOT_DIR / "vendor" / "ProPainter"))
    ).resolve()

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def batches_dir(self) -> Path:
        return self.data_dir / "batches"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def ffmpeg_path(self) -> Path | None:
        return _resolve_binary(
            "FFMPEG_PATH",
            "ffmpeg",
            _ffmpeg_candidates(self.root_dir),
        )

    @property
    def ffprobe_path(self) -> Path | None:
        return _resolve_binary(
            "FFPROBE_PATH",
            "ffprobe",
            _ffprobe_candidates(self.root_dir),
        )

    @property
    def sam2_runtime_available(self) -> bool:
        direct = Path(self.sam2_python)
        if direct.is_file():
            return True
        command = shlex.split(self.sam2_python, posix=os.name != "nt")
        return bool(command and shutil.which(command[0]))

    @property
    def propainter_runtime_available(self) -> bool:
        direct = Path(self.propainter_python)
        if direct.is_file():
            return True
        command = shlex.split(self.propainter_python, posix=os.name != "nt")
        return bool(command and shutil.which(command[0]))

    @property
    def propainter_weights_available(self) -> bool:
        weights = self.propainter_repo / "weights"
        return all(
            (weights / filename).is_file()
            for filename in (
                "raft-things.pth",
                "recurrent_flow_completion.pth",
                "ProPainter.pth",
            )
        )

    @property
    def propainter_available(self) -> bool:
        return (
            (self.propainter_repo / "inference_propainter.py").is_file()
            and self.propainter_runtime_available
            and self.propainter_weights_available
        )


settings = Settings()
