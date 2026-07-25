from __future__ import annotations

import json
import os
import shutil
import shlex
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from ..config import settings
from ..database.sqlite import connection, utc_now
from ..models import ProjectStatus, RenderRequest, TrackRequest
from .ffmpeg_service import ffmpeg_service
from .project_service import project_service
from .render_dimensions import output_dimensions


class JobConflictError(RuntimeError):
    pass


class ProcessSupervisor:
    """A single-worker local queue for media and GPU-heavy jobs."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lvc-job")
        self._cancel_events: dict[str, threading.Event] = {}
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.RLock()

    def normalize(self, project_id: str) -> str:
        return self._submit(
            project_id,
            "NORMALIZE",
            ProjectStatus.NORMALIZING,
            lambda job_id, cancel: self._run_normalize(
                job_id, project_id, cancel
            ),
        )

    def track(self, project_id: str, request: TrackRequest) -> str:
        payload = request.model_dump()
        return self._submit(
            project_id,
            "TRACK",
            ProjectStatus.GENERATING_MASKS,
            lambda job_id, cancel: self._run_track(
                job_id, project_id, payload, cancel
            ),
            recovery_payload=payload,
        )

    def render(self, project_id: str, request: RenderRequest) -> str:
        payload = request.model_dump()
        return self._submit(
            project_id,
            "RENDER",
            ProjectStatus.INPAINTING,
            lambda job_id, cancel: self._run_render(
                job_id, project_id, payload, cancel
            ),
            recovery_payload=payload,
        )

    def cancel(self, project_id: str) -> bool:
        job = self.latest_job(project_id)
        if not job or job["status"] not in {"QUEUED", "RUNNING"}:
            return False
        job_id = job["id"]
        with self._lock:
            event = self._cancel_events.get(job_id)
            if event:
                event.set()
            process = self._active_processes.get(job_id)
            if process and process.poll() is None:
                process.terminate()
        project_dir = project_service.path(project_id)
        for filename in ("inpainted_silent.mp4", "final.mp4"):
            (project_dir / filename).unlink(missing_ok=True)
        self._update_job(job_id, status="CANCELLED", message="Processing cancelled")
        project_service.update(project_id, status=ProjectStatus.CANCELLED, error=None)
        return True

    def latest_job(self, project_id: str) -> dict[str, Any] | None:
        with connection() as db:
            row = db.execute(
                """
                SELECT * FROM jobs
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return dict(row) if row else None

    def _submit(
        self,
        project_id: str,
        job_type: str,
        project_status: ProjectStatus,
        runner: Callable[[str, threading.Event], None],
        recovery_payload: dict[str, Any] | None = None,
    ) -> str:
        active = self.latest_job(project_id)
        if active and active["status"] in {"QUEUED", "RUNNING"}:
            raise JobConflictError("This project already has an active job.")
        if recovery_payload is not None:
            request_path = project_service.path(
                project_id, "work", f"{job_type.lower()}_request.json"
            )
            request_path.write_text(
                json.dumps(recovery_payload, indent=2), encoding="utf-8"
            )
        job_id = str(uuid.uuid4())
        now = utc_now()
        with connection() as db:
            db.execute(
                """
                INSERT INTO jobs
                    (id, project_id, job_type, status, progress, message,
                     created_at, updated_at)
                VALUES (?, ?, ?, 'QUEUED', 0, 'Waiting for the local worker', ?, ?)
                """,
                (job_id, project_id, job_type, now, now),
            )
        project_service.update(project_id, status=project_status, error=None)
        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[job_id] = cancel_event
        self._executor.submit(
            self._job_wrapper, job_id, project_id, cancel_event, runner
        )
        return job_id

    def _job_wrapper(
        self,
        job_id: str,
        project_id: str,
        cancel_event: threading.Event,
        runner: Callable[[str, threading.Event], None],
    ) -> None:
        try:
            if cancel_event.is_set():
                raise InterruptedError("Processing was cancelled")
            self._update_job(job_id, status="RUNNING", message="Worker started")
            runner(job_id, cancel_event)
            if cancel_event.is_set():
                raise InterruptedError("Processing was cancelled")
            self._update_job(
                job_id, status="COMPLETE", progress=100, message="Stage complete"
            )
        except InterruptedError:
            self._update_job(
                job_id, status="CANCELLED", message="Processing cancelled"
            )
            project_service.update(
                project_id, status=ProjectStatus.CANCELLED, error=None
            )
        except Exception as exc:  # worker errors must reach the UI
            detail = str(exc).strip() or exc.__class__.__name__
            self._update_job(
                job_id,
                status="FAILED",
                message="Processing failed",
                error_message=detail[-4000:],
            )
            project_service.update(
                project_id, status=ProjectStatus.FAILED, error=detail[-2000:]
            )
        finally:
            with self._lock:
                self._cancel_events.pop(job_id, None)
                self._active_processes.pop(job_id, None)

    def _run_normalize(
        self, job_id: str, project_id: str, cancel_event: threading.Event
    ) -> None:
        project_dir = project_service.path(project_id)
        original = project_service.find_original(project_id)

        def progress(value: int, message: str) -> None:
            self._update_job(job_id, progress=value, message=message)

        metadata = ffmpeg_service.normalize(
            original, project_dir, cancel_event, progress
        )
        project_service.update(
            project_id,
            status=ProjectStatus.READY_FOR_SELECTION,
            metadata=metadata,
            error=None,
        )

    def _run_track(
        self,
        job_id: str,
        project_id: str,
        request: dict[str, Any],
        cancel_event: threading.Event,
    ) -> None:
        project_dir = project_service.path(project_id)
        selection_path = project_dir / "selection.json"
        if not selection_path.is_file():
            raise ValueError("Save a selection before starting tracking.")
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        project = project_service.get(project_id)
        engine = request.get("engine", "auto")
        if engine == "auto":
            engine = settings.tracker_engine
        input_payload = {
            "projectId": project_id,
            "projectPath": str(project_dir),
            "framesPath": str(project_dir / "frames"),
            "masksPath": str(project_dir / "masks" / "raw"),
            "initialFrame": selection["frameIndex"],
            "objectId": 1,
            "positivePoints": selection.get("positivePoints", []),
            "negativePoints": selection.get("negativePoints", []),
            "box": selection.get("box"),
            "manualMaskPath": selection.get("manualMaskPath"),
            "direction": request.get("direction", "both"),
            "engine": engine,
            "sam2Checkpoint": str(settings.sam2_checkpoint),
            "sam2Config": settings.sam2_config,
            "expectedFrameCount": project.get("frameCount"),
        }
        input_path = project_dir / "work" / "track_input.json"
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(json.dumps(input_payload, indent=2), encoding="utf-8")
        worker = settings.root_dir / "workers" / "sam2_worker" / "track_video.py"
        use_sam_environment = engine == "sam2" or (
            engine == "auto"
            and settings.sam2_checkpoint.is_file()
            and (settings.root_dir / "vendor" / "sam2").is_dir()
        )
        worker_python = (
            shlex.split(settings.sam2_python, posix=os.name != "nt")
            if use_sam_environment
            else [sys.executable]
        )
        result = self._run_worker(
            job_id,
            [*worker_python, str(worker), "--input", str(input_path)],
            cancel_event,
        )
        metrics_path = project_dir / "mask_metrics.json"
        metrics = (
            json.loads(metrics_path.read_text(encoding="utf-8"))
            if metrics_path.is_file()
            else {}
        )
        project_service.update(
            project_id,
            status=ProjectStatus.READY_FOR_MASK_REVIEW,
            metadata={
                "trackerEngine": result.get("engine", engine),
                "suspiciousFrames": metrics.get("suspiciousFrames", []),
                "sceneCuts": metrics.get("sceneCuts", []),
            },
            error=None,
        )

    def _run_render(
        self,
        job_id: str,
        project_id: str,
        request: dict[str, Any],
        cancel_event: threading.Event,
    ) -> None:
        project_dir = project_service.path(project_id)
        project = project_service.get(project_id)
        original = project_service.find_original(project_id)
        engine = request.get("engine", "auto")
        if engine == "auto":
            engine = settings.inpainting_engine
        if engine == "auto":
            engine = "propainter" if settings.propainter_available else "opencv"
        if engine == "propainter" and not settings.propainter_available:
            raise ValueError(
                "ProPainter source, runtime, or model weights are not ready."
            )
        output_width, output_height = output_dimensions(
            int(project.get("processingWidth") or 0),
            int(project.get("processingHeight") or 0),
            request["resolution"],
        )
        ffmpeg, ffprobe = ffmpeg_service.ensure_available()
        input_payload = {
            "projectId": project_id,
            "projectPath": str(project_dir),
            "framesPath": str(project_dir / "frames"),
            "rawMasksPath": str(project_dir / "masks" / "raw"),
            "correctedMasksPath": str(project_dir / "masks" / "corrected"),
            "finalMasksPath": str(project_dir / "masks" / "final"),
            "normalizedVideo": str(project_dir / "normalized.mp4"),
            "originalVideo": str(original),
            "silentOutput": str(project_dir / "inpainted_silent.mp4"),
            "finalOutput": str(project_dir / "final.mp4"),
            "ffmpegPath": str(ffmpeg),
            "ffprobePath": str(ffprobe),
            "engine": engine,
            "quality": request["quality"],
            "resolution": request["resolution"],
            "maskExpansion": request["maskExpansion"],
            "preserveAudio": request["preserveAudio"],
            "propainterRepo": str(settings.propainter_repo),
            "propainterPython": settings.propainter_python,
            "frameCount": project.get("frameCount"),
            "fps": project.get("fps"),
            "sourceWidth": project.get("processingWidth"),
            "sourceHeight": project.get("processingHeight"),
            "width": output_width,
            "height": output_height,
        }
        input_path = project_dir / "work" / "render_input.json"
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(json.dumps(input_payload, indent=2), encoding="utf-8")
        worker = settings.root_dir / "workers" / "render_worker" / "export_video.py"

        def handle_event(event: dict[str, Any]) -> None:
            if event.get("stage") == "MUXING_AUDIO":
                project_service.update(
                    project_id, status=ProjectStatus.MUXING_AUDIO, error=None
                )

        result = self._run_worker(
            job_id,
            [sys.executable, str(worker), "--input", str(input_path)],
            cancel_event,
            handle_event,
        )
        final_path = project_dir / "final.mp4"
        expected_output = {
            **project,
            "processingWidth": output_width,
            "processingHeight": output_height,
        }
        output_metadata = ffmpeg_service.validate_output(
            final_path, expected_output
        )
        project_service.update(
            project_id,
            status=ProjectStatus.COMPLETE,
            metadata={
                "inpaintingEngine": result.get("engine", engine),
                "outputDurationSeconds": output_metadata["durationSeconds"],
                "outputFrameCount": output_metadata["frameCount"],
                "outputHasAudio": output_metadata["hasAudio"],
                "outputWidth": output_metadata["width"],
                "outputHeight": output_metadata["height"],
            },
            error=None,
        )

    def _run_worker(
        self,
        job_id: str,
        args: list[str],
        cancel_event: threading.Event,
        event_handler: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            ),
        )
        with self._lock:
            self._active_processes[job_id] = process
        self._update_job(job_id, pid=process.pid)
        result: dict[str, Any] = {}
        diagnostic: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            if cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise InterruptedError("Processing was cancelled")
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                diagnostic.append(line)
                diagnostic = diagnostic[-20:]
                continue
            if event_handler:
                event_handler(event)
            if event.get("type") == "result":
                result.update(event)
            progress = event.get("progress")
            message = event.get("message")
            fields: dict[str, Any] = {}
            if progress is not None:
                fields["progress"] = max(0, min(99, int(progress)))
            if message:
                fields["message"] = str(message)
            if event.get("currentFrame") is not None:
                fields["current_frame"] = int(event["currentFrame"])
            if event.get("totalFrames") is not None:
                fields["total_frames"] = int(event["totalFrames"])
            if fields:
                self._update_job(job_id, **fields)
        return_code = process.wait()
        if return_code:
            detail = "\n".join(diagnostic[-10:])
            raise RuntimeError(detail or f"Worker exited with code {return_code}.")
        return result

    @staticmethod
    def _update_job(job_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = {
            "status",
            "progress",
            "current_frame",
            "total_frames",
            "message",
            "pid",
            "error_message",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with connection() as db:
            db.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",
                (*values.values(), job_id),
            )


process_supervisor = ProcessSupervisor()
