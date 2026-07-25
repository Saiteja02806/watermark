import {
  CheckCircle2,
  CircleX,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import type { Health } from "../types";

interface FailureScreenProps {
  error?: string;
  health: Health | null;
  onRetry: () => void;
}

export function FailureScreen({
  error,
  health,
  onRetry,
}: FailureScreenProps) {
  const propainter = health?.details?.propainter;
  const acceleration = health?.details?.acceleration;
  const weightsReady = propainter
    ? Object.values(propainter.weights).every(Boolean)
    : false;
  const checks = [
    { label: "ProPainter source", ready: Boolean(propainter?.source) },
    { label: "Python runtime", ready: Boolean(propainter?.runtime) },
    { label: "Model weights", ready: weightsReady },
    { label: "CUDA GPU", ready: Boolean(acceleration?.cudaAvailable) },
  ];

  return (
    <main className="failure-workspace">
      <div className="failure-visual" aria-hidden="true">
        <TriangleAlert size={46} />
      </div>
      <section className="failure-copy" aria-labelledby="failure-title">
        <p className="eyebrow">Processing stopped</p>
        <h1 id="failure-title">The repair did not complete.</h1>
        <p className="failure-message" role="alert">
          {error ?? "The worker stopped before it produced an output video."}
        </p>

        {propainter && !propainter.ready && (
          <div className="readiness-card">
            <strong>RunPod readiness</strong>
            <ul>
              {checks.map((check) => (
                <li key={check.label} data-ready={check.ready}>
                  {check.ready ? (
                    <CheckCircle2 size={15} />
                  ) : (
                    <CircleX size={15} />
                  )}
                  <span>{check.label}</span>
                  <small>{check.ready ? "Ready" : "Missing"}</small>
                </li>
              ))}
            </ul>
            {acceleration?.gpuName && (
              <p>
                Detected {acceleration.gpuName}
                {acceleration.torchVersion
                  ? ` with PyTorch ${acceleration.torchVersion}`
                  : ""}
                .
              </p>
            )}
          </div>
        )}

        <div className="failure-actions">
          <button
            className="button button--primary"
            type="button"
            onClick={onRetry}
          >
            <RotateCcw size={16} />
            Review settings and retry
          </button>
          <p>
            Retry after the health check reports ProPainter ready, or choose the
            OpenCV fallback for a faster lower-quality proof.
          </p>
        </div>
      </section>
    </main>
  );
}
