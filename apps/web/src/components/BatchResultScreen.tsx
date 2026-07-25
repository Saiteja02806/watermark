import {
  ArrowLeft,
  CheckCircle2,
  Download,
  Film,
  PackageOpen,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { api } from "../api/client";
import type { Batch } from "../types";

interface BatchResultScreenProps {
  batch: Batch;
  onCorrections: () => void;
  onNew: () => void;
  onDelete: () => void;
}

export function BatchResultScreen({
  batch,
  onCorrections,
  onNew,
  onDelete,
}: BatchResultScreenProps) {
  const completed = batch.items.filter((item) => item.status === "COMPLETE");
  const failed = batch.items.length - completed.length;

  return (
    <main className="batch-result">
      <header className="batch-result__header">
        <div>
          <p className="eyebrow">GPU batch complete</p>
          <h1>
            {completed.length}
            <span>/{batch.items.length}</span>
          </h1>
        </div>
        <div className="batch-result__headline">
          <h2>Repaired videos are ready.</h2>
          <p>
            Download the complete package or inspect each export separately.
            Keep visual review as the final quality gate.
          </p>
        </div>
        <div className="batch-result__proof">
          <CheckCircle2 size={18} />
          <span>
            <strong>{completed.length} exports passed validation</strong>
            <small>
              {failed ? `${failed} need attention` : "Original audio preserved"}
            </small>
          </span>
        </div>
      </header>

      <section className="batch-result__list" aria-label="Batch outputs">
        {batch.items.map((item) => (
          <article
            className={`batch-output ${
              item.status === "COMPLETE" ? "is-complete" : "is-failed"
            }`}
            key={item.id}
          >
            <span className="batch-output__number">
              {String(item.position + 1).padStart(2, "0")}
            </span>
            <span className="batch-output__icon">
              {item.status === "COMPLETE" ? (
                <Film size={17} />
              ) : (
                <TriangleAlert size={17} />
              )}
            </span>
            <span className="batch-output__copy">
              <strong>{item.name || item.originalFilename}</strong>
              <small>
                {item.status === "COMPLETE"
                  ? `${item.outputWidth}×${item.outputHeight} · ${
                      item.inpaintingEngine || "repair"
                    } · ${item.outputHasAudio ? "audio restored" : "silent"}`
                  : item.error || item.message}
              </small>
            </span>
            {item.status === "COMPLETE" && (
              <a
                className="button button--quiet"
                href={api.outputUrl(item.id)}
                download={`${item.name || "cleaned-video"}.mp4`}
              >
                <Download size={15} />
                MP4
              </a>
            )}
          </article>
        ))}
      </section>

      <footer className="result-actions">
        <div>
          <button className="button button--quiet" type="button" onClick={onCorrections}>
            <ArrowLeft size={16} />
            Return to review
          </button>
          <button className="button button--quiet" type="button" onClick={onNew}>
            Start new batch
          </button>
        </div>
        <div>
          <button className="button button--danger-quiet" type="button" onClick={onDelete}>
            <Trash2 size={16} />
            Delete batch
          </button>
          {completed.length > 0 && (
            <a
              className="button button--primary"
              href={api.batchOutputUrl(batch.id)}
              download={`${batch.name || "frameclean-batch"}-results.zip`}
            >
              <PackageOpen size={16} />
              Download all
            </a>
          )}
        </div>
      </footer>
    </main>
  );
}
