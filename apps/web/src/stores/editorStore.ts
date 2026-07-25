import { create } from "zustand";
import type {
  CanvasBox,
  CanvasPoint,
  EditorTool,
  ProgressEvent,
  Project,
  RenderSettings,
} from "../types";

interface EditorState {
  project: Project | null;
  progress: ProgressEvent | null;
  frameIndex: number;
  tool: EditorTool;
  brushSize: number;
  positivePoints: CanvasPoint[];
  negativePoints: CanvasPoint[];
  box: CanvasBox | null;
  manualMask: string | null;
  maskRevision: number;
  isLocked: boolean;
  screenFixed: boolean;
  renderSettings: RenderSettings;
  setProject: (project: Project | null) => void;
  setProgress: (progress: ProgressEvent | null) => void;
  setFrameIndex: (index: number) => void;
  setTool: (tool: EditorTool) => void;
  setBrushSize: (size: number) => void;
  addPoint: (point: CanvasPoint, positive: boolean) => void;
  setBox: (box: CanvasBox | null) => void;
  setManualMask: (mask: string | null) => void;
  bumpMaskRevision: () => void;
  setLocked: (locked: boolean) => void;
  setScreenFixed: (fixed: boolean) => void;
  setRenderSettings: (settings: Partial<RenderSettings>) => void;
  clearPrompts: () => void;
  reset: () => void;
}

const initialSettings: RenderSettings = {
  quality: "balanced",
  resolution: "720p",
  maskExpansion: 4,
  preserveAudio: true,
  engine: "auto",
};

export const useEditorStore = create<EditorState>((set) => ({
  project: null,
  progress: null,
  frameIndex: 0,
  tool: "positive",
  brushSize: 24,
  positivePoints: [],
  negativePoints: [],
  box: null,
  manualMask: null,
  maskRevision: 0,
  isLocked: false,
  screenFixed: false,
  renderSettings: initialSettings,
  setProject: (project) => set({ project }),
  setProgress: (progress) => set({ progress }),
  setFrameIndex: (frameIndex) =>
    set({
      frameIndex,
      positivePoints: [],
      negativePoints: [],
      box: null,
      manualMask: null,
      isLocked: false,
    }),
  setTool: (tool) => set({ tool }),
  setBrushSize: (brushSize) => set({ brushSize }),
  addPoint: (point, positive) =>
    set((state) =>
      positive
        ? { positivePoints: [...state.positivePoints, point] }
        : { negativePoints: [...state.negativePoints, point] },
    ),
  setBox: (box) => set({ box }),
  setManualMask: (manualMask) => set({ manualMask }),
  bumpMaskRevision: () =>
    set((state) => ({ maskRevision: state.maskRevision + 1 })),
  setLocked: (isLocked) => set({ isLocked }),
  setScreenFixed: (screenFixed) => set({ screenFixed }),
  setRenderSettings: (settings) =>
    set((state) => ({
      renderSettings: { ...state.renderSettings, ...settings },
    })),
  clearPrompts: () =>
    set({
      positivePoints: [],
      negativePoints: [],
      box: null,
      manualMask: null,
      isLocked: false,
      screenFixed: false,
    }),
  reset: () =>
    set({
      project: null,
      progress: null,
      frameIndex: 0,
      tool: "positive",
      brushSize: 24,
      positivePoints: [],
      negativePoints: [],
      box: null,
      manualMask: null,
      maskRevision: 0,
      isLocked: false,
      screenFixed: false,
      renderSettings: initialSettings,
    }),
}));
