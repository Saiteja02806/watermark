import type { ProjectStatus } from "../types";

const labels: Record<ProjectStatus, string> = {
  CREATED: "Project created",
  UPLOADING: "Uploading locally",
  UPLOADED: "Upload complete",
  NORMALIZING: "Preparing video",
  READY_FOR_SELECTION: "Ready to select",
  GENERATING_MASKS: "Tracking selection",
  READY_FOR_MASK_REVIEW: "Review masks",
  INPAINTING: "Reconstructing",
  MUXING_AUDIO: "Restoring audio",
  COMPLETE: "Export ready",
  FAILED: "Needs attention",
  CANCELLED: "Cancelled",
};

export function StatusBadge({ status }: { status: ProjectStatus }) {
  const tone =
    status === "FAILED"
      ? "danger"
      : status === "COMPLETE"
        ? "success"
        : status === "READY_FOR_MASK_REVIEW"
          ? "warning"
          : "active";
  return (
    <span className={`status-badge status-badge--${tone}`}>
      <span className="status-badge__dot" aria-hidden="true" />
      {labels[status]}
    </span>
  );
}

