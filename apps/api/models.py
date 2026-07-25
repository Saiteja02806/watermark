from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProjectStatus(StrEnum):
    CREATED = "CREATED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    NORMALIZING = "NORMALIZING"
    READY_FOR_SELECTION = "READY_FOR_SELECTION"
    GENERATING_MASKS = "GENERATING_MASKS"
    READY_FOR_MASK_REVIEW = "READY_FOR_MASK_REVIEW"
    INPAINTING = "INPAINTING"
    MUXING_AUDIO = "MUXING_AUDIO"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BatchStatus(StrEnum):
    CREATED = "CREATED"
    PREPARING = "PREPARING"
    READY_FOR_SELECTION = "READY_FOR_SELECTION"
    TRACKING = "TRACKING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    PARTIAL_COMPLETE = "PARTIAL_COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProjectCreate(BaseModel):
    name: str | None = Field(default=None, max_length=80)


class BatchCreate(BaseModel):
    name: str | None = Field(default=None, max_length=80)


class BatchProjectCreate(BaseModel):
    name: str | None = Field(default=None, max_length=80)


class PointPrompt(BaseModel):
    frameIndex: int = Field(ge=0)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    label: Literal[0, 1]


class BoxPrompt(BaseModel):
    frameIndex: int = Field(ge=0)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)
    x2: float = Field(ge=0)
    y2: float = Field(ge=0)

    @field_validator("x2")
    @classmethod
    def x2_after_x1(cls, value: float, info):
        x1 = info.data.get("x1")
        if x1 is not None and value <= x1:
            raise ValueError("x2 must be greater than x1")
        return value

    @field_validator("y2")
    @classmethod
    def y2_after_y1(cls, value: float, info):
        y1 = info.data.get("y1")
        if y1 is not None and value <= y1:
            raise ValueError("y2 must be greater than y1")
        return value


class SelectionRequest(BaseModel):
    frameIndex: int = Field(ge=0)
    positivePoints: list[list[float]] = Field(default_factory=list)
    negativePoints: list[list[float]] = Field(default_factory=list)
    box: list[float] | None = None
    manualMaskDataUrl: str | None = None

    @field_validator("box")
    @classmethod
    def valid_box(cls, value: list[float] | None):
        if value is None:
            return value
        if len(value) != 4 or value[2] <= value[0] or value[3] <= value[1]:
            raise ValueError("box must contain [x1, y1, x2, y2]")
        return value

    def has_prompt(self) -> bool:
        return bool(
            self.positivePoints
            or self.box
            or self.manualMaskDataUrl
        )


class AutoWatermarkRequest(BaseModel):
    sampleCount: int = Field(default=24, ge=4, le=72)


class BatchSelectionRequest(SelectionRequest):
    referenceProjectId: str
    fixed: bool = True


class TrackRequest(BaseModel):
    direction: Literal["forward", "backward", "both"] = "both"
    engine: Literal["auto", "sam2", "opencv", "fixed"] = "auto"


class MaskCorrectionRequest(BaseModel):
    maskDataUrl: str | None = None
    positivePoints: list[list[float]] = Field(default_factory=list)
    negativePoints: list[list[float]] = Field(default_factory=list)
    locked: bool = False


class RenderRequest(BaseModel):
    quality: Literal["fast", "balanced", "high"] = "balanced"
    resolution: Literal["480p", "720p"] = "720p"
    maskExpansion: Literal[2, 4, 8, 12] = 4
    preserveAudio: bool = True
    engine: Literal["auto", "propainter", "opencv"] = "auto"


class ProjectResponse(BaseModel):
    id: str
    name: str | None = None
    status: ProjectStatus
    originalFilename: str | None = None
    fps: float | None = None
    frameCount: int | None = None
    width: int | None = None
    height: int | None = None
    processingWidth: int | None = None
    processingHeight: int | None = None
    durationSeconds: float | None = None
    hasAudio: bool | None = None
    createdAt: str
    updatedAt: str
    error: str | None = None
    trackerEngine: str | None = None
    inpaintingEngine: str | None = None
    outputHasAudio: bool | None = None
    outputDurationSeconds: float | None = None
    outputFrameCount: int | None = None
    outputWidth: int | None = None
    outputHeight: int | None = None
    suspiciousFrames: list[int] = Field(default_factory=list)


class BatchItemResponse(ProjectResponse):
    position: int
    progress: int = 0
    message: str = ""
    jobStatus: str | None = None


class BatchResponse(BaseModel):
    id: str
    name: str | None = None
    status: BatchStatus
    progress: int = 0
    createdAt: str
    updatedAt: str
    items: list[BatchItemResponse] = Field(default_factory=list)
