from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

from ..config import settings


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(settings.database_path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize_database() -> None:
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    settings.batches_dir.mkdir(parents=True, exist_ok=True)
    with connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT NOT NULL,
                original_filename TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                current_frame INTEGER,
                total_frames INTEGER,
                message TEXT,
                pid INTEGER,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_project_updated
            ON jobs(project_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS batch_items (
                batch_id TEXT NOT NULL,
                project_id TEXT NOT NULL UNIQUE,
                position INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (batch_id, project_id),
                FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_batch_items_position
            ON batch_items(batch_id, position);
            """
        )


def recover_interrupted_jobs() -> list[dict[str, Any]]:
    """Mark orphaned jobs and return them in their original queue order."""
    with connection() as db:
        rows = db.execute(
            """
            SELECT id, project_id, job_type, created_at
            FROM jobs
            WHERE status IN ('QUEUED', 'RUNNING')
            ORDER BY created_at
            """
        ).fetchall()
        if not rows:
            return []
        now = utc_now()
        for row in rows:
            fallback_status = {
                "NORMALIZE": "UPLOADED",
                "TRACK": "READY_FOR_SELECTION",
                "RENDER": "READY_FOR_MASK_REVIEW",
            }.get(row["job_type"], "FAILED")
            db.execute(
                """
                UPDATE jobs
                SET status = 'FAILED', message = ?,
                    error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    "Interrupted by a server restart; rescheduling",
                    "The worker stopped when the server restarted.",
                    now,
                    row["id"],
                ),
            )
            db.execute(
                """
                UPDATE projects
                SET status = ?, error_message = NULL, updated_at = ?
                WHERE id = ?
                """,
                (fallback_status, now, row["project_id"]),
            )
        return [dict(row) for row in rows]


def row_to_project(row: sqlite3.Row) -> dict[str, Any]:
    metadata = json.loads(row["metadata_json"] or "{}")
    return {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "originalFilename": row["original_filename"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "error": row["error_message"],
        **metadata,
    }
