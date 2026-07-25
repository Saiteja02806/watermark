from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

from ..models import RenderRequest
from ..services.event_service import project_events
from ..services.process_service import JobConflictError, process_supervisor
from ..services.project_service import ProjectNotFoundError, project_service


router = APIRouter(prefix="/api/projects", tags=["rendering"])


@router.post("/{project_id}/render", status_code=status.HTTP_202_ACCEPTED)
def render_video(project_id: str, payload: RenderRequest) -> dict:
    try:
        project = project_service.get(project_id)
        final_masks = project_service.path(project_id, "masks", "final")
        retryable_failure = (
            project["status"] == "FAILED"
            and final_masks.is_dir()
            and any(final_masks.glob("*.png"))
        )
        if (
            project["status"] not in {"READY_FOR_MASK_REVIEW", "COMPLETE"}
            and not retryable_failure
        ):
            raise HTTPException(
                status_code=400, detail="Review tracked masks before processing."
            )
        job_id = process_supervisor.render(project_id, payload)
        return {"jobId": job_id, "status": "INPAINTING"}
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{project_id}/events")
def events(project_id: str) -> StreamingResponse:
    try:
        project_service.get(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return StreamingResponse(
        project_events(project_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{project_id}/output")
def get_output(project_id: str) -> FileResponse:
    try:
        project = project_service.get(project_id)
        path = project_service.path(project_id, "final.mp4")
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    if project["status"] != "COMPLETE" or not path.is_file():
        raise HTTPException(status_code=404, detail="Output is not ready")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"{project.get('name') or 'cleaned-video'}.mp4",
    )


@router.get("/{project_id}/quality-report")
def get_quality_report(project_id: str) -> dict:
    try:
        project = project_service.get(project_id)
        path = project_service.path(project_id, "quality_report.json")
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    if project["status"] != "COMPLETE" or not path.is_file():
        raise HTTPException(status_code=404, detail="Quality report is not ready")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Quality report could not be read",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="Quality report is invalid")
    return payload
