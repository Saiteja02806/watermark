import { useEffect } from "react";
import { api } from "../api/client";
import { useEditorStore } from "../stores/editorStore";
import type { ProgressEvent } from "../types";

const REFRESH_STATUSES = new Set([
  "READY_FOR_SELECTION",
  "READY_FOR_MASK_REVIEW",
  "COMPLETE",
  "FAILED",
  "CANCELLED",
]);

export function useProjectEvents(projectId?: string) {
  const setProgress = useEditorStore((state) => state.setProgress);
  const setProject = useEditorStore((state) => state.setProject);

  useEffect(() => {
    if (!projectId) return;
    const source = new EventSource(api.eventsUrl(projectId));
    let lastRefreshStatus = "";
    source.onmessage = (event) => {
      const payload = JSON.parse(event.data) as ProgressEvent;
      setProgress(payload);
      if (
        REFRESH_STATUSES.has(payload.status) &&
        payload.status !== lastRefreshStatus
      ) {
        lastRefreshStatus = payload.status;
        void api.getProject(projectId).then(setProject);
      }
    };
    source.onerror = () => {
      // EventSource reconnects automatically while the local server is alive.
    };
    return () => source.close();
  }, [projectId, setProgress, setProject]);
}

