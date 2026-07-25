import { HardDrive, Plus, ShieldCheck } from "lucide-react";
import type { Project } from "../types";
import { StatusBadge } from "./StatusBadge";

interface EditorHeaderProps {
  project: Project;
  onNew: () => void;
}

export function EditorHeader({ project, onNew }: EditorHeaderProps) {
  return (
    <header className="editor-header">
      <button
        className="brand brand--compact brand--button"
        type="button"
        aria-label="Start a new batch"
        onClick={onNew}
      >
        <span className="brand__mark" aria-hidden="true">
          <span />
        </span>
        <span>Frameclean</span>
      </button>
      <div className="project-title">
        <span>{project.name || "Untitled cleanup"}</span>
        <small>
          {project.originalFilename} · {project.processingWidth}×
          {project.processingHeight}
        </small>
      </div>
      <div className="editor-header__right">
        <button className="new-work-button" type="button" onClick={onNew}>
          <Plus size={14} />
          New batch
        </button>
        <span className="storage-mark">
          <HardDrive size={14} />
          Private storage
        </span>
        <StatusBadge status={project.status} />
        <span className="shield-mark" title="Protected project workspace">
          <ShieldCheck size={17} />
        </span>
      </div>
    </header>
  );
}
