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
  /** One-click Falstad URL — opens the circuit running in a browser simulator. */
  simulate_url?: string;
  /** Quick stats about what's simulatable (counts, supply voltage, skipped refs). */
  simulate_summary?: {
    supply_voltage?: number;
    simulatable_count?: number;
    total_components?: number;
    skipped_refs?: string[];
    ok?: boolean;
    reason?: string | null;
    error?: string;
  };
}

export interface GerberData {
  download_url: string | null;
  filename?: string;
  bundle_includes?: string[];
  cpl_url?: string | null;
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
  unit_price_usd?: number | null;
  extended_price_usd?: number | null;
}

export interface CostEstimate {
  qty: number;
  parts: number;
  pcb_fab: number;
  smt_setup: number;
  smt_placement: number;
  stencil: number;
  shipping: number;
  total: number;
  smt_joints: number;
}

export interface BomData {
  project_name: string;
  lines: BomLine[];
  total_unique: number;
  total_quantity: number;
  total_unit_cost_usd?: number;
  priced_line_count?: number;
  currency?: string;
  smt_joints?: number;
  cost_estimates?: CostEstimate[];
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
