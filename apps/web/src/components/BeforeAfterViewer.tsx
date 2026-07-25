import { useRef } from "react";
import { api } from "../api/client";
import type { Project } from "../types";

export function BeforeAfterViewer({ project }: { project: Project }) {
  const beforeRef = useRef<HTMLVideoElement>(null);
  const afterRef = useRef<HTMLVideoElement>(null);

  const syncBefore = () => {
    const before = beforeRef.current;
    const after = afterRef.current;
    if (!before || !after) return;
    if (Math.abs(before.currentTime - after.currentTime) > 0.08) {
      before.currentTime = after.currentTime;
    }
  };

  return (
    <div className="comparison-viewer">
      <div className="comparison-pane">
        <span className="comparison-label">Before</span>
        <video
          ref={beforeRef}
          src={api.proxyUrl(project.id)}
          muted
          playsInline
          preload="metadata"
        />
      </div>
      <div className="comparison-seam" aria-hidden="true">
        <span />
      </div>
      <div className="comparison-pane">
        <span className="comparison-label comparison-label--after">After</span>
        <video
          ref={afterRef}
          src={api.outputUrl(project.id)}
          controls
          playsInline
          preload="metadata"
          onPlay={() => void beforeRef.current?.play()}
          onPause={() => beforeRef.current?.pause()}
          onSeeked={syncBefore}
          onTimeUpdate={syncBefore}
          onEnded={() => {
            if (beforeRef.current) beforeRef.current.currentTime = 0;
          }}
        />
      </div>
    </div>
  );
}

