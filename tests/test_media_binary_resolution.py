from __future__ import annotations

from pathlib import Path

from apps.api import config


def _write_binary(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test binary")
    return path


def test_linux_resolver_never_selects_windows_media_binaries(
    tmp_path: Path, monkeypatch
) -> None:
    windows_probe = _write_binary(
        tmp_path
        / "node_modules"
        / "ffprobe-static"
        / "bin"
        / "win32"
        / "x64"
        / "ffprobe.exe"
    )
    linux_probe = _write_binary(
        tmp_path
        / "node_modules"
        / "ffprobe-static"
        / "bin"
        / "linux"
        / "x64"
        / "ffprobe"
    )
    _write_binary(tmp_path / "node_modules" / "ffmpeg-static" / "ffmpeg.exe")
    linux_ffmpeg = _write_binary(
        tmp_path / "node_modules" / "ffmpeg-static" / "ffmpeg"
    )
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.delenv("FFPROBE_PATH", raising=False)
    monkeypatch.setattr(config.shutil, "which", lambda _: None)

    resolved_probe = config._resolve_binary(
        "FFPROBE_PATH",
        "ffprobe",
        config._ffprobe_candidates(tmp_path, "linux", "x86_64"),
    )
    resolved_ffmpeg = config._resolve_binary(
        "FFMPEG_PATH",
        "ffmpeg",
        config._ffmpeg_candidates(tmp_path, "linux"),
    )

    assert resolved_probe == linux_probe.resolve()
    assert resolved_probe != windows_probe.resolve()
    assert resolved_ffmpeg == linux_ffmpeg.resolve()


def test_windows_resolver_selects_windows_media_binaries(
    tmp_path: Path, monkeypatch
) -> None:
    windows_probe = _write_binary(
        tmp_path
        / "node_modules"
        / "ffprobe-static"
        / "bin"
        / "win32"
        / "x64"
        / "ffprobe.exe"
    )
    windows_ffmpeg = _write_binary(
        tmp_path / "node_modules" / "ffmpeg-static" / "ffmpeg.exe"
    )
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.delenv("FFPROBE_PATH", raising=False)
    monkeypatch.setattr(config.shutil, "which", lambda _: None)

    resolved_probe = config._resolve_binary(
        "FFPROBE_PATH",
        "ffprobe",
        config._ffprobe_candidates(tmp_path, "win32", "AMD64"),
    )
    resolved_ffmpeg = config._resolve_binary(
        "FFMPEG_PATH",
        "ffmpeg",
        config._ffmpeg_candidates(tmp_path, "win32"),
    )

    assert resolved_probe == windows_probe.resolve()
    assert resolved_ffmpeg == windows_ffmpeg.resolve()
