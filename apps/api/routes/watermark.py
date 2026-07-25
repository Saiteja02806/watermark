from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import AutoWatermarkRequest
from ..services.project_service import ProjectNotFoundError
from ..services.watermark_detector import (
    WatermarkDetectionError,
    watermark_detector,
)


router = APIRouter(prefix="/api/projects", tags=["watermark"])


@router.post("/{project_id}/watermark/auto")
def detect_watermark(
    project_id: str, payload: AutoWatermarkRequest | None = None
) -> dict:
    try:
        request = payload or AutoWatermarkRequest()
        return watermark_detector.detect(project_id, request.sampleCount)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except WatermarkDetectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
