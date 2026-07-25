from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

os.environ["LVC_ALLOW_TEST_CLIENT"] = "1"

from apps.api.config import settings  # noqa: E402
from apps.api.main import app  # noqa: E402
from apps.api.services.project_service import project_service  # noqa: E402


def _make_test_video(directory: Path, frame_count: int = 36) -> Path:
    frames = directory / "source_frames"
    frames.mkdir()
    height, width = 180, 320
    x_gradient = np.linspace(25, 150, width, dtype=np.uint8)
    for index in range(frame_count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = x_gradient
        frame[:, :, 1] = np.flip(x_gradient)
        frame[:, :, 2] = 48
        x = 40 + index * 2
        cv2.rectangle(frame, (x, 62), (x + 48, 112), (30, 40, 238), -1)
        cv2.putText(
            frame,
            str(index),
            (8, 170),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (220, 220, 220),
            1,
            cv2.LINE_AA,
        )
        assert cv2.imwrite(str(frames / f"{index:06d}.png"), frame)

    output = directory / "moving-object-with-audio.mp4"
    completed = subprocess.run(
        [
            str(settings.ffmpeg_path),
            "-y",
            "-framerate",
            "30",
            "-start_number",
            "0",
            "-i",
            str(frames / "%06d.png"),
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={frame_count / 30}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return output


def _wait_for(
    client: TestClient,
    project_id: str,
    statuses: set[str],
    timeout: float = 60,
) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in statuses:
            return last
        time.sleep(0.15)
    raise AssertionError(f"Timed out waiting for {statuses}; last project: {last}")


def test_upload_track_render_and_restore_audio(tmp_path: Path) -> None:
    source = _make_test_video(tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/projects", json={"name": "Synthetic motion proof"}
        )
        assert created.status_code == 201
        project_id = created.json()["id"]
        project_dir = project_service.path(project_id)
        try:
            with source.open("rb") as stream:
                uploaded = client.post(
                    f"/api/projects/{project_id}/upload",
                    files={"file": (source.name, stream, "video/mp4")},
                )
            assert uploaded.status_code == 202, uploaded.text
            ready = _wait_for(
                client, project_id, {"READY_FOR_SELECTION", "FAILED"}, timeout=45
            )
            assert ready["status"] == "READY_FOR_SELECTION", ready.get("error")
            assert ready["frameCount"] == 36
            assert ready["processingWidth"] == 320
            assert ready["processingHeight"] == 180
            assert ready["hasAudio"] is True
            assert (project_dir / "proxy.mp4").is_file()
            assert len(list((project_dir / "frames").glob("*.png"))) == 36

            selection = client.post(
                f"/api/projects/{project_id}/selection",
                json={
                    "frameIndex": 0,
                    "positivePoints": [[62, 86]],
                    "negativePoints": [],
                    "box": [34, 56, 96, 118],
                },
            )
            assert selection.status_code == 200, selection.text
            tracked = client.post(
                f"/api/projects/{project_id}/track",
                json={"direction": "both", "engine": "opencv"},
            )
            assert tracked.status_code == 202, tracked.text
            review = _wait_for(
                client, project_id, {"READY_FOR_MASK_REVIEW", "FAILED"}, timeout=45
            )
            assert review["status"] == "READY_FOR_MASK_REVIEW", review.get("error")
            assert review["trackerEngine"] == "opencv"
            assert len(list((project_dir / "masks" / "raw").glob("*.png"))) == 36
            first_mask = cv2.imread(
                str(project_dir / "masks" / "raw" / "000000.png"),
                cv2.IMREAD_GRAYSCALE,
            )
            assert first_mask is not None and int(np.count_nonzero(first_mask)) > 0

            rendered = client.post(
                f"/api/projects/{project_id}/render",
                json={
                    "quality": "fast",
                    "resolution": "480p",
                    "maskExpansion": 2,
                    "preserveAudio": True,
                    "engine": "opencv",
                },
            )
            assert rendered.status_code == 202, rendered.text
            complete = _wait_for(
                client, project_id, {"COMPLETE", "FAILED"}, timeout=60
            )
            assert complete["status"] == "COMPLETE", complete.get("error")
            assert complete["inpaintingEngine"] == "opencv"
            assert complete["outputHasAudio"] is True
            assert abs(complete["outputDurationSeconds"] - 1.2) < 0.15
            output = project_dir / "final.mp4"
            assert output.is_file() and output.stat().st_size > 10_000
            report = json.loads(
                (project_dir / "quality_report.json").read_text(encoding="utf-8")
            )
            assert report["valid"] is True

            download = client.get(f"/api/projects/{project_id}/output")
            assert download.status_code == 200
            assert download.headers["content-type"].startswith("video/mp4")
        finally:
            client.delete(f"/api/projects/{project_id}")
        assert not project_dir.exists()

