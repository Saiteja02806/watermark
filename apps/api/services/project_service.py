from __future__ import annotations

import base64
import binascii
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from PIL import Image

from ..config import settings
from ..database.sqlite import connection, row_to_project, utc_now
from ..models import ProjectStatus


ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


class ProjectNotFoundError(LookupError):
    pass


class InvalidUploadError(ValueError):
    pass


class ProjectService:
    def create(self, name: str | None = None) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        now = utc_now()
        project_dir = self.path(project_id, require_exists=False)
        for relative in (
            "thumbnails",
            "frames",
            "masks/raw",
            "masks/corrected",
            "masks/final",
            "previews",
            "logs",
            "work/inpainted_frames",
        ):
            (project_dir / relative).mkdir(parents=True, exist_ok=True)

        with connection() as db:
            db.execute(
                """
                INSERT INTO projects
                    (id, name, status, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, '{}', ?, ?)
                """,
                (project_id, name, ProjectStatus.CREATED, now, now),
            )
        project = self.get(project_id)
        self._write_snapshot(project)
        return project

    def get(self, project_id: str) -> dict[str, Any]:
        self._validate_uuid(project_id)
        with connection() as db:
            row = db.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(project_id)
        return row_to_project(row)

    def update(
        self,
        project_id: str,
        *,
        status: ProjectStatus | str | None = None,
        metadata: dict[str, Any] | None = None,
        original_filename: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        current = self.get(project_id)
        merged_metadata = {
            key: value
            for key, value in current.items()
            if key
            not in {
                "id",
                "name",
                "status",
                "originalFilename",
                "createdAt",
                "updatedAt",
                "error",
            }
        }
        if metadata:
            merged_metadata.update(metadata)
        new_status = str(status or current["status"])
        if isinstance(status, ProjectStatus):
            new_status = status.value
        filename = (
            self.sanitize_filename(original_filename)
            if original_filename is not None
            else current.get("originalFilename")
        )
        now = utc_now()
        with connection() as db:
            db.execute(
                """
                UPDATE projects
                SET status = ?, original_filename = ?, metadata_json = ?,
                    error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_status,
                    filename,
                    json.dumps(merged_metadata),
                    error,
                    now,
                    project_id,
                ),
            )
        project = self.get(project_id)
        self._write_snapshot(project)
        return project

    def path(
        self, project_id: str, *parts: str, require_exists: bool = True
    ) -> Path:
        self._validate_uuid(project_id)
        root = settings.projects_dir.resolve()
        candidate = (root / project_id / Path(*parts)).resolve()
        if root not in candidate.parents:
            raise ValueError("Invalid project path")
        if require_exists and not (root / project_id).is_dir():
            raise ProjectNotFoundError(project_id)
        return candidate

    def save_upload(
        self, project_id: str, stream: BinaryIO, filename: str, content_length: int | None
    ) -> Path:
        safe_name = self.sanitize_filename(filename)
        extension = Path(safe_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise InvalidUploadError(
                "Unsupported video format. Use MP4, MOV, M4V, WebM, AVI, or MKV."
            )
        if content_length and content_length > settings.max_upload_bytes:
            raise InvalidUploadError("The selected file is larger than the 1 GB limit.")

        project_dir = self.path(project_id)
        target = project_dir / f"original{extension}"
        written = 0
        with target.open("wb") as destination:
            while chunk := stream.read(1024 * 1024):
                written += len(chunk)
                if written > settings.max_upload_bytes:
                    destination.close()
                    target.unlink(missing_ok=True)
                    raise InvalidUploadError(
                        "The selected file is larger than the 1 GB limit."
                    )
                destination.write(chunk)
        if written == 0:
            target.unlink(missing_ok=True)
            raise InvalidUploadError("The selected file is empty.")
        self.update(
            project_id,
            status=ProjectStatus.UPLOADED,
            original_filename=safe_name,
            metadata={"originalStoredAs": target.name, "uploadBytes": written},
        )
        return target

    def find_original(self, project_id: str) -> Path:
        project_dir = self.path(project_id)
        matches = list(project_dir.glob("original.*"))
        if len(matches) != 1:
            raise FileNotFoundError("Original video is unavailable")
        return matches[0]

    def save_data_url_mask(
        self, project_id: str, frame_index: int, data_url: str, subdir: str
    ) -> Path:
        if not data_url.startswith("data:image/png;base64,"):
            raise ValueError("Mask must be a base64-encoded PNG")
        try:
            payload = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Mask PNG is not valid base64 data") from exc
        if len(payload) > 32 * 1024 * 1024:
            raise ValueError("Mask PNG is too large")

        project = self.get(project_id)
        expected_size = (
            int(project.get("processingWidth") or 0),
            int(project.get("processingHeight") or 0),
        )
        target = self.path(
            project_id, "masks", subdir, f"{frame_index:06d}.png"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp.png")
        temporary.write_bytes(payload)
        try:
            with Image.open(temporary) as image:
                image.verify()
            with Image.open(temporary) as image:
                if expected_size != (0, 0) and image.size != expected_size:
                    raise ValueError(
                        f"Mask dimensions must be {expected_size[0]}×{expected_size[1]}"
                    )
                image.convert("L").point(lambda p: 255 if p >= 128 else 0).save(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def delete(self, project_id: str) -> None:
        project_dir = self.path(project_id)
        root = settings.projects_dir.resolve()
        resolved = project_dir.resolve()
        if resolved.parent != root:
            raise ValueError("Refusing to delete an unexpected path")
        with connection() as db:
            db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        shutil.rmtree(resolved)

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        basename = Path(filename.replace("\\", "/")).name
        cleaned = SAFE_FILENAME.sub("_", basename).strip(" .")
        if not cleaned:
            cleaned = "video.mp4"
        return cleaned[:180]

    @staticmethod
    def _validate_uuid(project_id: str) -> None:
        try:
            parsed = uuid.UUID(project_id)
        except (ValueError, AttributeError) as exc:
            raise ProjectNotFoundError(project_id) from exc
        if str(parsed) != project_id.lower():
            raise ProjectNotFoundError(project_id)

    def _write_snapshot(self, project: dict[str, Any]) -> None:
        path = self.path(project["id"], "project.json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(project, indent=2), encoding="utf-8")
        temporary.replace(path)


project_service = ProjectService()

