import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Lock,
  Play,
  Save,
  ScanSearch,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { api } from "./api/client";
import { BatchRail } from "./components/BatchRail";
import { BatchResultScreen } from "./components/BatchResultScreen";
import { EditorHeader } from "./components/EditorHeader";
import { FailureScreen } from "./components/FailureScreen";
import { MaskToolbar } from "./components/MaskToolbar";
import { ProcessingPanel } from "./components/ProcessingPanel";
import { ProcessingSettings } from "./components/ProcessingSettings";
import { ResultScreen } from "./components/ResultScreen";
import { UploadScreen } from "./components/UploadScreen";
import { VideoCanvas } from "./components/VideoCanvas";
import { VideoTimeline } from "./components/VideoTimeline";
import { useProjectEvents } from "./hooks/useProjectEvents";
import { useEditorStore } from "./stores/editorStore";
import type { Batch, BatchItem, Health } from "./types";
import type { AutoWatermarkResult, CanvasBox } from "./types";

function App() {
  const store = useEditorStore();
  const [health, setHealth] = useState<Health | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [restoringProject, setRestoringProject] = useState(true);
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showResult, setShowResult] = useState(true);
  const [showSettings, setShowSettings] = useState(false);

  useProjectEvents(store.project?.id);

  useEffect(() => {
    void api
      .health()
      .then(setHealth)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Local server unavailable"),
      );
  }, []);

  useEffect(() => {
    const batchId = window.localStorage.getItem("frameclean.currentBatch");
    const projectId = window.localStorage.getItem("frameclean.currentProject");
    const restore = async () => {
      if (batchId) {
        try {
          const restored = await api.getBatch(batchId);
          setBatch(restored);
          if (restored.items.length) {
            store.setProject(restored.items[0]);
            window.localStorage.setItem(
              "frameclean.currentProject",
              restored.items[0].id,
            );
          }
          return;
        } catch {
          window.localStorage.removeItem("frameclean.currentBatch");
        }
      }
      if (projectId) {
        try {
          store.setProject(await api.getProject(projectId));
        } catch {
          window.localStorage.removeItem("frameclean.currentProject");
        }
      }
    };
    void restore().finally(() => setRestoringProject(false));
  }, [store.setProject]);

  useEffect(() => {
    if (!batch && store.project?.status === "COMPLETE") setShowResult(true);
  }, [batch?.id, store.project?.status]);

  useEffect(() => {
    const batchId = batch?.id;
    if (!batchId) return;
    let stopped = false;
    const refresh = async () => {
      try {
        const next = await api.getBatch(batchId);
        if (stopped) return;
        setBatch(next);
        const activeId = useEditorStore.getState().project?.id;
        const active = next.items.find((item) => item.id === activeId);
        if (active) store.setProject(active);
        else if (next.items.length) store.setProject(next.items[0]);
      } catch {
        // A temporary proxy interruption is retried on the next poll.
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [batch?.id, store.setProject]);

  useEffect(() => {
    if (
      batch &&
      ["COMPLETE", "PARTIAL_COMPLETE", "FAILED", "CANCELLED"].includes(
        batch.status,
      )
    ) {
      setShowResult(true);
    }
  }, [batch?.status]);

  const handleFiles = async (files: File[]) => {
    if (!files.length) return;
    if (
      health?.limits.maximumBatchVideos &&
      files.length > health.limits.maximumBatchVideos
    ) {
      setError(
        `Choose no more than ${health.limits.maximumBatchVideos} videos per batch.`,
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (files.length > 1) {
        const created = await api.createBatch(
          `${files.length}-video watermark repair`,
        );
        setBatch(created);
        window.localStorage.setItem("frameclean.currentBatch", created.id);
        window.localStorage.removeItem("frameclean.currentProject");
        const failures: string[] = [];
        for (const file of files) {
          const name = file.name.replace(/\.[^.]+$/, "").slice(0, 80);
          try {
            const project = await api.addBatchProject(created.id, name);
            if (!useEditorStore.getState().project) {
              store.setProject(project);
              window.localStorage.setItem(
                "frameclean.currentProject",
                project.id,
              );
            }
            await api.upload(project.id, file);
          } catch (reason) {
            failures.push(
              `${file.name}: ${
                reason instanceof Error ? reason.message : "upload failed"
              }`,
            );
          }
          setBatch(await api.getBatch(created.id));
        }
        const readyBatch = await api.getBatch(created.id);
        setBatch(readyBatch);
        if (readyBatch.items.length) {
          store.setProject(readyBatch.items[0]);
          store.setScreenFixed(true);
          window.localStorage.setItem(
            "frameclean.currentProject",
            readyBatch.items[0].id,
          );
        }
        if (failures.length) {
          setError(`${failures.length} video(s) could not be prepared.`);
        }
        return;
      }

      const file = files[0];
      const name = file.name.replace(/\.[^.]+$/, "").slice(0, 80);
      const project = await api.createProject(name);
      setBatch(null);
      window.localStorage.removeItem("frameclean.currentBatch");
      window.localStorage.setItem("frameclean.currentProject", project.id);
      store.setProject(project);
      await api.upload(project.id, file);
      store.setProject(await api.getProject(project.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not prepare this video");
    } finally {
      setBusy(false);
    }
  };

  const selectBatchItem = (item: BatchItem) => {
    store.setProject(item);
    store.clearPrompts();
    window.localStorage.setItem("frameclean.currentProject", item.id);
  };

  const saveAndTrack = async (
    forceEngine: "auto" | "opencv" | "fixed" = "auto",
  ) => {
    const project = store.project;
    if (!project) return;
    if (
      !store.positivePoints.length &&
      !store.box &&
      !store.manualMask
    ) {
      setError("Add a positive point, draw a box, or paint the object first.");
      return;
    }
    setActionBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (batch) {
        await api.applyBatchSelection(
          batch.id,
          project.id,
          store.frameIndex,
          store.positivePoints,
          store.negativePoints,
          store.box,
          store.manualMask,
          store.screenFixed,
        );
        setBatch(await api.getBatch(batch.id));
      } else {
        await api.saveSelection(
          project.id,
          store.frameIndex,
          store.positivePoints,
          store.negativePoints,
          store.box,
          store.manualMask,
        );
        await api.track(
          project.id,
          store.screenFixed ? "fixed" : forceEngine,
        );
      }
      store.setProject(await api.getProject(project.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tracking could not start");
    } finally {
      setActionBusy(false);
    }
  };

  const autoDetectWatermark = async () => {
    const project = store.project;
    if (!project) return;
    setActionBusy(true);
    setError(null);
    setNotice(null);
    try {
      const detected = await api.detectWatermark(project.id);
      const detectedBox = toCanvasBox(detected);
      store.setFrameIndex(detected.frameIndex);
      store.setBox(detectedBox);
      store.setManualMask(detected.manualMaskDataUrl);
      store.setScreenFixed(true);
      if (batch) {
        await api.applyBatchSelection(
          batch.id,
          project.id,
          detected.frameIndex,
          [],
          [],
          detectedBox,
          detected.manualMaskDataUrl,
          true,
        );
        setBatch(await api.getBatch(batch.id));
      } else {
        await api.track(project.id, "fixed");
      }
      store.setProject(await api.getProject(project.id));
      setNotice(
        `Auto watermark mask created (${Math.round(
          detected.confidence * 100,
        )}% confidence). Review it before processing.`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Auto watermark detection could not find a stable overlay",
      );
    } finally {
      setActionBusy(false);
    }
  };

  const saveCorrection = async () => {
    const project = store.project;
    if (!project) return;
    setActionBusy(true);
    setError(null);
    try {
      await api.correctMask(
        project.id,
        store.frameIndex,
        store.manualMask,
        store.positivePoints,
        store.negativePoints,
        store.isLocked,
      );
      store.bumpMaskRevision();
      store.clearPrompts();
      setNotice(`Correction saved on frame ${store.frameIndex + 1}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Correction could not be saved");
    } finally {
      setActionBusy(false);
    }
  };

  const startRender = async () => {
    const project = store.project;
    if (!project) return;
    setActionBusy(true);
    setError(null);
    try {
      if (batch) {
        await api.renderBatch(batch.id, store.renderSettings);
        setBatch(await api.getBatch(batch.id));
      } else {
        await api.render(project.id, store.renderSettings);
      }
      store.setProject(await api.getProject(project.id));
      setShowSettings(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Processing could not start");
    } finally {
      setActionBusy(false);
    }
  };

  const cancel = async () => {
    if (!store.project) return;
    if (batch) {
      await api.cancelBatch(batch.id);
      setBatch(await api.getBatch(batch.id));
    } else {
      await api.cancel(store.project.id);
    }
    store.setProject(await api.getProject(store.project.id));
  };

  const startNew = () => {
    window.localStorage.removeItem("frameclean.currentBatch");
    window.localStorage.removeItem("frameclean.currentProject");
    setBatch(null);
    store.reset();
    setShowResult(false);
    setShowSettings(false);
    setError(null);
    setNotice(null);
  };

  const removeProject = async () => {
    if (!store.project) return;
    const confirmed = window.confirm(
      batch
        ? "Permanently delete every original, mask, and export in this batch?"
        : "Permanently delete the original video, frames, masks, and export for this project?",
    );
    if (!confirmed) return;
    if (batch) {
      await api.deleteBatch(batch.id);
      window.localStorage.removeItem("frameclean.currentBatch");
      setBatch(null);
    } else {
      await api.delete(store.project.id);
    }
    window.localStorage.removeItem("frameclean.currentProject");
    store.reset();
    setShowResult(false);
    setError(null);
  };

  if (restoringProject) {
    return (
      <main className="restore-screen" aria-live="polite">
        <span className="brand__mark" aria-hidden="true">
          <span />
        </span>
        <p>Opening the local workspace…</p>
      </main>
    );
  }

  if (!store.project) {
    return (
      <UploadScreen
        health={health}
        busy={busy}
        error={error}
        onSelect={handleFiles}
      />
    );
  }

  if (
    batch &&
    ["COMPLETE", "PARTIAL_COMPLETE", "FAILED", "CANCELLED"].includes(
      batch.status,
    ) &&
    showResult
  ) {
    return (
      <BatchResultScreen
        batch={batch}
        onCorrections={() => setShowResult(false)}
        onNew={startNew}
        onDelete={() => void removeProject()}
      />
    );
  }

  if (!batch && store.project.status === "COMPLETE" && showResult) {
    return (
      <ResultScreen
        project={store.project}
        onCorrections={() => setShowResult(false)}
        onDelete={() => void removeProject()}
      />
    );
  }

  const isSelecting = store.project.status === "READY_FOR_SELECTION";
  const isReviewing =
    store.project.status === "READY_FOR_MASK_REVIEW" ||
    store.project.status === "COMPLETE";
  const isProcessing = [
    "NORMALIZING",
    "GENERATING_MASKS",
    "INPAINTING",
    "MUXING_AUDIO",
  ].includes(store.project.status);
  const canvasReady = isSelecting || isReviewing;
  const hasPrompt = Boolean(
    store.positivePoints.length ||
      store.box ||
      store.manualMask,
  );

  return (
    <div className="app-shell">
      <EditorHeader project={store.project} onNew={startNew} />
      {batch && (
        <BatchRail
          batch={batch}
          activeProjectId={store.project.id}
          onSelect={selectBatchItem}
        />
      )}

      <div className="workspace">
        {canvasReady ? (
          <>
            <MaskToolbar
              tool={store.tool}
              brushSize={store.brushSize}
              onTool={store.setTool}
              onBrushSize={store.setBrushSize}
              onClear={store.clearPrompts}
            />
            <main className="editor-stage">
              <div className="stage-heading">
                <div>
                  <span className="section-kicker">
                    {isSelecting ? "Selection pass" : "Mask review"}
                  </span>
                  <h1>
                    {isSelecting
                      ? "Mark the unwanted region."
                      : "Inspect the tracked edge."}
                  </h1>
                </div>
                <p>
                  {isSelecting
                    ? "Start with one click inside the object. Add a box when its boundary is clear."
                    : "Orange frames need attention. Paint over misses, erase spill, then save the correction."}
                </p>
              </div>

              <div className="canvas-area">
                <VideoCanvas
                  project={store.project}
                  frameIndex={store.frameIndex}
                  tool={store.tool}
                  brushSize={store.brushSize}
                  positivePoints={store.positivePoints}
                  negativePoints={store.negativePoints}
                  box={store.box}
                  maskRevision={store.maskRevision}
                  showTrackedMask={isReviewing}
                  onPoint={store.addPoint}
                  onBox={store.setBox}
                  onManualMask={store.setManualMask}
                />
              </div>

              <VideoTimeline
                project={store.project}
                frameIndex={store.frameIndex}
                onFrame={store.setFrameIndex}
              />
            </main>

            <aside className="action-panel">
              <div className="action-panel__summary">
                <span className="section-kicker">
                  {isSelecting ? "Current prompt" : "Frame review"}
                </span>
                <PromptSummary
                  positives={store.positivePoints.length}
                  negatives={store.negativePoints.length}
                  hasBox={Boolean(store.box)}
                  hasBrush={Boolean(store.manualMask)}
                />
              </div>

              {isReviewing && (
                <label className="lock-row">
                  <span>
                    <Lock size={15} />
                    Lock this frame
                  </span>
                  <input
                    type="checkbox"
                    checked={store.isLocked}
                    onChange={(event) => store.setLocked(event.currentTarget.checked)}
                  />
                </label>
              )}

              {isSelecting && (
                <label className="lock-row">
                  <span>
                    <Lock size={15} />
                    {batch
                      ? "Use this position across the batch"
                      : "Keep mask fixed on screen"}
                  </span>
                  <input
                    type="checkbox"
                    checked={store.screenFixed}
                    onChange={(event) =>
                      store.setScreenFixed(event.currentTarget.checked)
                    }
                  />
                </label>
              )}

              <div className="action-panel__buttons">
                {isSelecting ? (
                  <>
                    <button
                      className="button button--quiet button--full"
                      type="button"
                      disabled={
                        actionBusy ||
                        Boolean(batch && batch.status !== "READY_FOR_SELECTION")
                      }
                      onClick={() => void autoDetectWatermark()}
                    >
                      <Sparkles size={16} />
                      Auto Watermark
                    </button>
                    <button
                      className="button button--primary button--full"
                      type="button"
                      disabled={
                        actionBusy ||
                        !hasPrompt ||
                        Boolean(batch && batch.status !== "READY_FOR_SELECTION")
                      }
                      onClick={() => void saveAndTrack()}
                    >
                      <ScanSearch size={17} />
                      {batch && batch.status !== "READY_FOR_SELECTION"
                        ? "Waiting for batch preparation"
                        : hasPrompt
                          ? batch
                            ? "Apply selection to batch"
                            : "Track selection"
                          : "Select a region first"}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      className="button button--quiet button--full"
                      type="button"
                      disabled={actionBusy}
                      onClick={() => void saveCorrection()}
                    >
                      <Save size={16} />
                      Save frame correction
                    </button>
                    <button
                      className="button button--quiet button--full"
                      type="button"
                      disabled={actionBusy}
                      onClick={() => void saveAndTrack()}
                    >
                      <Play size={16} />
                      Re-track from here
                    </button>
                    <button
                      className="button button--primary button--full"
                      type="button"
                      disabled={
                        actionBusy ||
                        Boolean(batch && batch.status !== "READY_FOR_REVIEW")
                      }
                      onClick={() => setShowSettings(true)}
                    >
                      <Sparkles size={16} />
                      {batch
                        ? `Process ${batch.items.length} videos`
                        : "Process video"}
                    </button>
                  </>
                )}
              </div>
              {health && !health.sam2 && !store.screenFixed && (
                <div className="engine-note engine-note--compact">
                  <TriangleAlert size={15} />
                  <p>
                    SAM 2.1 is not installed. Tracking will use the local motion
                    fallback.
                  </p>
                </div>
              )}
              {isSelecting && !hasPrompt && (
                <p className="selection-nudge">
                  Click inside the object, drag a box around it, or paint its
                  full outline before tracking.
                </p>
              )}
              {notice && <p className="inline-notice">{notice}</p>}
              {error && (
                <p className="inline-error" role="alert">
                  {error}
                </p>
              )}
            </aside>
          </>
        ) : store.project.status === "FAILED" ? (
          <FailureScreen
            error={store.project.error}
            health={health}
            onRetry={() => setShowSettings(true)}
          />
        ) : (
          <main className="processing-workspace">
            <div className="processing-visual" aria-hidden="true">
              <span className="processing-visual__scan" />
              <span className="processing-visual__frame" />
            </div>
            <div>
              <p className="eyebrow">Local worker active</p>
              <h1>{store.progress?.message ?? "Preparing the next stage…"}</h1>
              <p>
                The queue is saved on disk. You can close this page and return
                while the GPU continues working.
              </p>
            </div>
          </main>
        )}
      </div>

      <ProcessingPanel
        progress={store.progress}
        status={store.project.status}
        onCancel={() => void cancel()}
      />

      {showSettings && (
        <div className="settings-drawer" role="dialog" aria-modal="true" aria-label="Process video">
          <button
            className="drawer-scrim"
            type="button"
            aria-label="Close process settings"
            onClick={() => setShowSettings(false)}
          />
          <div className="settings-drawer__panel">
            <ProcessingSettings
              health={health}
              settings={store.renderSettings}
              onChange={store.setRenderSettings}
            />
            <div className="settings-drawer__actions">
              <button
                className="button button--quiet"
                type="button"
                onClick={() => setShowSettings(false)}
              >
                Keep reviewing
              </button>
              <button
                className="button button--primary"
                type="button"
                disabled={actionBusy}
                onClick={() => void startRender()}
              >
                {batch
                  ? `Start ${batch.items.length}-video batch`
                  : "Start repair"}
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PromptSummary({
  positives,
  negatives,
  hasBox,
  hasBrush,
}: {
  positives: number;
  negatives: number;
  hasBox: boolean;
  hasBrush: boolean;
}) {
  const items = useMemo(
    () => [
      { label: "Include points", value: positives },
      { label: "Exclude points", value: negatives },
      { label: "Bounding box", value: hasBox ? "Drawn" : "—" },
      { label: "Manual mask", value: hasBrush ? "Painted" : "—" },
    ],
    [hasBox, hasBrush, negatives, positives],
  );
  return (
    <dl className="prompt-summary">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export default App;

function toCanvasBox(result: AutoWatermarkResult): CanvasBox {
  const [x1, y1, x2, y2] = result.box;
  return { x1, y1, x2, y2 };
}
