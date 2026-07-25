import type {
  Batch,
  Health,
  Project,
  RenderSettings,
  CanvasBox,
  CanvasPoint,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // Keep the status-based message for non-JSON errors.
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),

  createBatch: (name: string) =>
    request<Batch>("/api/batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  getBatch: (batchId: string) =>
    request<Batch>(`/api/batches/${batchId}`),

  listBatches: () => request<Batch[]>("/api/batches"),

  addBatchProject: (batchId: string, name: string) =>
    request<Project>(`/api/batches/${batchId}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  createProject: (name: string) =>
    request<Project>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  getProject: (projectId: string) =>
    request<Project>(`/api/projects/${projectId}`),

  upload: async (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ jobId: string; status: string }>(
      `/api/projects/${projectId}/upload`,
      { method: "POST", body: form },
    );
  },

  saveSelection: (
    projectId: string,
    frameIndex: number,
    positivePoints: CanvasPoint[],
    negativePoints: CanvasPoint[],
    box: CanvasBox | null,
    manualMaskDataUrl?: string | null,
  ) =>
    request<{ saved: boolean }>(`/api/projects/${projectId}/selection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        frameIndex,
        positivePoints: positivePoints.map(({ x, y }) => [x, y]),
        negativePoints: negativePoints.map(({ x, y }) => [x, y]),
        box: box ? [box.x1, box.y1, box.x2, box.y2] : null,
        manualMaskDataUrl: manualMaskDataUrl || null,
      }),
    }),

  track: (
    projectId: string,
    engine: "auto" | "sam2" | "opencv" | "fixed" = "auto",
  ) =>
    request<{ jobId: string }>(`/api/projects/${projectId}/track`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ direction: "both", engine }),
    }),

  applyBatchSelection: (
    batchId: string,
    referenceProjectId: string,
    frameIndex: number,
    positivePoints: CanvasPoint[],
    negativePoints: CanvasPoint[],
    box: CanvasBox | null,
    manualMaskDataUrl: string | null,
    fixed: boolean,
  ) =>
    request<{ jobs: string[] }>(`/api/batches/${batchId}/selection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        referenceProjectId,
        frameIndex,
        positivePoints: positivePoints.map(({ x, y }) => [x, y]),
        negativePoints: negativePoints.map(({ x, y }) => [x, y]),
        box: box ? [box.x1, box.y1, box.x2, box.y2] : null,
        manualMaskDataUrl: manualMaskDataUrl || null,
        fixed,
      }),
    }),

  correctMask: (
    projectId: string,
    frameIndex: number,
    maskDataUrl: string | null,
    positivePoints: CanvasPoint[],
    negativePoints: CanvasPoint[],
    locked: boolean,
  ) =>
    request<{ saved: boolean }>(
      `/api/projects/${projectId}/masks/${frameIndex}/correct`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          maskDataUrl,
          positivePoints: positivePoints.map(({ x, y }) => [x, y]),
          negativePoints: negativePoints.map(({ x, y }) => [x, y]),
          locked,
        }),
      },
    ),

  render: (projectId: string, settings: RenderSettings) =>
    request<{ jobId: string }>(`/api/projects/${projectId}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }),

  renderBatch: (batchId: string, settings: RenderSettings) =>
    request<{ jobs: string[] }>(`/api/batches/${batchId}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }),

  cancel: (projectId: string) =>
    request<{ cancelled: boolean }>(`/api/projects/${projectId}/cancel`, {
      method: "POST",
    }),

  cancelBatch: (batchId: string) =>
    request<{ cancelled: string[] }>(`/api/batches/${batchId}/cancel`, {
      method: "POST",
    }),

  delete: (projectId: string) =>
    request<void>(`/api/projects/${projectId}`, { method: "DELETE" }),

  deleteBatch: (batchId: string) =>
    request<void>(`/api/batches/${batchId}`, { method: "DELETE" }),

  frameUrl: (projectId: string, frameIndex: number) =>
    `${API_BASE}/api/projects/${projectId}/frame/${frameIndex}`,
  maskUrl: (projectId: string, frameIndex: number, revision = 0) =>
    `${API_BASE}/api/projects/${projectId}/masks/${frameIndex}?v=${revision}`,
  proxyUrl: (projectId: string) =>
    `${API_BASE}/api/projects/${projectId}/video`,
  outputUrl: (projectId: string) =>
    `${API_BASE}/api/projects/${projectId}/output`,
  batchOutputUrl: (batchId: string) =>
    `${API_BASE}/api/batches/${batchId}/output.zip`,
  eventsUrl: (projectId: string) =>
    `${API_BASE}/api/projects/${projectId}/events`,
};
