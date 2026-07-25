import { useEffect, useRef } from "react";

interface MaskOverlayProps {
  width: number;
  height: number;
  src: string | null;
}

export function MaskOverlay({ width, height, src }: MaskOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return;
    context.clearRect(0, 0, width, height);
    if (!src) return;
    const image = new Image();
    image.onload = () => {
      context.clearRect(0, 0, width, height);
      context.drawImage(image, 0, 0, width, height);
      const pixels = context.getImageData(0, 0, width, height);
      for (let index = 0; index < pixels.data.length; index += 4) {
        const selected = pixels.data[index] >= 128;
        pixels.data[index] = 65;
        pixels.data[index + 1] = 191;
        pixels.data[index + 2] = 220;
        pixels.data[index + 3] = selected ? 112 : 0;
      }
      context.putImageData(pixels, 0, 0);
    };
    image.onerror = () => context.clearRect(0, 0, width, height);
    image.src = src;
  }, [height, src, width]);

  return (
    <canvas
      ref={canvasRef}
      className="video-canvas__layer"
      width={width}
      height={height}
      aria-hidden="true"
    />
  );
}

