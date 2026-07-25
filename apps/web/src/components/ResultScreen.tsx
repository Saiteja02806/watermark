import { ArrowLeft, Download, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "../api/client";
import type { Project } from "../types";
import { BeforeAfterViewer } from "./BeforeAfterViewer";

interface ResultScreenProps {
  project: Project;
  onCorrections: () => void;
  onDelete: () => void;
}

export function ResultScreen({
  project,
  onCorrections,
  onDelete,
}: ResultScreenProps) {
  return (
    <main className="result-screen">
      <header className="result-header">
        <div>
          <p className="eyebrow">Local export complete</p>
          <h1>Review the repaired sequence.</h1>
          <p>
            Automated checks passed. Visual review is still the final quality
            gate, especially around moving edges and occlusions.
          </p>
        </div>
        <div className="result-header__proof">
          <ShieldCheck size={18} />
          <span>
            <strong>Stayed on this computer</strong>
            <small>{project.outputHasAudio ? "Original audio restored" : "Silent output"}</small>
          </span>
        </div>
      </header>

      <BeforeAfterViewer project={project} />

      <footer className="result-actions">
        <button className="button button--quiet" type="button" onClick={onCorrections}>
          <ArrowLeft size={16} />
          Return to corrections
        </button>
        <div>
          <button className="button button--danger-quiet" type="button" onClick={onDelete}>
            <Trash2 size={16} />
            Delete project
          </button>
          <a
            className="button button--primary"
            href={api.outputUrl(project.id)}
            download={`${project.name || "cleaned-video"}.mp4`}
          >
            <Download size={16} />
            Download result
          </a>
        </div>
      </footer>
    </main>
  );
}

