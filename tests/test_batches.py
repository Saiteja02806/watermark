from __future__ import annotations

import json
import os
import zipfile

from fastapi.testclient import TestClient

os.environ["LVC_ALLOW_TEST_CLIENT"] = "1"

from apps.api.main import app  # noqa: E402
from apps.api.models import BatchSelectionRequest  # noqa: E402
from apps.api.services.batch_service import batch_service  # noqa: E402
from apps.api.services.project_service import project_service  # noqa: E402


def test_batch_selection_scales_to_each_video() -> None:
    with TestClient(app) as client:
        created = client.post("/api/batches", json={"name": "Watermark run"})
        assert created.status_code == 201
        batch_id = created.json()["id"]
        try:
            first = client.post(
                f"/api/batches/{batch_id}/projects",
                json={"name": "Portrait"},
            ).json()
            second = client.post(
                f"/api/batches/{batch_id}/projects",
                json={"name": "Landscape"},
            ).json()
            project_service.update(
                first["id"],
                status="READY_FOR_SELECTION",
                metadata={
                    "processingWidth": 400,
                    "processingHeight": 720,
                    "frameCount": 120,
                },
            )
            project_service.update(
                second["id"],
                status="READY_FOR_SELECTION",
                metadata={
                    "processingWidth": 800,
                    "processingHeight": 360,
                    "frameCount": 60,
                },
            )

            project_ids = batch_service.apply_selection(
                batch_id,
                BatchSelectionRequest(
                    referenceProjectId=first["id"],
                    frameIndex=60,
                    positivePoints=[[350, 650]],
                    negativePoints=[],
                    box=[320, 620, 380, 700],
                    fixed=True,
                ),
            )
            assert project_ids == [first["id"], second["id"]]

            scaled = json.loads(
                project_service.path(second["id"], "selection.json").read_text(
                    encoding="utf-8"
                )
            )
            assert scaled["frameIndex"] == 30
            assert scaled["positivePoints"] == [[700.0, 325.0]]
            assert scaled["box"] == [640.0, 310.0, 760.0, 350.0]

            batch = client.get(f"/api/batches/{batch_id}").json()
            assert batch["status"] == "READY_FOR_SELECTION"
            assert len(batch["items"]) == 2
        finally:
            client.delete(f"/api/batches/{batch_id}")


def test_batch_zip_contains_completed_outputs() -> None:
    with TestClient(app) as client:
        batch_id = client.post(
            "/api/batches", json={"name": "Exports"}
        ).json()["id"]
        try:
            for name in ("First", "Second"):
                project = client.post(
                    f"/api/batches/{batch_id}/projects", json={"name": name}
                ).json()
                project_service.path(project["id"], "final.mp4").write_bytes(
                    f"{name}-video".encode()
                )
                project_service.update(
                    project["id"],
                    status="COMPLETE",
                    metadata={
                        "outputWidth": 404,
                        "outputHeight": 720,
                        "outputFrameCount": 30,
                        "outputHasAudio": True,
                    },
                )

            response = client.get(f"/api/batches/{batch_id}/output.zip")
            assert response.status_code == 200
            archive = batch_service.path(batch_id, "frameclean-results.zip")
            with zipfile.ZipFile(archive) as zipped:
                assert zipped.namelist() == ["First.mp4", "Second.mp4"]
        finally:
            client.delete(f"/api/batches/{batch_id}")
