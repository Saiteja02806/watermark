from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..models import TrackRequest
from ..services.process_service import JobConflictError, process_supervisor
from ..services.project_service import ProjectNotFoundError, project_service


router = APIRouter(prefix="/api/projects", tags=["tracking"])


@router.post("/{project_id}/track", status_code=status.HTTP_202_ACCEPTED)
def track_selection(project_id: str, payload: TrackRequest) -> dict:
    try:
        selection = project_service.path(project_id, "selection.json")
        if not selection.is_file():
            raise HTTPException(status_code=400, detail="Save a selection first")
        job_id = process_supervisor.track(project_id, payload)
        return {"jobId": job_id, "status": "GENERATING_MASKS"}
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

