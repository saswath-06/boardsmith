// TypeScript interfaces mirroring backend/app/models.py

export type StageStatus = "running" | "complete" | "error";

export interface PipelineEvent {
  stage: string;
  status: StageStatus;
  data?: unknown;
  message: string;
}

export interface Pad {
  ref: string;
  pin: string;
  net?: string | null;
  x: number;
  y: number;
  w?: number;
  h?: number;
}

export interface LayoutComponent {
  ref: string;
  type: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation?: number;
  color: string;
  pads: Pad[];
}

export interface Segment {
  net: string;
  points: Array<[number, number]>;
  routed?: boolean;
}

export interface RatsnestLine {
  net: string;
  from_point: [number, number];
  to_point: [number, number];
}

export interface BoardInfo {
  width: number;
  height: number;
  thickness?: number;
}

export interface Board3DData {
  board: BoardInfo;
  components: LayoutComponent[];
  traces: Segment[];
  ratsnest: RatsnestLine[];
}

export interface SchematicData {
  svg: string;
  artifacts?: Record<string, string>;
  /** Display/download name for KiCad schematic (matches backend slugged project name). */
  kicad_filename?: string;
}

export interface GerberData {
  download_url: string | null;
  filename?: string;
}

// UI-side log line shape used inside PipelineProgress.
export interface LogEntry {
  level: "info" | "ok" | "warn" | "err";
  msg: string;
}
