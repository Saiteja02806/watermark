from __future__ import annotations

import numpy as np
import pytest

from workers.sam2_worker.track_video import normalize_sam_mask


def test_normalize_sam_mask_removes_object_and_channel_axes() -> None:
    logits = np.array([[[True, False], [False, True]]], dtype=bool)

    mask = normalize_sam_mask(logits)

    assert mask.shape == (2, 2)
    assert mask.dtype == np.uint8
    assert mask.tolist() == [[255, 0], [0, 255]]


def test_normalize_sam_mask_rejects_non_image_output() -> None:
    with pytest.raises(ValueError, match="unsupported mask shape"):
        normalize_sam_mask(np.zeros((2, 2, 3), dtype=bool))
