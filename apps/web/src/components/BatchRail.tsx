import { Check, Clock3, Film, LoaderCircle, TriangleAlert } from "lucide-react";
import type { Batch, BatchItem } from "../types";

interface BatchRailProps {
  batch: Batch;
  activeProjectId?: string;
  onSelect: (item: BatchItem) => void;
}

export function BatchRail({
  batch,
  activeProjectId,
  onSelect,
}: BatchRailProps) {
  return (
    <section className="batch-rail" aria-label="Batch queue">
      <div className="batch-rail__summary">
        <span className="batch-rail__index">
          {String(batch.items.length).padStart(2, "0")}
        </span>
        <span>
          <strong>{batch.name || "Video batch"}</strong>
          <small>{batch.progress}% across the queue</small>
        </span>
      </div>
      <div className="batch-rail__track" aria-hidden="true">
        <span style={{ height: `${batch.progress}%` }} />
      </div>
      <div className="batch-rail__items">
        {batch.items.map((item) => (
          <button
            className={`batch-clip ${
              item.id === activeProjectId ? "is-active" : ""
            }`}
            type="button"
            key={item.id}
            title={`${item.name || item.originalFilename} · ${item.message}`}
            onClick={() => onSelect(item)}
          >
            <BatchStateIcon item={item} />
            <span>
              <strong>{item.name || `Clip ${item.position + 1}`}</strong>
              <small>{formatStatus(item)}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function BatchStateIcon({ item }: { item: BatchItem }) {
  if (item.status === "COMPLETE") return <Check size={13} />;
  if (item.status === "FAILED" || item.status === "CANCELLED") {
    return <TriangleAlert size={13} />;
  }
  if (item.jobStatus === "RUNNING") {
    return <LoaderCircle className="batch-clip__spinner" size={13} />;
  }
  if (item.jobStatus === "QUEUED") return <Clock3 size={13} />;
  return <Film size={13} />;
}

function formatStatus(item: BatchItem) {
  if (item.jobStatus === "RUNNING") return `${item.progress}% · working`;
  if (item.jobStatus === "QUEUED") return "Queued";
  return item.status.replaceAll("_", " ").toLowerCase();
}
