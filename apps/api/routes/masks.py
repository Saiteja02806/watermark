from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..models import MaskCorrectionRequest, SelectionRequest
from ..services.project_service import ProjectNotFoundError, project_service


router = APIRouter(prefix="/api/projects", tags=["masks"])


@router.post("/{project_id}/selection")
def save_selection(project_id: str, payload: SelectionRequest) -> dict:
    if not payload.has_prompt():
        raise HTTPException(
            status_code=400,
            detail="Add a point, draw a box, or paint a mask before tracking.",
        )
    try:
        project = project_service.get(project_id)
        frame_count = int(project.get("frameCount") or 0)
        if payload.frameIndex >= frame_count:
            raise HTTPException(status_code=400, detail="Frame index is out of range")
        data = payload.model_dump(exclude={"manualMaskDataUrl"})
        if payload.manualMaskDataUrl:
            mask_path = project_service.save_data_url_mask(
                project_id, payload.frameIndex, payload.manualMaskDataUrl, "corrected"
            )
            data["manualMaskPath"] = str(mask_path)
        selection_path = project_service.path(project_id, "selection.json")
        selection_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"saved": True, "selection": data}
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/masks/{frame_index}")
def get_mask(project_id: str, frame_index: int) -> FileResponse:
    if frame_index < 0:
        raise HTTPException(status_code=404, detail="Mask not found")
    try:
        for subdir in ("corrected", "final", "raw"):
            path = project_service.path(
                project_id, "masks", subdir, f"{frame_index:06d}.png"
            )
            if path.is_file():
                return FileResponse(path, media_type="image/png")
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    raise HTTPException(status_code=404, detail="Mask not found")


@router.post("/{project_id}/masks/{frame_index}/correct")
def correct_mask(
    project_id: str, frame_index: int, payload: MaskCorrectionRequest
) -> dict:
    try:
        project = project_service.get(project_id)
        if frame_index < 0 or frame_index >= int(project.get("frameCount") or 0):
            raise HTTPException(status_code=400, detail="Frame index is out of range")
        saved_path = None
        if payload.maskDataUrl:
            saved_path = project_service.save_data_url_mask(
                project_id, frame_index, payload.maskDataUrl, "corrected"
            )
        corrections_path = project_service.path(project_id, "corrections.json")
        corrections = (
            json.loads(corrections_path.read_text(encoding="utf-8"))
            if corrections_path.is_file()
            else {}
        )
        corrections[str(frame_index)] = {
            "frameIndex": frame_index,
            "type": "manual_mask" if saved_path else "sam_correction",
            "positivePoints": payload.positivePoints,
            "negativePoints": payload.negativePoints,
            "locked": payload.locked,
        }
        corrections_path.write_text(
            json.dumps(corrections, indent=2), encoding="utf-8"
        )
        return {"saved": True, "locked": payload.locked}
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

