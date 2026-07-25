from __future__ import annotations

import pytest

from apps.api.services.render_dimensions import output_dimensions


def test_720p_preserves_portrait_working_resolution() -> None:
    assert output_dimensions(404, 720, "720p") == (404, 720)


def test_480p_scales_portrait_to_even_dimensions() -> None:
    assert output_dimensions(404, 720, "480p") == (270, 480)


def test_resolution_never_upscales_small_video() -> None:
    assert output_dimensions(320, 180, "720p") == (320, 180)


def test_unknown_resolution_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported output resolution"):
        output_dimensions(404, 720, "1080p")
