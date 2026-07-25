import {
  BoxSelect,
  Brush,
  CircleMinus,
  CirclePlus,
  Eraser,
  Eye,
  RotateCcw,
} from "lucide-react";
import type { EditorTool } from "../types";

interface MaskToolbarProps {
  tool: EditorTool;
  brushSize: number;
  onTool: (tool: EditorTool) => void;
  onBrushSize: (size: number) => void;
  onClear: () => void;
}

const tools: Array<{
  id: EditorTool;
  label: string;
  hint: string;
  icon: typeof CirclePlus;
}> = [
  {
    id: "positive",
    label: "Include",
    hint: "Click inside the object",
    icon: CirclePlus,
  },
  {
    id: "negative",
    label: "Exclude",
    hint: "Click outside incorrect areas",
    icon: CircleMinus,
  },
  {
    id: "box",
    label: "Box",
    hint: "Drag around a rectangular region",
    icon: BoxSelect,
  },
  {
    id: "brush",
    label: "Brush",
    hint: "Paint a precise removal mask",
    icon: Brush,
  },
  {
    id: "eraser",
    label: "Eraser",
    hint: "Remove painted mask areas",
    icon: Eraser,
  },
  {
    id: "inspect",
    label: "Inspect",
    hint: "Review without adding marks",
    icon: Eye,
  },
];

export function MaskToolbar({
  tool,
  brushSize,
  onTool,
  onBrushSize,
  onClear,
}: MaskToolbarProps) {
  return (
    <aside className="tool-rail" aria-label="Selection tools">
      <div className="tool-rail__heading">
        <span>Mask tools</span>
        <button className="icon-button" type="button" onClick={onClear} title="Clear marks">
          <RotateCcw size={15} />
          <span className="visually-hidden">Clear marks</span>
        </button>
      </div>
      <div className="tool-list">
        {tools.map(({ id, label, hint, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={`tool-button ${tool === id ? "is-active" : ""}`}
            aria-pressed={tool === id}
            title={hint}
            onClick={() => onTool(id)}
          >
            <Icon size={18} strokeWidth={1.8} />
            <span>{label}</span>
          </button>
        ))}
      </div>
      {(tool === "brush" || tool === "eraser") && (
        <label className="brush-size">
          <span>
            Brush size <strong>{brushSize}px</strong>
          </span>
          <input
            type="range"
            min="4"
            max="80"
            step="2"
            value={brushSize}
            onChange={(event) => onBrushSize(Number(event.currentTarget.value))}
          />
        </label>
      )}
      <p className="tool-hint">
        {tools.find((entry) => entry.id === tool)?.hint}
      </p>
    </aside>
  );
}

