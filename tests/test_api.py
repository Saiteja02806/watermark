from __future__ import annotations

import base64
import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

os.environ["LVC_ALLOW_TEST_CLIENT"] = "1"

from apps.api.main import app  # noqa: E402
from apps.api.services.project_service import project_service  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_local_only_and_media_tools(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["localOnly"] is True
    assert payload["ffmpeg"] is True
    assert payload["ffprobe"] is True
    assert payload["limits"]["maximumDurationSeconds"] == 15


def test_project_lifecycle_and_filename_sanitization(client: TestClient) -> None:
    created = client.post("/api/projects", json={"name": "Private repair"})
    assert created.status_code == 201
    project = created.json()
    project_id = project["id"]
    project_path = project_service.path(project_id)
    assert project_path.is_dir()
    try:
        invalid = client.post(
            f"/api/projects/{project_id}/upload",
            files={"file": ("../../not-video.txt", b"nope", "text/plain")},
        )
        assert invalid.status_code == 400
        assert "Unsupported video format" in invalid.json()["detail"]
        assert not (project_path.parent / "not-video.txt").exists()
    finally:
        deleted = client.delete(f"/api/projects/{project_id}")
        assert deleted.status_code == 204
    assert not project_path.exists()


def test_mask_data_url_is_dimension_checked(client: TestClient) -> None:
    project = client.post("/api/projects", json={"name": "Mask"}).json()
    project_id = project["id"]
    try:
        project_service.update(
            project_id,
            metadata={
                "processingWidth": 64,
                "processingHeight": 48,
                "frameCount": 1,
            },
        )
        image = Image.new("L", (64, 48), color=0)
        for x in range(12, 32):
            for y in range(10, 30):
                image.putpixel((x, y), 255)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        response = client.post(
            f"/api/projects/{project_id}/selection",
            json={
                "frameIndex": 0,
                "positivePoints": [],
                "negativePoints": [],
                "box": None,
                "manualMaskDataUrl": f"data:image/png;base64,{encoded}",
            },
        )
        assert response.status_code == 200
        saved = project_service.path(
            project_id, "masks", "corrected", "000000.png"
        )
        assert saved.is_file()

        wrong = Image.new("L", (32, 24), color=255)
        buffer = io.BytesIO()
        wrong.save(buffer, format="PNG")
        wrong_encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        response = client.post(
            f"/api/projects/{project_id}/selection",
            json={
                "frameIndex": 0,
                "manualMaskDataUrl": f"data:image/png;base64,{wrong_encoded}",
            },
        )
        assert response.status_code == 400
        assert "Mask dimensions must be 64×48" in response.json()["detail"]
    finally:
        client.delete(f"/api/projects/{project_id}")

