import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { api } from "../api/client";
import type {
  CanvasBox,
  CanvasPoint,
  EditorTool,
  Project,
} from "../types";
import { clientToCanvas } from "../utils/coordinates";
import { MaskOverlay } from "./MaskOverlay";

interface VideoCanvasProps {
  project: Project;
  frameIndex: number;
  tool: EditorTool;
  brushSize: number;
  positivePoints: CanvasPoint[];
  negativePoints: CanvasPoint[];
  box: CanvasBox | null;
  maskRevision: number;
  showTrackedMask: boolean;
  onPoint: (point: CanvasPoint, positive: boolean) => void;
  onBox: (box: CanvasBox) => void;
  onManualMask: (dataUrl: string | null) => void;
}

export function VideoCanvas({
  project,
  frameIndex,
  tool,
  brushSize,
  positivePoints,
  negativePoints,
  box,
  maskRevision,
  showTrackedMask,
  onPoint,
  onBox,
  onManualMask,
}: VideoCanvasProps) {
  const width = project.processingWidth ?? project.width ?? 720;
  const height = project.processingHeight ?? project.height ?? 480;
  const imageCanvasRef = useRef<HTMLCanvasElement>(null);
  const manualCanvasRef = useRef<HTMLCanvasElement>(null);
  const promptCanvasRef = useRef<HTMLCanvasElement>(null);
  const drawingRef = useRef(false);
  const lastPointRef = useRef<CanvasPoint | null>(null);
  const boxStartRef = useRef<CanvasPoint | null>(null);
  const [draftBox, setDraftBox] = useState<CanvasBox | null>(null);
  const [frameLoaded, setFrameLoaded] = useState(false);

  useEffect(() => {
    const canvas = imageCanvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    setFrameLoaded(false);
    const image = new Image();
    image.onload = () => {
      context.clearRect(0, 0, width, height);
      context.drawImage(image, 0, 0, width, height);
      setFrameLoaded(true);
    };
    image.src = api.frameUrl(project.id, frameIndex);
  }, [frameIndex, height, project.id, width]);

  useEffect(() => {
    const canvas = manualCanvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    context.clearRect(0, 0, width, height);
    onManualMask(null);
  }, [frameIndex, height, maskRevision, onManualMask, width]);

  useEffect(() => {
    const canvas = promptCanvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    context.clearRect(0, 0, width, height);
    for (const point of positivePoints) drawPrompt(context, point, true, width);
    for (const point of negativePoints) drawPrompt(context, point, false, width);
    const visibleBox = draftBox ?? box;
    if (visibleBox) drawBox(context, visibleBox, width);
  }, [
    box,
    draftBox,
    height,
    negativePoints,
    positivePoints,
    width,
  ]);

  const toPoint = useCallback(
    (event: ReactPointerEvent<HTMLCanvasElement>) => {
      return clientToCanvas(
        event.clientX,
        event.clientY,
        event.currentTarget.getBoundingClientRect(),
        width,
        height,
      );
    },
    [height, width],
  );

  const paint = useCallback(
    (from: CanvasPoint, to: CanvasPoint, erase: boolean) => {
      const canvas = manualCanvasRef.current;
      const context = canvas?.getContext("2d");
      if (!canvas || !context) return;
      context.save();
      context.globalCompositeOperation = erase
        ? "destination-out"
        : "source-over";
      context.strokeStyle = "#ffffff";
      context.lineWidth = brushSize;
      context.lineCap = "round";
      context.lineJoin = "round";
      context.beginPath();
      context.moveTo(from.x, from.y);
      context.lineTo(to.x, to.y);
      context.stroke();
      context.restore();
    },
    [brushSize],
  );

  const handlePointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (tool === "inspect") return;
    const point = toPoint(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    if (tool === "positive" || tool === "negative") {
      onPoint(point, tool === "positive");
      return;
    }
    drawingRef.current = true;
    lastPointRef.current = point;
    if (tool === "box") {
      boxStartRef.current = point;
      setDraftBox({ x1: point.x, y1: point.y, x2: point.x, y2: point.y });
    } else {
      paint(point, point, tool === "eraser");
    }
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return;
    const point = toPoint(event);
    if (tool === "box" && boxStartRef.current) {
      const start = boxStartRef.current;
      setDraftBox({
        x1: Math.min(start.x, point.x),
        y1: Math.min(start.y, point.y),
        x2: Math.max(start.x, point.x),
        y2: Math.max(start.y, point.y),
      });
      return;
    }
    if ((tool === "brush" || tool === "eraser") && lastPointRef.current) {
      paint(lastPointRef.current, point, tool === "eraser");
      lastPointRef.current = point;
    }
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    if (tool === "box" && boxStartRef.current) {
      const start = boxStartRef.current;
      const end = toPoint(event);
      const finalBox = {
        x1: Math.min(start.x, end.x),
        y1: Math.min(start.y, end.y),
        x2: Math.max(start.x, end.x),
        y2: Math.max(start.y, end.y),
      };
      if (finalBox.x2 - finalBox.x1 > 2 && finalBox.y2 - finalBox.y1 > 2) {
        onBox(finalBox);
      }
      setDraftBox(null);
      boxStartRef.current = null;
    }
    if (tool === "brush" || tool === "eraser") {
      const canvas = manualCanvasRef.current;
      onManualMask(canvas ? canvas.toDataURL("image/png") : null);
    }
    lastPointRef.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Pointer capture may already be released by the browser.
    }
  };

  const cursorClass =
    tool === "brush" || tool === "eraser"
      ? "is-brush"
      : tool === "box"
        ? "is-crosshair"
        : tool === "inspect"
          ? "is-inspect"
          : "is-point";

  return (
    <div
      className="frame-gate"
      style={
        {
          aspectRatio: `${width} / ${height}`,
          "--frame-ratio": width / height,
        } as CSSProperties
      }
      aria-label={`Video frame ${frameIndex + 1}`}
    >
      <span className="frame-gate__corner frame-gate__corner--tl" />
      <span className="frame-gate__corner frame-gate__corner--tr" />
      <span className="frame-gate__corner frame-gate__corner--bl" />
      <span className="frame-gate__corner frame-gate__corner--br" />
      <div className={`video-canvas ${cursorClass} ${frameLoaded ? "is-loaded" : ""}`}>
        <canvas
          ref={imageCanvasRef}
          className="video-canvas__layer"
          width={width}
          height={height}
          aria-hidden="true"
        />
        {showTrackedMask && (
          <MaskOverlay
            width={width}
            height={height}
            src={api.maskUrl(project.id, frameIndex, maskRevision)}
          />
        )}
        <canvas
          ref={manualCanvasRef}
          className="video-canvas__layer video-canvas__manual"
          width={width}
          height={height}
          aria-hidden="true"
        />
        <canvas
          ref={promptCanvasRef}
          className="video-canvas__layer video-canvas__interaction"
          width={width}
          height={height}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          aria-label="Selection canvas. Use the active tool to mark the unwanted region."
        />
      </div>
      {!frameLoaded && <span className="canvas-loading">Loading frame…</span>}
      <span className="frame-gate__label">
        FRAME {String(frameIndex + 1).padStart(4, "0")}
      </span>
    </div>
  );
}

