import { useRef, useState } from "react";
import {
  Check,
  Film,
  HardDrive,
  LockKeyhole,
  Upload,
  WifiOff,
} from "lucide-react";
import type { Health } from "../types";

interface UploadScreenProps {
  health: Health | null;
  busy: boolean;
  error: string | null;
  onSelect: (files: File[]) => void;
}

export function UploadScreen({
  health,
  busy,
  error,
  onSelect,
}: UploadScreenProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const accept = (files: FileList | null) => {
    const selected = Array.from(files ?? []);
    if (selected.length) onSelect(selected);
  };

  return (
    <main className="upload-shell">
      <nav className="brand-bar" aria-label="Product">
        <a className="brand" href="/" aria-label="Frameclean home">
          <span className="brand__mark" aria-hidden="true">
            <span />
          </span>
          <span>Frameclean</span>
        </a>
        <span className="local-pill">
          <WifiOff size={13} />
          {health?.localOnly
            ? "127.0.0.1 · offline workspace"
            : "Private GPU workspace"}
        </span>
      </nav>

      <section className="upload-hero">
        <div className="upload-intro">
          <p className="eyebrow">Private video repair</p>
          <h1>
            Remove the interruption.
            <span>Keep the moment.</span>
          </h1>
          <p className="upload-intro__copy">
            Upload one clip or a full run. Mark the watermark once, then let the
            GPU queue rebuild every video in sequence.
          </p>
          <div className="privacy-proof" aria-label="Workspace guarantees">
            <span>
              <LockKeyhole size={16} />
              Protected workspace
            </span>
            <span>
              <HardDrive size={16} />
              Persistent project storage
            </span>
            <span>
              <Check size={16} />
              Original audio restored
            </span>
          </div>
        </div>

        <div
          className={`drop-gate ${dragging ? "drop-gate--dragging" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => {
            if (event.currentTarget === event.target) setDragging(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            accept(event.dataTransfer.files);
          }}
        >
          <span className="gate-corner gate-corner--tl" />
          <span className="gate-corner gate-corner--tr" />
          <span className="gate-corner gate-corner--bl" />
          <span className="gate-corner gate-corner--br" />
          <div className="drop-gate__icon">
            <Film size={34} strokeWidth={1.4} />
          </div>
          <p className="drop-gate__title">
            {busy ? "Building your batch queue…" : "Drop videos here"}
          </p>
          <p className="drop-gate__hint">
            Select up to {health?.limits.maximumBatchVideos ?? 20} clips · one
            watermark position · sequential GPU repair
          </p>
          <input
            ref={inputRef}
            className="visually-hidden"
            type="file"
            multiple
            accept="video/mp4,video/quicktime,video/webm,video/x-msvideo,video/x-matroska"
            onChange={(event) => accept(event.currentTarget.files)}
          />
          <button
            className="button button--primary"
            type="button"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
          >
            <Upload size={16} />
            {busy ? "Preparing queue" : "Choose videos"}
          </button>
          {error && (
            <p className="inline-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </section>

      <section className="readiness-strip" aria-label="System readiness">
        <p>{health?.localOnly ? "Local pipeline" : "GPU pod pipeline"}</p>
        <Readiness label="Media tools" ready={Boolean(health?.ffmpeg && health?.ffprobe)} />
        <Readiness
          label="SAM 2.1"
          ready={Boolean(health?.sam2)}
          fallback="Motion fallback"
        />
        <Readiness
          label="ProPainter"
          ready={Boolean(health?.propainter)}
          fallback="CPU repair fallback"
        />
      </section>

      <p className="use-note">
        Built for authorized cleanup of footage you are allowed to edit. It
        does not include provenance-removal tooling.
      </p>
    </main>
  );
}

function Readiness({
  label,
  ready,
  fallback,
}: {
  label: string;
  ready: boolean;
  fallback?: string;
}) {
  return (
    <div className="readiness-item">
      <span
        className={`readiness-item__light ${ready ? "is-ready" : "is-fallback"}`}
        aria-hidden="true"
      />
      <span>
        <strong>{label}</strong>
        <small>{ready ? "Ready" : fallback || "Setup required"}</small>
      </span>
    </div>
  );
}
