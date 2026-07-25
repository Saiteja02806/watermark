import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Health } from "../types";
import { FailureScreen } from "./FailureScreen";

const health: Health = {
  status: "ok",
  localOnly: false,
  ffmpeg: true,
  ffprobe: true,
  sam2: true,
  propainter: false,
  fallbackTracking: true,
  fallbackInpainting: true,
  details: {
    sam2: {
      source: true,
      runtime: true,
      checkpoint: true,
      ready: true,
    },
    propainter: {
      source: true,
      runtime: true,
      weights: {
        "raft-things.pth": true,
        "recurrent_flow_completion.pth": false,
        "ProPainter.pth": false,
      },
      ready: false,
      missing: [
        "weights (recurrent_flow_completion.pth, ProPainter.pth)",
      ],
    },
    acceleration: {
      cudaAvailable: true,
      gpuName: "NVIDIA GeForce RTX 5090",
      torchVersion: "2.7.1+cu128",
      error: null,
    },
  },
  limits: {
    maximumDurationSeconds: 15,
    maximumProcessingLongEdge: 720,
    selectedRegions: 1,
    activeJobs: 1,
    maximumBatchVideos: 20,
  },
};

describe("FailureScreen", () => {
  it("shows the worker error and truthful readiness checks", () => {
    const markup = renderToStaticMarkup(
      <FailureScreen
        error="ProPainter is not ready."
        health={health}
        onRetry={() => undefined}
      />,
    );

    expect(markup).toContain("Processing stopped");
    expect(markup).toContain("ProPainter is not ready.");
    expect(markup).toContain("Model weights");
    expect(markup).toContain("Missing");
    expect(markup).toContain("NVIDIA GeForce RTX 5090");
    expect(markup).not.toContain("Local worker active");
  });
});
