from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse

from ..models import (
    BatchCreate,
    BatchProjectCreate,
    BatchResponse,
    BatchSelectionRequest,
    ProjectResponse,
    RenderRequest,
    TrackRequest,
)
from ..services.batch_service import (
    BatchNotFoundError,
    BatchValidationError,
    batch_service,
)
from ..services.process_service import JobConflictError, process_supervisor
from ..services.project_service import ProjectNotFoundError


router = APIRouter(prefix="/api/batches", tags=["batches"])


@router.get("", response_model=list[BatchResponse])
def list_batches() -> list[dict]:
    return batch_service.list()


@router.post("", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
def create_batch(payload: BatchCreate) -> dict:
    return batch_service.create(payload.name)


@router.get("/{batch_id}", response_model=BatchResponse)
def get_batch(batch_id: str) -> dict:
    try:
        return batch_service.get(batch_id)
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Batch not found") from exc


@router.post(
    "/{batch_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_batch_project(batch_id: str, payload: BatchProjectCreate) -> dict:
    try:
        return batch_service.add_project(batch_id, payload.name)
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Batch not found") from exc
    except BatchValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{batch_id}/selection", status_code=status.HTTP_202_ACCEPTED)
def apply_batch_selection(batch_id: str, payload: BatchSelectionRequest) -> dict:
    try:
        project_ids = batch_service.apply_selection(batch_id, payload)
        job_ids = [
            process_supervisor.track(
                project_id,
                TrackRequest(
                    direction="both", engine="fixed" if payload.fixed else "auto"
                ),
            )
            for project_id in project_ids
        ]
        return {
            "batchId": batch_id,
            "status": "TRACKING",
            "jobs": job_ids,
        }
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Batch not found") from exc
    except (BatchValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{batch_id}/render", status_code=status.HTTP_202_ACCEPTED)
def render_batch(batch_id: str, payload: RenderRequest) -> dict:
    try:
        batch = batch_service.get(batch_id)
        if not batch["items"]:
            raise BatchValidationError("Upload at least one video first.")
        processable = [
            item
            for item in batch["items"]
            if item["status"] not in {"FAILED", "CANCELLED"}
        ]
        if not processable:
            raise BatchValidationError("No prepared videos are available to process.")
        invalid = [
            item
            for item in processable
            if item["status"] not in {"READY_FOR_MASK_REVIEW", "COMPLETE"}
        ]
        if invalid:
            raise BatchValidationError(
                "Wait until every video mask is ready before processing the batch."
            )
        batch_service.invalidate_archive(batch_id)
        job_ids = [
            process_supervisor.render(item["id"], payload)
            for item in processable
        ]
        batch_service.touch(batch_id)
        return {
            "batchId": batch_id,
            "status": "PROCESSING",
            "jobs": job_ids,
        }
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Batch not found") from exc
    except (BatchValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{batch_id}/cancel")
def cancel_batch(batch_id: str) -> dict:
    try:
        batch = batch_service.get(batch_id)
        cancelled = [
            item["id"]
            for item in batch["items"]
            if process_supervisor.cancel(item["id"])
        ]
        batch_service.touch(batch_id)
        return {"cancelled": cancelled}
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Batch not found") from exc


@router.get("/{batch_id}/output.zip")
def download_batch(batch_id: str) -> FileResponse:
    try:
        batch = batch_service.get(batch_id)
        path = batch_service.build_archive(batch_id)
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Batch not found") from exc
    except BatchValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = (
        f"{batch.get('name') or 'frameclean-batch'}-results.zip"
        .replace("/", "-")
        .replace("\\", "-")
    )
    return FileResponse(path, media_type="application/zip", filename=filename)


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(batch_id: str) -> Response:
    try:
        batch = batch_service.get(batch_id)
        for item in batch["items"]:
            process_supervisor.cancel(item["id"])
        batch_service.delete(batch_id)
    except (BatchNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Batch not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
