from __future__ import annotations

import os
import subprocess
import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

os.environ["LVC_ALLOW_TEST_CLIENT"] = "1"

from apps.api.config import settings  # noqa: E402
from apps.api.main import app  # noqa: E402
from apps.api.services.project_service import project_service  # noqa: E402


def _write_watermarked_frames(project_id: str, frame_count: int = 18) -> None:
    frames_dir = project_service.path(project_id, "frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    width, height = 180, 120
    for index in range(frame_count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        gradient = (np.arange(width, dtype=np.uint16) + index * 9) % 150
        frame[:, :, 0] = (30 + gradient).astype(np.uint8)
        frame[:, :, 1] = np.flip(gradient).astype(np.uint8)
        frame[:, :, 2] = 80
        cv2.circle(frame, (30 + index * 5, 44), 18, (210, 80, 35), -1)
        cv2.putText(
            frame,
            "WM",
            (122, 98),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (245, 245, 245),
            2,
            cv2.LINE_AA,
        )
        assert cv2.imwrite(str(frames_dir / f"{index:06d}.png"), frame)


def _encode_original(project_id: str) -> None:
    project_dir = project_service.path(project_id)
    completed = subprocess.run(
        [
            str(settings.ffmpeg_path),
            "-y",
            "-framerate",
            "30",
            "-start_number",
            "0",
            "-i",
            str(project_dir / "frames" / "%06d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(project_dir / "original.mp4"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _wait_for(
    client: TestClient,
    project_id: str,
    statuses: set[str],
    timeout: float = 45,
) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in statuses:
            return last
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {statuses}; last project: {last}")


def _mark_project_ready(project_id: str) -> None:
    project_service.update(
        project_id,
        status="READY_FOR_SELECTION",
        original_filename="original.mp4",
        metadata={
            "processingWidth": 180,
            "processingHeight": 120,
            "width": 180,
            "height": 120,
            "frameCount": 18,
            "fps": 30,
            "durationSeconds": 0.6,
            "hasAudio": False,
        },
    )


def test_auto_watermark_detection_saves_compact_mask() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Auto watermark"}).json()
        project_id = project["id"]
        try:
            _write_watermarked_frames(project_id)
            _mark_project_ready(project_id)

            response = client.post(f"/api/projects/{project_id}/watermark/auto")
            assert response.status_code == 200, response.text
            detected = response.json()
            box = detected["box"]
            assert box[0] >= 110
            assert box[1] >= 74
            assert box[2] <= 178
            assert box[3] <= 112
            assert 0 < detected["areaRatio"] < 0.08

            selection = detected["selection"]
            mask = cv2.imread(selection["manualMaskPath"], cv2.IMREAD_GRAYSCALE)
            assert mask is not None
            assert int(np.count_nonzero(mask[72:112, 112:178])) > 100
            assert (project_service.path(project_id, "selection.json")).is_file()
        finally:
            client.delete(f"/api/projects/{project_id}")


def test_auto_watermark_track_and_render_reduces_overlay_pixels() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Auto repair"}).json()
        project_id = project["id"]
        project_dir = project_service.path(project_id)
        try:
            _write_watermarked_frames(project_id)
            _encode_original(project_id)
            _mark_project_ready(project_id)

            detected = client.post(
                f"/api/projects/{project_id}/watermark/auto"
            )
            assert detected.status_code == 200, detected.text
            tracked = client.post(
                f"/api/projects/{project_id}/track",
                json={"direction": "both", "engine": "fixed"},
            )
            assert tracked.status_code == 202, tracked.text
            review = _wait_for(
                client, project_id, {"READY_FOR_MASK_REVIEW", "FAILED"}
            )
            assert review["status"] == "READY_FOR_MASK_REVIEW", review.get("error")

            rendered = client.post(
                f"/api/projects/{project_id}/render",
                json={
                    "quality": "fast",
                    "resolution": "480p",
                    "maskExpansion": 4,
                    "preserveAudio": False,
                    "engine": "opencv",
                },
            )
            assert rendered.status_code == 202, rendered.text
            complete = _wait_for(client, project_id, {"COMPLETE", "FAILED"})
            assert complete["status"] == "COMPLETE", complete.get("error")

            source = cv2.imread(str(project_dir / "frames" / "000000.png"))
            repaired = cv2.imread(
                str(project_dir / "work" / "inpainted_frames" / "000000.png")
            )
            mask = cv2.imread(
                str(project_dir / "masks" / "final" / "000000.png"),
                cv2.IMREAD_GRAYSCALE,
            )
            assert source is not None and repaired is not None and mask is not None
            selected = mask >= 128
            assert selected.any()
            source_mean = float(np.mean(source[selected]))
            repaired_mean = float(np.mean(repaired[selected]))
            assert repaired_mean < source_mean - 20
            assert repaired_mean > 15
            assert (project_dir / "final.mp4").is_file()
        finally:
            client.delete(f"/api/projects/{project_id}")


def test_negative_only_prompt_is_rejected() -> None:
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Negative only"}).json()
        project_id = project["id"]
        try:
            project_service.update(
                project_id,
                status="READY_FOR_SELECTION",
                metadata={
                    "processingWidth": 64,
                    "processingHeight": 48,
                    "frameCount": 1,
                },
            )
            response = client.post(
                f"/api/projects/{project_id}/selection",
                json={
                    "frameIndex": 0,
                    "positivePoints": [],
                    "negativePoints": [[10, 10]],
                    "box": None,
                    "manualMaskDataUrl": None,
                },
            )
            assert response.status_code == 400
            assert "positive point" in response.json()["detail"]
        finally:
            client.delete(f"/api/projects/{project_id}")
