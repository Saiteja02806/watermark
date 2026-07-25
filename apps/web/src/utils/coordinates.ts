import type { CanvasPoint } from "../types";

export function clientToCanvas(
  clientX: number,
  clientY: number,
  bounds: Pick<DOMRect, "left" | "top" | "width" | "height">,
  canvasWidth: number,
  canvasHeight: number,
): CanvasPoint {
  return {
    x: Math.max(
      0,
      Math.min(canvasWidth, ((clientX - bounds.left) / bounds.width) * canvasWidth),
    ),
    y: Math.max(
      0,
      Math.min(
        canvasHeight,
        ((clientY - bounds.top) / bounds.height) * canvasHeight,
      ),
    ),
  };
}

export function frameToTime(frameIndex: number, fps = 30): number {
  return Math.max(0, frameIndex / fps);
}

export function formatTime(seconds = 0): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds - minutes * 60;
  return `${minutes}:${remainder.toFixed(2).padStart(5, "0")}`;
}

