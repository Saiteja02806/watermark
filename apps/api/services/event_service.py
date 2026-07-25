from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from .process_service import process_supervisor
from .project_service import ProjectNotFoundError, project_service


async def project_events(project_id: str) -> AsyncIterator[str]:
    previous = ""
    heartbeats = 0
    while True:
        try:
            project = project_service.get(project_id)
        except ProjectNotFoundError:
            yield "event: deleted\ndata: {}\n\n"
            return
        job = process_supervisor.latest_job(project_id)
        payload = {
            "projectId": project_id,
            "status": project["status"],
            "stage": project["status"],
            "progress": int(job["progress"]) if job else 0,
            "currentFrame": job.get("current_frame") if job else None,
            "totalFrames": job.get("total_frames") if job else project.get("frameCount"),
            "message": (
                job.get("error_message")
                or job.get("message")
                or project.get("error")
                or project["status"].replace("_", " ").title()
            )
            if job
            else project.get("error") or project["status"].replace("_", " ").title(),
            "jobStatus": job.get("status") if job else None,
            "error": project.get("error"),
        }
        serialized = json.dumps(payload, separators=(",", ":"))
        if serialized != previous:
            yield f"data: {serialized}\n\n"
            previous = serialized
            heartbeats = 0
        else:
            heartbeats += 1
            if heartbeats >= 25:
                yield ": keep-alive\n\n"
                heartbeats = 0
        await asyncio.sleep(0.4)

