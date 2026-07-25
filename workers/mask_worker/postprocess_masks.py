from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def postprocess(
    raw_dir: Path,
    corrected_dir: Path,
    final_dir: Path,
    frame_count: int,
    expansion: int,
) -> list[Path]:
    final_dir.mkdir(parents=True, exist_ok=True)
    for stale in final_dir.glob("*.png"):
        stale.unlink()
    kernel = np.ones((3, 3), np.uint8)
    dilation_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (expansion * 2 + 1, expansion * 2 + 1)
    )
    written: list[Path] = []
    for index in range(frame_count):
        corrected = corrected_dir / f"{index:06d}.png"
        raw = raw_dir / f"{index:06d}.png"
        source = corrected if corrected.is_file() else raw
        if not source.is_file():
            raise FileNotFoundError(f"Mask {index:06d}.png is missing")
        mask = cv2.imread(str(source), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise ValueError(f"Mask {source.name} cannot be decoded")
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        if expansion:
            mask = cv2.dilate(mask, dilation_kernel, iterations=1)
        target = final_dir / f"{index:06d}.png"
        if not cv2.imwrite(str(target), mask):
            raise OSError(f"Could not write {target}")
        written.append(target)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    paths = postprocess(
        Path(payload["rawMasksPath"]),
        Path(payload["correctedMasksPath"]),
        Path(payload["finalMasksPath"]),
        int(payload["frameCount"]),
        int(payload.get("maskExpansion", 0)),
    )
    print(json.dumps({"type": "result", "masks": len(paths)}), flush=True)


if __name__ == "__main__":
    main()

