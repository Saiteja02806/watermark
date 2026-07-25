from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import settings
from ..database.sqlite import connection, row_to_project, utc_now
from ..models import BatchSelectionRequest
from .project_service import ProjectNotFoundError, project_service


class BatchNotFoundError(LookupError):
    pass


class BatchValidationError(ValueError):
    pass


class BatchService:
    def create(self, name: str | None = None) -> dict[str, Any]:
        batch_id = str(uuid.uuid4())
        now = utc_now()
        self.path(batch_id, require_exists=False).mkdir(parents=True, exist_ok=True)
        with connection() as db:
            db.execute(
                """
                INSERT INTO batches (id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (batch_id, name, now, now),
            )
        return self.get(batch_id)

    def add_project(self, batch_id: str, name: str | None = None) -> dict[str, Any]:
        batch = self.get(batch_id)
        if len(batch["items"]) >= settings.max_batch_videos:
            raise BatchValidationError(
                f"A batch can contain at most {settings.max_batch_videos} videos."
            )
        project = project_service.create(name)
        now = utc_now()
        try:
            with connection() as db:
                position = db.execute(
                    """
                    SELECT COALESCE(MAX(position), -1) + 1
                    FROM batch_items WHERE batch_id = ?
                    """,
                    (batch_id,),
                ).fetchone()[0]
                db.execute(
                    """
                    INSERT INTO batch_items
                        (batch_id, project_id, position, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (batch_id, project["id"], position, now),
                )
                db.execute(
                    "UPDATE batches SET updated_at = ? WHERE id = ?",
                    (now, batch_id),
                )
        except Exception:
            project_service.delete(project["id"])
            raise
        return {**project, "position": int(position)}

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with connection() as db:
            rows = db.execute(
                """
                SELECT id FROM batches
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self.get(row["id"]) for row in rows]

    def get(self, batch_id: str) -> dict[str, Any]:
        self._validate_uuid(batch_id)
        with connection() as db:
            batch = db.execute(
                "SELECT * FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if batch is None:
                raise BatchNotFoundError(batch_id)
            rows = db.execute(
                """
                SELECT
                    p.*,
                    bi.position AS batch_position,
                    j.status AS job_status,
                    j.progress AS job_progress,
                    j.message AS job_message,
                    j.error_message AS job_error
                FROM batch_items bi
                JOIN projects p ON p.id = bi.project_id
                LEFT JOIN jobs j ON j.id = (
                    SELECT id FROM jobs
                    WHERE project_id = p.id
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                WHERE bi.batch_id = ?
                ORDER BY bi.position
                """,
                (batch_id,),
            ).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            project = row_to_project(row)
            project["position"] = int(row["batch_position"])
            project["progress"] = int(row["job_progress"] or 0)
            project["message"] = (
                row["job_error"]
                or row["job_message"]
                or project.get("error")
                or str(project["status"]).replace("_", " ").title()
            )
            project["jobStatus"] = row["job_status"]
            items.append(project)

        status = self._derive_status(items)
        progress = (
            round(sum(self._pipeline_progress(item) for item in items) / len(items))
            if items
            else 0
        )
        return {
            "id": batch["id"],
            "name": batch["name"],
            "status": status,
            "progress": progress,
            "createdAt": batch["created_at"],
            "updatedAt": batch["updated_at"],
            "items": items,
        }

    def apply_selection(
        self, batch_id: str, payload: BatchSelectionRequest
    ) -> list[str]:
        batch = self.get(batch_id)
        selectable = [
            item
            for item in batch["items"]
            if item["status"] not in {"FAILED", "CANCELLED"}
        ]
        if not selectable:
            raise BatchValidationError("Upload at least one video first.")
        reference = next(
            (
                item
                for item in selectable
                if item["id"] == payload.referenceProjectId
            ),
            None,
        )
        if reference is None:
            raise BatchValidationError("The reference video is not in this batch.")
        if any(item["status"] != "READY_FOR_SELECTION" for item in selectable):
            raise BatchValidationError(
                "Wait until every video is prepared before applying the selection."
            )
        if not payload.has_prompt():
            raise BatchValidationError(
                "Add a point, draw a box, or paint the watermark first."
            )

        reference_width = int(reference.get("processingWidth") or 0)
        reference_height = int(reference.get("processingHeight") or 0)
        if reference_width <= 0 or reference_height <= 0:
            raise BatchValidationError("The reference video dimensions are unavailable.")

        reference_manual_path: Path | None = None
        if payload.manualMaskDataUrl:
            reference_manual_path = project_service.save_data_url_mask(
                reference["id"],
                payload.frameIndex,
                payload.manualMaskDataUrl,
                "corrected",
            )

        project_ids: list[str] = []
        for item in selectable:
            width = int(item.get("processingWidth") or 0)
            height = int(item.get("processingHeight") or 0)
            frame_count = int(item.get("frameCount") or 0)
            if width <= 0 or height <= 0 or frame_count <= 0:
                raise BatchValidationError(
                    f"{item.get('name') or item['id']} is not ready for selection."
                )
            scale_x = width / reference_width
            scale_y = height / reference_height
            reference_frames = max(1, int(reference.get("frameCount") or 1))
            frame_ratio = payload.frameIndex / max(1, reference_frames - 1)
            target_frame = min(frame_count - 1, round(frame_ratio * (frame_count - 1)))

            manual_path: Path | None = None
            if reference_manual_path is not None:
                manual_path = project_service.path(
                    item["id"], "masks", "corrected", f"{target_frame:06d}.png"
                )
                if item["id"] != reference["id"] or target_frame != payload.frameIndex:
                    with Image.open(reference_manual_path) as source:
                        source.convert("L").resize(
                            (width, height), Image.Resampling.NEAREST
                        ).save(manual_path)
                else:
                    manual_path = reference_manual_path

            selection = {
                "frameIndex": target_frame,
                "positivePoints": [
                    [point[0] * scale_x, point[1] * scale_y]
                    for point in payload.positivePoints
                ],
                "negativePoints": [
                    [point[0] * scale_x, point[1] * scale_y]
                    for point in payload.negativePoints
                ],
                "box": (
                    [
                        payload.box[0] * scale_x,
                        payload.box[1] * scale_y,
                        payload.box[2] * scale_x,
                        payload.box[3] * scale_y,
                    ]
                    if payload.box
                    else None
                ),
                "manualMaskPath": str(manual_path) if manual_path else None,
            }
            project_service.path(item["id"], "selection.json").write_text(
                json.dumps(selection, indent=2), encoding="utf-8"
            )
            project_ids.append(item["id"])

        self.touch(batch_id)
        self.invalidate_archive(batch_id)
        return project_ids

    def contains(self, batch_id: str, project_id: str) -> bool:
        self._validate_uuid(batch_id)
        try:
            project_service.get(project_id)
        except ProjectNotFoundError:
            return False
        with connection() as db:
            row = db.execute(
                """
                SELECT 1 FROM batch_items
                WHERE batch_id = ? AND project_id = ?
                """,
                (batch_id, project_id),
            ).fetchone()
        return row is not None

    def touch(self, batch_id: str) -> None:
        self._validate_uuid(batch_id)
        with connection() as db:
            updated = db.execute(
                "UPDATE batches SET updated_at = ? WHERE id = ?",
                (utc_now(), batch_id),
            ).rowcount
        if not updated:
            raise BatchNotFoundError(batch_id)

    def path(
        self, batch_id: str, *parts: str, require_exists: bool = True
    ) -> Path:
        self._validate_uuid(batch_id)
        root = settings.batches_dir.resolve()
        candidate = (root / batch_id / Path(*parts)).resolve()
        if root not in candidate.parents:
            raise ValueError("Invalid batch path")
        if require_exists and not (root / batch_id).is_dir():
            raise BatchNotFoundError(batch_id)
        return candidate

    def invalidate_archive(self, batch_id: str) -> None:
        self.path(batch_id, "frameclean-results.zip").unlink(missing_ok=True)

    def build_archive(self, batch_id: str) -> Path:
        batch = self.get(batch_id)
        completed = [item for item in batch["items"] if item["status"] == "COMPLETE"]
        if not completed:
            raise BatchValidationError("No completed videos are ready to download.")
        target = self.path(batch_id, "frameclean-results.zip")
        temporary = target.with_suffix(".tmp.zip")
        temporary.unlink(missing_ok=True)
        used_names: set[str] = set()
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for item in completed:
                output = project_service.path(item["id"], "final.mp4")
                if not output.is_file():
                    continue
                base = project_service.sanitize_filename(
                    f"{item.get('name') or 'cleaned-video'}.mp4"
                )
                name = base
                suffix = 2
                while name.lower() in used_names:
                    stem = Path(base).stem
                    name = f"{stem}-{suffix}.mp4"
                    suffix += 1
                used_names.add(name.lower())
                archive.write(output, arcname=name)
        if not used_names:
            temporary.unlink(missing_ok=True)
            raise BatchValidationError("Completed output files are unavailable.")
        temporary.replace(target)
        return target

    def delete(self, batch_id: str) -> None:
        batch = self.get(batch_id)
        for item in batch["items"]:
            try:
                project_service.delete(item["id"])
            except ProjectNotFoundError:
                pass
        with connection() as db:
            db.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        directory = self.path(batch_id, require_exists=False)
        if directory.is_dir():
            shutil.rmtree(directory)

    @staticmethod
    def _derive_status(items: list[dict[str, Any]]) -> str:
        if not items:
            return "CREATED"
        statuses = {str(item["status"]) for item in items}
        terminal = {"COMPLETE", "FAILED", "CANCELLED"}
        if statuses == {"COMPLETE"}:
            return "COMPLETE"
        if statuses.issubset(terminal):
            if "COMPLETE" in statuses:
                return "PARTIAL_COMPLETE"
            if statuses == {"CANCELLED"}:
                return "CANCELLED"
            return "FAILED"
        active_statuses = statuses - {"FAILED", "CANCELLED"}
        if active_statuses & {"INPAINTING", "MUXING_AUDIO", "COMPLETE"}:
            return "PROCESSING"
        if active_statuses.issubset({"READY_FOR_MASK_REVIEW", "COMPLETE"}):
            return "READY_FOR_REVIEW"
        if "GENERATING_MASKS" in active_statuses:
            return "TRACKING"
        if active_statuses == {"READY_FOR_SELECTION"}:
            return "READY_FOR_SELECTION"
        return "PREPARING"

    @staticmethod
    def _pipeline_progress(item: dict[str, Any]) -> float:
        status = str(item["status"])
        job_progress = float(item.get("progress") or 0)
        if status in {"CREATED", "UPLOADING", "UPLOADED"}:
            return 0
        if status == "NORMALIZING":
            return job_progress * 0.15
        if status == "READY_FOR_SELECTION":
            return 15
        if status == "GENERATING_MASKS":
            return 15 + job_progress * 0.10
        if status == "READY_FOR_MASK_REVIEW":
            return 25
        if status in {"INPAINTING", "MUXING_AUDIO"}:
            return 25 + job_progress * 0.75
        if status in {"COMPLETE", "FAILED", "CANCELLED"}:
            return 100
        return 0

    @staticmethod
    def _validate_uuid(batch_id: str) -> None:
        try:
            parsed = uuid.UUID(batch_id)
        except (ValueError, AttributeError) as exc:
            raise BatchNotFoundError(batch_id) from exc
        if str(parsed) != batch_id.lower():
            raise BatchNotFoundError(batch_id)


batch_service = BatchService()
