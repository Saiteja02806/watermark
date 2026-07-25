from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from ..models import ProjectCreate, ProjectResponse
from ..services.process_service import process_supervisor
from ..services.project_service import ProjectNotFoundError, project_service


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate) -> dict:
    return project_service.create(payload.name)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str) -> dict:
    try:
        return project_service.get(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@router.post("/{project_id}/cancel")
def cancel_project(project_id: str) -> dict:
    try:
        project_service.get(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    cancelled = process_supervisor.cancel(project_id)
    return {"cancelled": cancelled}


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str) -> Response:
    try:
        process_supervisor.cancel(project_id)
        project_service.delete(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

