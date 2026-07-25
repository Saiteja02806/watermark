import { ChevronLeft, ChevronRight, Flag } from "lucide-react";
import type { Project } from "../types";
import { formatTime, frameToTime } from "../utils/coordinates";
import { FrameStrip } from "./FrameStrip";

interface VideoTimelineProps {
  project: Project;
  frameIndex: number;
  onFrame: (frame: number) => void;
}

export function VideoTimeline({
  project,
  frameIndex,
  onFrame,
}: VideoTimelineProps) {
  const count = Math.max(1, project.frameCount ?? 1);
  const fps = project.fps || 30;
  const suspicious = project.suspiciousFrames ?? [];
  const nextSuspicious = (direction: -1 | 1) => {
    const ordered = [...suspicious].sort((a, b) => a - b);
    const target =
      direction === 1
        ? ordered.find((frame) => frame > frameIndex)
        : ordered.reverse().find((frame) => frame < frameIndex);
    if (target !== undefined) onFrame(target);
  };

  return (
    <section className="timeline-panel" aria-label="Video timeline">
      <div className="timeline-panel__top">
        <div className="timecode">
          <strong>{formatTime(frameToTime(frameIndex, fps))}</strong>
          <span>/ {formatTime(project.durationSeconds)}</span>
        </div>
        {suspicious.length > 0 && (
          <div className="review-nav">
            <Flag size={14} />
            <span>{suspicious.length} flagged</span>
            <button
              className="icon-button"
              type="button"
              onClick={() => nextSuspicious(-1)}
              title="Previous flagged frame"
            >
              <ChevronLeft size={15} />
            </button>
            <button
              className="icon-button"
              type="button"
              onClick={() => nextSuspicious(1)}
              title="Next flagged frame"
            >
              <ChevronRight size={15} />
            </button>
          </div>
        )}
      </div>
      <div className="timeline-track">
        <input
          type="range"
          min="0"
          max={count - 1}
          step="1"
          value={Math.min(frameIndex, count - 1)}
          onChange={(event) => onFrame(Number(event.currentTarget.value))}
          aria-label="Current video frame"
        />
        <div className="timeline-markers" aria-hidden="true">
          {suspicious.map((frame) => (
            <span
              key={frame}
              style={{ left: `${(frame / Math.max(1, count - 1)) * 100}%` }}
            />
          ))}
        </div>
      </div>
      <FrameStrip
        project={project}
        frameIndex={frameIndex}
        onFrame={onFrame}
      />
    </section>
  );
}

