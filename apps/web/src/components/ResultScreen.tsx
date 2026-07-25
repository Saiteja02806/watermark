import { useEffect, useState } from "react";
import { ArrowLeft, Download, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "../api/client";
import type { Project, QualityReport } from "../types";
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
  const [report, setReport] = useState<QualityReport | null>(null);

  useEffect(() => {
    let active = true;
    void api
      .qualityReport(project.id)
      .then((next) => {
        if (active) setReport(next);
      })
      .catch(() => {
        if (active) setReport(null);
      });
    return () => {
      active = false;
    };
  }, [project.id]);

  const warnings = report?.qualityWarnings ?? [];
  return (
    <main className="result-screen">
      <header className="result-header">
        <div>
          <p className="eyebrow">Local export complete</p>
          <h1>Review the repaired sequence.</h1>
          <p>
            {!report
              ? "The output is ready, but its quality report could not be loaded. Review the repaired region carefully before downloading."
              : warnings.length
                ? `Automated review flagged: ${warnings.join(" ")}`
                : `${report.encodedOutputInspected ? "Every encoded frame" : "Every reconstructed frame"} was checked for missing or black frames, background spill, boundary damage, and temporal variation. Visual review remains the final quality gate.`}
          </p>
        </div>
        <div className="result-header__proof">
          <ShieldCheck size={18} />
          <span>
            <strong>Stayed on this computer</strong>
            <small>
              {report?.encodedOutputInspected
                ? `${report.frameCount} encoded frames inspected`
                : project.outputHasAudio
                  ? "Original audio restored"
                  : "Silent output"}
            </small>
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
