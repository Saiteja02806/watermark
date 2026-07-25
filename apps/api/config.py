from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
PROPAINTER_WEIGHT_FILES = (
    "raft-things.pth",
    "recurrent_flow_completion.pth",
    "ProPainter.pth",
)


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


def _runtime_command(command: str) -> list[str]:
    direct = Path(command)
    if direct.is_file():
        return [str(direct)]
    return shlex.split(command, posix=os.name != "nt")


@lru_cache(maxsize=16)
def _runtime_available(command: str) -> bool:
    args = _runtime_command(command)
    if not args or (not Path(args[0]).is_file() and not shutil.which(args[0])):
        return False
    try:
        completed = subprocess.run(
            [*args, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _default_model_runtime(venv_name: str, conda_env: str) -> str:
    direct = ROOT_DIR / venv_name / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    if direct.is_file():
        return str(direct)
    conda_command = f"conda run -n {conda_env} python"
    if shutil.which("conda") and _runtime_available(conda_command):
        return conda_command
    return str(direct)


@lru_cache(maxsize=16)
def _torch_runtime_details(command: str) -> dict[str, str | bool | None]:
    if not _runtime_available(command):
        return {
            "cudaAvailable": False,
            "gpuName": None,
            "torchVersion": None,
            "error": "The configured Python runtime could not be started.",
        }
    script = (
        "import json\n"
        "try:\n"
        " import torch\n"
        " available = bool(torch.cuda.is_available())\n"
        " print(json.dumps({'cudaAvailable': available,"
        " 'gpuName': torch.cuda.get_device_name(0) if available else None,"
        " 'torchVersion': torch.__version__, 'error': None}))\n"
        "except Exception as exc:\n"
        " print(json.dumps({'cudaAvailable': False, 'gpuName': None,"
        " 'torchVersion': None, 'error': str(exc)}))\n"
    )
    args = _runtime_command(command)
    try:
        completed = subprocess.run(
            [*args, "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "cudaAvailable": False,
            "gpuName": None,
            "torchVersion": None,
            "error": str(exc),
        }
    for line in reversed(completed.stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "cudaAvailable" in payload:
            return payload
    detail = completed.stderr.strip() or completed.stdout.strip()
    return {
        "cudaAvailable": False,
        "gpuName": None,
        "torchVersion": None,
        "error": detail[-500:] or "PyTorch did not return GPU diagnostics.",
    }


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
        _default_model_runtime(".sam2-venv", "sam2"),
    )
    propainter_python: str = os.getenv(
        "LVC_PROPAINTER_PYTHON",
        _default_model_runtime(".propainter-venv", "propainter"),
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
        return _runtime_available(self.sam2_python)

    @property
    def propainter_runtime_available(self) -> bool:
        return _runtime_available(self.propainter_python)

    @property
    def sam2_source_available(self) -> bool:
        return (self.root_dir / "vendor" / "sam2").is_dir()

    @property
    def sam2_checkpoint_available(self) -> bool:
        return self.sam2_checkpoint.is_file() and self.sam2_checkpoint.stat().st_size > 0

    @property
    def propainter_weights_available(self) -> bool:
        weights = self.propainter_repo / "weights"
        return all(
            (weights / filename).is_file()
            and (weights / filename).stat().st_size > 0
            for filename in PROPAINTER_WEIGHT_FILES
        )

    @property
    def propainter_weight_status(self) -> dict[str, bool]:
        weights = self.propainter_repo / "weights"
        return {
            filename: (weights / filename).is_file()
            and (weights / filename).stat().st_size > 0
            for filename in PROPAINTER_WEIGHT_FILES
        }

    @property
    def propainter_source_available(self) -> bool:
        return (self.propainter_repo / "inference_propainter.py").is_file()

    @property
    def propainter_cuda_available(self) -> bool:
        return bool(self.acceleration_details.get("cudaAvailable"))

    @property
    def propainter_available(self) -> bool:
        return (
            self.propainter_source_available
            and self.propainter_runtime_available
            and self.propainter_weights_available
            and self.propainter_cuda_available
        )

    @property
    def propainter_missing_components(self) -> list[str]:
        missing: list[str] = []
        if not self.propainter_source_available:
            missing.append("source")
        if not self.propainter_runtime_available:
            missing.append("Python runtime")
        unavailable_weights = [
            name for name, available in self.propainter_weight_status.items() if not available
        ]
        if unavailable_weights:
            missing.append(f"weights ({', '.join(unavailable_weights)})")
        if self.propainter_runtime_available and not self.propainter_cuda_available:
            missing.append("CUDA GPU")
        return missing

    @property
    def acceleration_details(self) -> dict[str, str | bool | None]:
        runtime = (
            self.propainter_python
            if self.propainter_runtime_available
            else self.sam2_python
        )
        return _torch_runtime_details(runtime)


settings = Settings()
