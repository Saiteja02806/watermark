from __future__ import annotations


def output_dimensions(
    width: int,
    height: int,
    resolution: str,
) -> tuple[int, int]:
    """Fit inside the requested long edge without upscaling the source."""
    if width <= 0 or height <= 0:
        raise ValueError("Video dimensions must be positive")
    target_long_edge = {"480p": 480, "720p": 720}.get(resolution)
    if target_long_edge is None:
        raise ValueError(f"Unsupported output resolution: {resolution}")
    source_long_edge = max(width, height)
    if source_long_edge <= target_long_edge:
        return width, height
    scale = target_long_edge / source_long_edge
    target_width = max(2, round(width * scale / 2) * 2)
    target_height = max(2, round(height * scale / 2) * 2)
    return target_width, target_height
