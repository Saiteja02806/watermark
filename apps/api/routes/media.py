from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from ..services.process_service import JobConflictError, process_supervisor
from ..services.project_service import (
    InvalidUploadError,
    ProjectNotFoundError,
    project_service,
)


router = APIRouter(prefix="/api/projects", tags=["media"])


@router.post("/{project_id}/upload", status_code=status.HTTP_202_ACCEPTED)
def upload_video(
    project_id: str,
    file: UploadFile = File(...),
    content_length: int | None = Header(default=None),
) -> dict:
    try:
        project_service.update(project_id, status="UPLOADING", error=None)
        project_service.save_upload(
            project_id,
            file.file,
            file.filename or "video.mp4",
            content_length,
        )
        job_id = process_supervisor.normalize(project_id)
        return {"jobId": job_id, "status": "NORMALIZING"}
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except (InvalidUploadError, ValueError) as exc:
        project_service.update(project_id, status="FAILED", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        file.file.close()


@router.get("/{project_id}/video")
def get_proxy_video(project_id: str) -> FileResponse:
    return _file(project_id, "proxy.mp4", "video/mp4")


@router.get("/{project_id}/original")
def get_original_video(project_id: str) -> FileResponse:
    try:
        path = project_service.find_original(project_id)
    except (ProjectNotFoundError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Original video not found") from exc
    return FileResponse(path, media_type="video/mp4")


@router.get("/{project_id}/frame/{frame_index}")
def get_frame(project_id: str, frame_index: int) -> FileResponse:
    if frame_index < 0:
        raise HTTPException(status_code=404, detail="Frame not found")
    return _file(
        project_id, str(Path("frames") / f"{frame_index:06d}.png"), "image/png"
    )


def _file(project_id: str, relative: str, media_type: str) -> FileResponse:
    try:
        path = project_service.path(project_id, relative)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media is not ready")
    return FileResponse(path, media_type=media_type)

