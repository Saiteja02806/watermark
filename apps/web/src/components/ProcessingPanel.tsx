import { CircleStop, LoaderCircle } from "lucide-react";
import type { ProgressEvent, ProjectStatus } from "../types";

interface ProcessingPanelProps {
  progress: ProgressEvent | null;
  status: ProjectStatus;
  onCancel: () => void;
}

export function ProcessingPanel({
  progress,
  status,
  onCancel,
}: ProcessingPanelProps) {
  const processing = [
    "NORMALIZING",
    "GENERATING_MASKS",
    "INPAINTING",
    "MUXING_AUDIO",
  ].includes(status);
  if (!processing) return null;
  const value = progress?.progress ?? 0;
  return (
    <div className="processing-card" role="status" aria-live="polite">
      <div className="processing-card__icon">
        <LoaderCircle size={20} />
      </div>
      <div className="processing-card__copy">
        <span>{stageLabel(status)}</span>
        <strong>{progress?.message ?? "Starting the local worker"}</strong>
        <div
          className="progress-track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={value}
        >
          <span style={{ width: `${value}%` }} />
        </div>
        <small>
          {progress?.currentFrame !== undefined && progress.totalFrames
            ? `Frame ${progress.currentFrame + 1} of ${progress.totalFrames}`
            : `${value}% complete`}
        </small>
      </div>
      <button className="button button--quiet" type="button" onClick={onCancel}>
        <CircleStop size={15} />
        Cancel
      </button>
    </div>
  );
}

function stageLabel(status: ProjectStatus) {
  if (status === "NORMALIZING") return "Preparing media";
  if (status === "GENERATING_MASKS") return "Tracking region";
  if (status === "MUXING_AUDIO") return "Final assembly";
  return "Reconstructing background";
}

