from __future__ import annotations

import shutil
from pathlib import Path

from workers.inpainting_worker import run_propainter as runner
from workers.inpainting_worker.run_propainter import propainter_preset


def test_balanced_propainter_preset_fits_six_gb_gpu() -> None:
    neighbor, stride, subvideo = propainter_preset("balanced")

    assert neighbor == 4
    assert stride == 20
    assert subvideo == 10


def test_unknown_quality_uses_balanced_preset() -> None:
    assert propainter_preset("unexpected") == propainter_preset("balanced")


def test_chunk_size_can_be_tuned_for_runpod(monkeypatch) -> None:
    monkeypatch.setenv("LVC_PROPAINTER_CHUNK_CORE_FRAMES", "24")
    monkeypatch.setenv("LVC_PROPAINTER_CHUNK_CONTEXT_FRAMES", "2")
    assert runner.propainter_chunk_sizes() == (24, 2)


def test_chunked_runner_reassembles_every_frame(
    tmp_path: Path,
    monkeypatch,
) -> None:
    frames = tmp_path / "frames"
    masks = tmp_path / "masks"
    save_root = tmp_path / "output"
    frames.mkdir()
    masks.mkdir()
    save_root.mkdir()
    for index in range(21):
        (frames / f"{index:06d}.png").write_bytes(b"frame")
        (masks / f"{index:06d}.png").write_bytes(b"mask")

    def fake_invoke(
        payload,
        video,
        chunk_masks,
        output,
        *,
        save_frames,
    ):
        assert save_frames is True
        rendered = output / video.name / "frames"
        rendered.mkdir(parents=True)
        for source in sorted(video.glob("*.png")):
            shutil.copy2(source, rendered / source.name)

    def fake_encode(payload, combined, output):
        output.write_bytes(b"video")

    monkeypatch.setattr(runner, "_invoke_propainter", fake_invoke)
    monkeypatch.setattr(runner, "_encode_frames", fake_encode)

    result = runner._run_chunked(
        {
            "framesPath": str(frames),
            "finalMasksPath": str(masks),
            "quality": "balanced",
            "width": 404,
            "height": 720,
            "fps": 30,
        },
        save_root,
    )

    assert result.read_bytes() == b"video"
    assert len(list((save_root / "combined_frames").glob("*.png"))) == 21
