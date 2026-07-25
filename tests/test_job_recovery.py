from __future__ import annotations

import json

from apps.api.config import settings
from apps.api.database.sqlite import initialize_database, recover_interrupted_jobs
from apps.api.models import ProjectStatus, RenderRequest
from apps.api.services.process_service import ProcessSupervisor
from apps.api.services.project_service import project_service


def test_queued_render_keeps_request_for_restart(tmp_path, monkeypatch) -> None:
    original_data_dir = settings.data_dir
    object.__setattr__(settings, "data_dir", tmp_path)
    supervisor = ProcessSupervisor()
    monkeypatch.setattr(supervisor._executor, "submit", lambda *args: None)
    try:
        initialize_database()
        project = project_service.create("Restart-safe render")
        project_service.update(
            project["id"], status=ProjectStatus.READY_FOR_MASK_REVIEW
        )

        supervisor.render(project["id"], RenderRequest())

        request = json.loads(
            project_service.path(
                project["id"], "work", "render_request.json"
            ).read_text(encoding="utf-8")
        )
        assert request["resolution"] == "720p"

        interrupted = recover_interrupted_jobs()
        assert [(job["project_id"], job["job_type"]) for job in interrupted] == [
            (project["id"], "RENDER")
        ]
        assert supervisor.latest_job(project["id"])["status"] == "FAILED"
        assert project_service.get(project["id"])["status"] == (
            ProjectStatus.READY_FOR_MASK_REVIEW
        )
    finally:
        supervisor._executor.shutdown(wait=False)
        object.__setattr__(settings, "data_dir", original_data_dir)
