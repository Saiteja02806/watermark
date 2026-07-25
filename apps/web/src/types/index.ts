export type ProjectStatus =
  | "CREATED"
  | "UPLOADING"
  | "UPLOADED"
  | "NORMALIZING"
  | "READY_FOR_SELECTION"
  | "GENERATING_MASKS"
  | "READY_FOR_MASK_REVIEW"
  | "INPAINTING"
  | "MUXING_AUDIO"
  | "COMPLETE"
  | "FAILED"
  | "CANCELLED";

export interface Project {
  id: string;
  name?: string;
  status: ProjectStatus;
  originalFilename?: string;
  fps?: number;
  frameCount?: number;
  width?: number;
  height?: number;
  processingWidth?: number;
  processingHeight?: number;
  durationSeconds?: number;
  createdAt: string;
  updatedAt: string;
  error?: string;
  trackerEngine?: string;
  inpaintingEngine?: string;
  suspiciousFrames: number[];
  hasAudio?: boolean;
  outputHasAudio?: boolean;
  outputDurationSeconds?: number;
  outputFrameCount?: number;
  outputWidth?: number;
  outputHeight?: number;
}

export type BatchStatus =
  | "CREATED"
  | "PREPARING"
  | "READY_FOR_SELECTION"
  | "TRACKING"
  | "READY_FOR_REVIEW"
  | "PROCESSING"
  | "COMPLETE"
  | "PARTIAL_COMPLETE"
  | "FAILED"
  | "CANCELLED";

export interface BatchItem extends Project {
  position: number;
  progress: number;
  message: string;
  jobStatus?: "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED" | "CANCELLED";
}

export interface Batch {
  id: string;
  name?: string;
  status: BatchStatus;
  progress: number;
  createdAt: string;
  updatedAt: string;
  items: BatchItem[];
}

export interface ProgressEvent {
  projectId: string;
  status: ProjectStatus;
  stage: string;
  progress: number;
  currentFrame?: number;
  totalFrames?: number;
  message: string;
  jobStatus?: "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED" | "CANCELLED";
  error?: string;
}

export interface Health {
  status: "ok" | "setup_required";
  localOnly: boolean;
  ffmpeg: boolean;
  ffprobe: boolean;
  sam2: boolean;
  propainter: boolean;
  fallbackTracking: boolean;
  fallbackInpainting: boolean;
  details: {
    sam2: {
      source: boolean;
      runtime: boolean;
      checkpoint: boolean;
      ready: boolean;
    };
    propainter: {
      source: boolean;
      runtime: boolean;
      weights: Record<string, boolean>;
      ready: boolean;
      missing: string[];
    };
    acceleration: {
      cudaAvailable: boolean;
      gpuName: string | null;
      torchVersion: string | null;
      error: string | null;
    };
  };
  limits: {
    maximumDurationSeconds: number;
    maximumProcessingLongEdge: number;
    selectedRegions: number;
    activeJobs: number;
    maximumBatchVideos: number;
  };
}

export interface QualityReport {
  valid: boolean;
  automatedChecksPassed: boolean;
  frameCount: number;
  selectedFrameCount: number;
  maskedBlackRatio: number;
  boundaryDifference: number;
  flickerScore: number;
  insideMeanAbsoluteChange: number;
  outsideMeanAbsoluteChange: number;
  humanReviewRequired: boolean;
  qualityWarnings: string[];
  encodedOutputInspected?: boolean;
  engine: "propainter" | "opencv";
}

export type EditorTool =
  | "positive"
  | "negative"
  | "box"
  | "brush"
  | "eraser"
  | "inspect";

export interface CanvasPoint {
  x: number;
  y: number;
}

export interface CanvasBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface AutoWatermarkResult {
  frameIndex: number;
  box: [number, number, number, number];
  manualMaskDataUrl: string;
  confidence: number;
  areaRatio: number;
}

export interface RenderSettings {
  quality: "fast" | "balanced" | "high";
  resolution: "480p" | "720p";
  maskExpansion: 2 | 4 | 8 | 12;
  preserveAudio: boolean;
  engine: "auto" | "propainter" | "opencv";
}
