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

export interface BomLine {
  line_id: number;
  references: string[];
  quantity: number;
  type: string;
  value?: string | null;
  description: string;
  package?: string | null;
  category: string;
  notes?: string | null;
  lcsc_part_number?: string | null;
  manufacturer_pn?: string | null;
  manufacturer?: string | null;
}

export interface BomData {
  project_name: string;
  lines: BomLine[];
  total_unique: number;
  total_quantity: number;
  artifacts?: {
    bom_csv?: string;
    bom_jlcpcb_csv?: string;
    bom_json?: string;
  };
  filenames?: {
    bom_csv?: string;
    bom_jlcpcb_csv?: string;
  };
}

// UI-side log line shape used inside PipelineProgress.
export interface LogEntry {
  level: "info" | "ok" | "warn" | "err";
  msg: string;
}

export interface ArtifactInfo {
  name: string;
  url: string;
}

export interface JobSnapshot {
  job_id: string;
  complete: boolean;
  events: PipelineEvent[];
  artifacts: ArtifactInfo[];
  parent_job_id?: string | null;
  instruction?: string | null;
  revision: number;
  description: string;
  created_at: number;
}

export interface JobSummary {
  job_id: string;
  description: string;
  instruction?: string | null;
  parent_job_id?: string | null;
  revision: number;
  complete: boolean;
  components: number;
  nets: number;
  created_at: number;
}

export interface LineageEntry {
  job_id: string;
  revision: number;
  title: string;
  complete: boolean;
}