function drawPrompt(
  context: CanvasRenderingContext2D,
  point: CanvasPoint,
  positive: boolean,
  canvasWidth: number,
) {
  const radius = Math.max(6, canvasWidth * 0.012);
  context.save();
  context.beginPath();
  context.arc(point.x, point.y, radius, 0, Math.PI * 2);
  context.fillStyle = positive ? "#4db8d8" : "#e26d5a";
  context.fill();
  context.lineWidth = Math.max(2, canvasWidth * 0.003);
  context.strokeStyle = "#f8faf8";
  context.stroke();
  context.beginPath();
  context.moveTo(point.x - radius * 0.45, point.y);
  context.lineTo(point.x + radius * 0.45, point.y);
  if (positive) {
    context.moveTo(point.x, point.y - radius * 0.45);
    context.lineTo(point.x, point.y + radius * 0.45);
  }
  context.lineWidth = Math.max(1.5, canvasWidth * 0.002);
  context.strokeStyle = "#101416";
  context.stroke();
  context.restore();
}

function drawBox(
  context: CanvasRenderingContext2D,
  box: CanvasBox,
  canvasWidth: number,
) {
  context.save();
  context.fillStyle = "rgba(77, 184, 216, 0.15)";
  context.strokeStyle = "#74d2eb";
  context.lineWidth = Math.max(2, canvasWidth * 0.003);
  context.setLineDash([canvasWidth * 0.012, canvasWidth * 0.007]);
  context.fillRect(box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1);
  context.strokeRect(box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1);
  context.restore();
}
