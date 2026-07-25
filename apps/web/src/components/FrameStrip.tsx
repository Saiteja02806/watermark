import type { Project } from "../types";
import { api } from "../api/client";

interface FrameStripProps {
  project: Project;
  frameIndex: number;
  onFrame: (frame: number) => void;
}

export function FrameStrip({ project, frameIndex, onFrame }: FrameStripProps) {
  const count = project.frameCount ?? 1;
  const visibleCount = Math.min(9, count);
  const half = Math.floor(visibleCount / 2);
  let start = Math.max(0, frameIndex - half);
  start = Math.min(start, Math.max(0, count - visibleCount));
  const frames = Array.from({ length: visibleCount }, (_, offset) => start + offset);
  const suspicious = new Set(project.suspiciousFrames ?? []);

  return (
    <div className="frame-strip" aria-label="Nearby frames">
      {frames.map((frame) => (
        <button
          type="button"
          key={frame}
          className={`frame-thumb ${frame === frameIndex ? "is-current" : ""} ${
            suspicious.has(frame) ? "is-suspicious" : ""
          }`}
          onClick={() => onFrame(frame)}
          aria-label={`Go to frame ${frame + 1}${
            suspicious.has(frame) ? ", flagged for review" : ""
          }`}
        >
          <img src={api.frameUrl(project.id, frame)} alt="" loading="lazy" />
          <span>{String(frame + 1).padStart(3, "0")}</span>
        </button>
      ))}
    </div>
  );
}

