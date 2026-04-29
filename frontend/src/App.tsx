// Boardsmith — main app shell.
// Single persistent dashboard with a Jobs sidebar that's always visible.
// When no project is selected, the center pane shows a welcome / new-project
// prompt instead of switching to a separate splash screen.
import { useEffect, useRef, useState } from "react";
import { Route, Routes } from "react-router-dom";
import AuthGate from "./components/AuthGate";
import DesignNotes from "./components/DesignNotes";
import LineageBreadcrumb from "./components/LineageBreadcrumb";
import BoardsmithLogo from "./components/Logo";
import PipelineProgress from "./components/PipelineProgress";
import PromptComposer from "./components/PromptComposer";
import PromptHistory from "./components/PromptHistory";
import PublicViewer from "./components/PublicViewer";
import RefinePanel from "./components/RefinePanel";
import ViewerTabs from "./components/Viewers";
import {
  createJob,
  deleteJob,
  getJob,
  getLineage,
  listJobs,
  publishJob,
  refineJob,
  subscribeToJob,
} from "./api";
import { AuthProvider, useAuth } from "./lib/auth";
import type {
  Board3DData,
  BomData,
  FirmwareData,
  GerberData,
  JobSnapshot,
  LineageEntry,
  LogEntry,
  PipelineEvent,
  SchematicData,
  StageStatus,
} from "./types";

const DEMO_PROMPT =
  "An ESP32 microcontroller connected to a DHT22 temperature sensor, an LED indicator with a current limiting resistor, and a USB-C power input with an AMS1117 3.3V regulator and decoupling capacitors.";

const SAMPLE_PROMPTS = [
  "ESP32 + DHT22 + LED + USB-C power",
  "Arduino Nano + MPU6050 + JST connector",
  "STM32F103 + BMP280 + AMS1117 regulator",
  "ATtiny85 blinker · 3 LEDs",
];

type StageRowStatus = StageStatus | "waiting";

// ── Top bar (active mode) ────────────────────────────────────────────────
interface TopBarProps {
  description: string;
  running: boolean;
  jobId: string | null;
  activeJobId: string | null;
  onSubmit: () => void;
  onDescriptionChange: (value: string) => void;
  onReset: () => void;
}

const TopBar = ({ description, running, jobId, activeJobId, onSubmit, onDescriptionChange, onReset }: TopBarProps) => {
  const { user, signOut } = useAuth();
  const breadcrumb = jobId ? jobId.slice(0, 8) : "—";
  const initials = (user?.email ?? "?").slice(0, 2).toUpperCase();
  const avatarUrl = (user?.user_metadata?.avatar_url as string | undefined) ?? null;
  const [shareState, setShareState] = useState<"idle" | "publishing" | "copied" | "error">(
    "idle",
  );

  // Share button is only useful when there's a complete project we can
  // generate a public link for. Disable it during the build to avoid
  // sharing half-rendered jobs.
  const canShare = activeJobId !== null && !running && shareState !== "publishing";

  const handleShare = async () => {
    if (!activeJobId) return;
    setShareState("publishing");
    try {
      const { share_url } = await publishJob(activeJobId);
      const fullUrl = `${window.location.origin}${share_url}`;
      try {
        await navigator.clipboard.writeText(fullUrl);
      } catch {
        // Fallback: still surface the URL even if clipboard write is blocked.
        window.prompt("Copy this link to share", fullUrl);
      }
      setShareState("copied");
      window.setTimeout(() => setShareState("idle"), 2000);
    } catch {
      setShareState("error");
      window.setTimeout(() => setShareState("idle"), 2000);
    }
  };

  return (
    <header className="flex items-center gap-4 px-4 h-12 border-b shrink-0"
      style={{ borderColor: "var(--bs-line-soft)", background: "var(--bs-bg-2)" }}>
      <button onClick={onReset} className="flex items-center gap-2.5 shrink-0">
        <BoardsmithLogo size={26} />
        <span className="text-[15px] font-semibold tracking-tight" style={{ color: "var(--bs-fg)" }}>
          Boardsmith
        </span>
      </button>

      <div className="hidden md:flex items-center gap-2 font-mono text-[11px]" style={{ color: "var(--bs-fg-dim)" }}>
        <span>/</span>
        <span style={{ color: "var(--bs-fg-mute)" }}>{breadcrumb}</span>
      </div>

      <div className="flex-1 flex items-center gap-2 max-w-3xl">
        <div className="flex-1 flex items-center gap-2 px-3 h-8 rounded"
          style={{ background: "var(--bs-bg)", border: "1px solid var(--bs-line)" }}>
          <span className="font-mono text-[11px] shrink-0" style={{ color: "var(--bs-copper)" }}>$</span>
          <input
            type="text"
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            placeholder="Describe a circuit…"
            className="flex-1 bg-transparent outline-none text-[13px] font-mono"
            style={{ color: "var(--bs-fg)" }}
            onKeyDown={(e) => { if (e.key === "Enter" && !running) onSubmit(); }}
          />
          <span className="font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
            ⏎
          </span>
        </div>
        <button
          onClick={onSubmit}
          disabled={running}
          className="bs-btn-primary px-4 h-8 rounded text-[13px] flex items-center gap-2 shrink-0">
          {running ? <><span className="bs-spin"/>Building…</> : "Generate"}
        </button>
      </div>

      <div className="flex items-center gap-3 shrink-0 font-mono text-[10px] uppercase tracking-wider"
        style={{ color: "var(--bs-fg-dim)" }}>
        {activeJobId !== null && (
          <button
            onClick={() => void handleShare()}
            disabled={!canShare}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded transition-colors normal-case tracking-normal"
            style={{
              border: "1px solid var(--bs-line-soft)",
              color:
                shareState === "copied"
                  ? "var(--bs-lime)"
                  : shareState === "error"
                  ? "var(--bs-red)"
                  : "var(--bs-fg-mute)",
              background: "var(--bs-bg)",
              opacity: canShare ? 1 : 0.55,
              cursor: canShare ? "pointer" : "default",
            }}
            onMouseEnter={(e) => {
              if (!canShare) return;
              e.currentTarget.style.borderColor = "var(--bs-copper)";
              e.currentTarget.style.color = "var(--bs-copper-2)";
            }}
            onMouseLeave={(e) => {
              if (shareState !== "idle") return;
              e.currentTarget.style.borderColor = "var(--bs-line-soft)";
              e.currentTarget.style.color = "var(--bs-fg-mute)";
            }}
            title="Publish a public read-only link to this project"
          >
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path
                d="M11 2.5a2 2 0 11-2 2 2 2 0 012-2zm-6 4.5a2 2 0 11-2 2 2 2 0 012-2zm6 4a2 2 0 11-2 2 2 2 0 012-2zM6.6 7.6l3.3-2M6.6 9.4l3.3 2"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="text-[11px]">
              {shareState === "publishing"
                ? "Publishing…"
                : shareState === "copied"
                ? "Link copied"
                : shareState === "error"
                ? "Share failed"
                : "Share"}
            </span>
          </button>
        )}
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bs-pulse"
            style={{ background: running ? "var(--bs-cyan)" : "var(--bs-lime)" }}/>
          {running ? "Running" : "Ready"}
        </span>
        <span style={{ color: "var(--bs-line)" }}>·</span>
        <div className="flex items-center gap-2">
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt=""
              className="h-5 w-5 rounded-full"
              style={{ border: "1px solid var(--bs-line)" }}
            />
          ) : (
            <span
              className="h-5 w-5 rounded-full flex items-center justify-center text-[9px] font-semibold"
              style={{
                background: "var(--bs-panel-2)",
                border: "1px solid var(--bs-line)",
                color: "var(--bs-fg)",
              }}
            >
              {initials}
            </span>
          )}
          <span className="hidden lg:inline normal-case tracking-normal" style={{ color: "var(--bs-fg-mute)" }}>
            {user?.email}
          </span>
          <button
            onClick={() => void signOut()}
            className="font-mono text-[10px] uppercase tracking-widest hover:text-[color:var(--bs-copper)]"
            style={{ color: "var(--bs-fg-dim)" }}
            title="Sign out"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
};

// ── Welcome pane (in-dashboard, shown when no project is selected) ───────
interface WelcomePaneProps {
  description: string;
  image: File | null;
  running: boolean;
  hasJobs: boolean;
  onDescriptionChange: (value: string) => void;
  onImageChange: (file: File | null) => void;
  onSubmit: () => void;
}

const WelcomePane = ({
  description,
  image,
  running,
  hasJobs,
  onDescriptionChange,
  onImageChange,
  onSubmit,
}: WelcomePaneProps) => {
  const heading = hasJobs ? "Start a new project" : "Describe your first circuit";
  const lede = hasJobs
    ? "Pick a project from the sidebar to review or refine, or kick off a new design below."
    : "Boardsmith turns plain English into the full pipeline — schematic, layout, 3D render, and Gerbers — live in your browser.";

  return (
    <section
      className="bs-panel flex h-full min-h-0 flex-col items-center overflow-y-auto bs-scroll bs-bg-grid"
      style={{ background: "var(--bs-panel)" }}
    >
      <div className="w-full max-w-2xl flex flex-col items-center text-center px-6 py-12">
        <div className="flex items-center gap-3 mb-6">
          <BoardsmithLogo size={42} />
          <div className="flex flex-col items-start">
            <span className="text-[22px] font-semibold tracking-tight leading-none" style={{ color: "var(--bs-fg)" }}>
              Boardsmith
            </span>
            <span className="font-mono text-[10px] mt-1 uppercase tracking-[0.2em]" style={{ color: "var(--bs-copper)" }}>
              PCB · forged in plain English
            </span>
          </div>
        </div>

        <h1
          className="mb-3 max-w-xl text-[28px] leading-[1.1] font-semibold tracking-tight"
          style={{ color: "var(--bs-fg)" }}
        >
          {heading}
        </h1>

        <p
          className="mb-8 max-w-md text-[13.5px] leading-relaxed"
          style={{ color: "var(--bs-fg-mute)" }}
        >
          {lede}
        </p>

        <PromptComposer
          description={description}
          image={image}
          running={running}
          onDescriptionChange={onDescriptionChange}
          onImageChange={onImageChange}
          onSubmit={onSubmit}
        />

        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--bs-fg-dim)" }}>
            Try:
          </span>
          {SAMPLE_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => onDescriptionChange(p)}
              className="px-3 py-1 rounded-full text-[11.5px] transition-colors"
              style={{ border: "1px solid var(--bs-line)", color: "var(--bs-fg-mute)", background: "var(--bs-bg-2)" }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "var(--bs-copper)";
                e.currentTarget.style.color = "var(--bs-copper-2)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "var(--bs-line)";
                e.currentTarget.style.color = "var(--bs-fg-mute)";
              }}
            >
              {p}
            </button>
          ))}
        </div>

        <div className="mt-10 grid grid-cols-3 gap-6 max-w-xl text-left">
          {[
            ["01", "Schematic", "custom SVG · KiCad sch"],
            ["02", "PCB layout", "force-directed + Lee router"],
            ["03", "Gerber",    "RS-274X · JLCPCB-ready"],
          ].map(([n, t, s]) => (
            <div key={n}>
              <div className="font-mono text-[10px] mb-1" style={{ color: "var(--bs-copper)" }}>STAGE {n}</div>
              <div className="text-[12.5px] font-medium" style={{ color: "var(--bs-fg)" }}>{t}</div>
              <div className="font-mono text-[10px] mt-0.5" style={{ color: "var(--bs-fg-dim)" }}>{s}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

// ── SSE-backed pipeline hook (real backend) ──────────────────────────────
interface PipelineState {
  running: boolean;
  jobId: string | null;
  activeJobId: string | null;
  stageStatus: Record<string, StageRowStatus>;
  stageLogs: Record<string, LogEntry[]>;
  activeStage: string | null;
  data: Board3DData | null;
  schematic: SchematicData | null;
  gerber: GerberData | null;
  bom: BomData | null;
  firmware: FirmwareData | null;
  designNotes: string[];
  lineage: LineageEntry[];
  jobsBump: number;
  start: (description: string, image?: File | null) => Promise<void>;
  refine: (instruction: string) => Promise<void>;
  loadJob: (jobId: string) => Promise<void>;
  reset: () => void;
  /** Clear the active job iff it (or one of its revisions) was deleted. */
  clearActiveIfDeleted: (deletedIds: string[]) => void;
  /** Force the jobs sidebar to re-fetch from the backend. */
  bumpJobs: () => void;
}

// Pure function: rebuild viewer state from a snapshot's stored events.
function projectSnapshot(snapshot: JobSnapshot): {
  stageStatus: Record<string, StageRowStatus>;
  stageLogs: Record<string, LogEntry[]>;
  data: Board3DData | null;
  schematic: SchematicData | null;
  gerber: GerberData | null;
  bom: BomData | null;
  firmware: FirmwareData | null;
  designNotes: string[];
} {
  const stageStatus: Record<string, StageRowStatus> = {};
  const stageLogs: Record<string, LogEntry[]> = {};
  let data: Board3DData | null = null;
  let schematic: SchematicData | null = null;
  let gerber: GerberData | null = null;
  let bom: BomData | null = null;
  let firmware: FirmwareData | null = null;
  let designNotes: string[] = [];

  for (const event of snapshot.events) {
    const stage = event.stage;
    if (stage === "done") continue;

    if (event.status === "running") {
      stageStatus[stage] = "running";
      (stageLogs[stage] ??= []).push({ level: "info", msg: event.message });
      continue;
    }
    if (event.status === "complete") {
      stageStatus[stage] = "complete";
      (stageLogs[stage] ??= []).push({ level: "ok", msg: event.message });

      const payload = event.data as Record<string, unknown> | null | undefined;
      if (stage === "parse" && payload && typeof payload === "object" && "design_decisions" in payload) {
        const notes = (payload as { design_decisions?: unknown }).design_decisions;
        if (Array.isArray(notes)) {
          designNotes = notes.filter((n): n is string => typeof n === "string");
        }
      }
      if (stage === "schematic" && payload && typeof payload === "object" && "svg" in payload) {
        schematic = payload as unknown as SchematicData;
      }
      if (stage === "3d" && payload && typeof payload === "object" && "components" in payload) {
        data = payload as unknown as Board3DData;
      }
      if (stage === "gerber" && payload && typeof payload === "object" && "download_url" in payload) {
        gerber = payload as unknown as GerberData;
      }
      if (stage === "bom" && payload && typeof payload === "object" && "lines" in payload) {
        bom = payload as unknown as BomData;
      }
      if (stage === "firmware" && payload && typeof payload === "object" && "code" in payload) {
        firmware = payload as unknown as FirmwareData;
      }
      continue;
    }
    if (event.status === "error") {
      (stageLogs[stage] ??= []).push({ level: "warn", msg: event.message });
    }
  }

  return { stageStatus, stageLogs, data, schematic, gerber, bom, firmware, designNotes };
}

function useRealPipeline(): PipelineState {
  const [running, setRunning] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [stageStatus, setStageStatus] = useState<Record<string, StageRowStatus>>({});
  const [stageLogs, setStageLogs] = useState<Record<string, LogEntry[]>>({});
  const [activeStage, setActiveStage] = useState<string | null>(null);
  const [data, setData] = useState<Board3DData | null>(null);
  const [schematic, setSchematic] = useState<SchematicData | null>(null);
  const [gerber, setGerber] = useState<GerberData | null>(null);
  const [bom, setBom] = useState<BomData | null>(null);
  const [firmware, setFirmware] = useState<FirmwareData | null>(null);
  const [designNotes, setDesignNotes] = useState<string[]>([]);
  const [lineage, setLineage] = useState<LineageEntry[]>([]);
  const [jobsBump, setJobsBump] = useState(0);

  const sourceRef = useRef<EventSource | null>(null);
  const streamingJobRef = useRef<string | null>(null);

  const closeSource = () => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
  };

  const clearViewerState = () => {
    setStageStatus({});
    setStageLogs({});
    setActiveStage(null);
    setData(null);
    setSchematic(null);
    setGerber(null);
    setBom(null);
    setFirmware(null);
    setDesignNotes([]);
  };

  const reset = () => {
    closeSource();
    streamingJobRef.current = null;
    setRunning(false);
    setJobId(null);
    setActiveJobId(null);
    setLineage([]);
    clearViewerState();
  };

  const appendLog = (stage: string, entry: LogEntry) => {
    setStageLogs((prev) => ({ ...prev, [stage]: [...(prev[stage] ?? []), entry] }));
  };

  const refreshLineage = async (id: string) => {
    try {
      const chain = await getLineage(id);
      setLineage(chain);
    } catch {
      setLineage([]);
    }
  };

  const handleEvent = (event: PipelineEvent) => {
    const stage = event.stage;

    if (stage === "done") {
      closeSource();
      setRunning(false);
      setActiveStage(null);
      setJobsBump((n) => n + 1);
      const finishedId = streamingJobRef.current;
      if (finishedId) {
        void refreshLineage(finishedId);
      }
      return;
    }

    if (event.status === "running") {
      setActiveStage(stage);
      setStageStatus((s) => ({ ...s, [stage]: "running" }));
      appendLog(stage, { level: "info", msg: event.message });
      return;
    }

    if (event.status === "complete") {
      setStageStatus((s) => ({ ...s, [stage]: "complete" }));
      appendLog(stage, { level: "ok", msg: event.message });

      const payload = event.data as Record<string, unknown> | null | undefined;
      if (stage === "parse" && payload && typeof payload === "object" && "design_decisions" in payload) {
        const notes = (payload as { design_decisions?: unknown }).design_decisions;
        if (Array.isArray(notes)) {
          setDesignNotes(notes.filter((n): n is string => typeof n === "string"));
        }
      }
      if (stage === "schematic" && payload && typeof payload === "object" && "svg" in payload) {
        setSchematic(payload as unknown as SchematicData);
      }
      if (stage === "3d" && payload && typeof payload === "object" && "components" in payload) {
        setData(payload as unknown as Board3DData);
      }
      if (stage === "gerber" && payload && typeof payload === "object" && "download_url" in payload) {
        setGerber(payload as unknown as GerberData);
      }
      if (stage === "bom" && payload && typeof payload === "object" && "lines" in payload) {
        setBom(payload as unknown as BomData);
      }
      if (stage === "firmware" && payload && typeof payload === "object" && "code" in payload) {
        setFirmware(payload as unknown as FirmwareData);
      }
      return;
    }

    if (event.status === "error") {
      appendLog(stage, { level: "warn", msg: event.message });
    }
  };

  const stream = async (newJobId: string) => {
    closeSource();
    streamingJobRef.current = newJobId;
    setJobId(newJobId);
    setActiveJobId(newJobId);
    clearViewerState();
    setRunning(true);
    setJobsBump((n) => n + 1);
    void refreshLineage(newJobId);
    const source = await subscribeToJob(newJobId, handleEvent, () => {
      closeSource();
      setRunning(false);
    });
    sourceRef.current = source;
  };

  const start = async (description: string, image?: File | null) => {
    try {
      const { job_id } = await createJob(description, image ?? null);
      await stream(job_id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      appendLog("parse", { level: "err", msg: `Failed to start job: ${msg}` });
      setRunning(false);
    }
  };

  const refine = async (instruction: string) => {
    if (!activeJobId) return;
    try {
      const { job_id } = await refineJob(activeJobId, instruction);
      await stream(job_id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      appendLog("parse", { level: "err", msg: `Failed to refine job: ${msg}` });
    }
  };

  const loadJob = async (id: string) => {
    closeSource();
    streamingJobRef.current = null;
    setRunning(false);
    try {
      const snapshot = await getJob(id);
      const projected = projectSnapshot(snapshot);
      setJobId(id);
      setActiveJobId(id);
      setStageStatus(projected.stageStatus);
      setStageLogs(projected.stageLogs);
      setActiveStage(null);
      setData(projected.data);
      setSchematic(projected.schematic);
      setGerber(projected.gerber);
      setBom(projected.bom);
      setFirmware(projected.firmware);
      setDesignNotes(projected.designNotes);
      void refreshLineage(id);
      // If this snapshot is still in progress, hop on its event stream.
      if (!snapshot.complete) {
        streamingJobRef.current = id;
        setRunning(true);
        const source = await subscribeToJob(id, handleEvent, () => {
          closeSource();
          setRunning(false);
        });
        sourceRef.current = source;
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      appendLog("parse", { level: "err", msg: `Failed to load job: ${msg}` });
    }
  };

  useEffect(() => {
    return () => {
      closeSource();
    };
  }, []);

  const clearActiveIfDeleted = (deletedIds: string[]) => {
    if (activeJobId && deletedIds.includes(activeJobId)) {
      reset();
    }
  };

  const bumpJobs = () => setJobsBump((n) => n + 1);

  return {
    running,
    jobId,
    activeJobId,
    stageStatus,
    stageLogs,
    activeStage,
    data,
    schematic,
    gerber,
    bom,
    firmware,
    designNotes,
    lineage,
    jobsBump,
    start,
    refine,
    loadJob,
    reset,
    clearActiveIfDeleted,
    bumpJobs,
  };
}

// ── Collapsed rail — thin 32px column shown in place of an expanded
// sidebar. Click to expand. Used for both Jobs and Pipeline.
interface CollapsedRailProps {
  label: string;
  onExpand: () => void;
}

const CollapsedRail = ({ label, onExpand }: CollapsedRailProps) => (
  <button
    type="button"
    onClick={onExpand}
    className="bs-panel h-full flex flex-col items-center justify-between py-3 transition-colors"
    style={{ width: 32, cursor: "pointer", color: "var(--bs-fg-mute)" }}
    onMouseEnter={(e) => {
      e.currentTarget.style.borderColor = "var(--bs-copper)";
      e.currentTarget.style.color = "var(--bs-fg)";
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.borderColor = "var(--bs-line)";
      e.currentTarget.style.color = "var(--bs-fg-mute)";
    }}
    title={`Expand ${label.toLowerCase()} column`}
    aria-label={`Expand ${label.toLowerCase()} column`}
  >
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden>
      <path d="M4.5 2.5l3 3.5-3 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
    <span
      className="font-mono text-[10px] uppercase tracking-[0.18em]"
      style={{
        // Rotate the label so it reads vertically up the rail. The
        // `writing-mode` would be cleaner but breaks letter-spacing in
        // some browsers, so transform-rotate it is.
        transform: "rotate(180deg)",
        writingMode: "vertical-rl",
        color: "var(--bs-fg-mute)",
      }}
    >
      {label}
    </span>
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden>
      <path d="M4.5 2.5l3 3.5-3 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  </button>
);

// ── Dashboard: persistent layout with always-visible Jobs sidebar ────────
interface DashboardProps {
  description: string;
  image: File | null;
  hasJobs: boolean;
  pipeline: PipelineState;
  jobsCollapsed: boolean;
  pipelineCollapsed: boolean;
  onSubmit: () => void;
  onDescriptionChange: (value: string) => void;
  onImageChange: (file: File | null) => void;
  onNew: () => void;
  onToggleJobs: () => void;
  onTogglePipeline: () => void;
}

const Dashboard = ({
  description,
  image,
  hasJobs,
  pipeline,
  jobsCollapsed,
  pipelineCollapsed,
  onSubmit,
  onDescriptionChange,
  onImageChange,
  onNew,
  onToggleJobs,
  onTogglePipeline,
}: DashboardProps) => {
  const hasProject = pipeline.activeJobId !== null;
  const recentInstructions = pipeline.lineage
    .filter((entry) => entry.revision > 0)
    .map((entry) => entry.title);

  // Build the grid template columns based on collapsed state. A
  // collapsed column is rendered as a thin 32px rail; an expanded
  // column gets its full width back. The rightmost workspace pane
  // always claims whatever's left over (1fr).
  const jobsCol = jobsCollapsed ? "32px" : "240px";
  const pipelineCol = pipelineCollapsed ? "32px" : "320px";
  const gridTemplateColumns = hasProject
    ? `${jobsCol} ${pipelineCol} 1fr`
    : `${jobsCol} 1fr`;

  return (
    <div className="h-screen flex flex-col">
      <TopBar
        description={description}
        running={pipeline.running}
        jobId={pipeline.jobId}
        activeJobId={pipeline.activeJobId}
        onSubmit={onSubmit}
        onDescriptionChange={onDescriptionChange}
        onReset={onNew}
      />
      <main
        className="flex-1 grid gap-2 p-2 min-h-0"
        style={{ gridTemplateColumns }}
      >
        {jobsCollapsed ? (
          <CollapsedRail label="Jobs" onExpand={onToggleJobs} />
        ) : (
          <PromptHistory
            activeId={pipeline.activeJobId}
            bump={pipeline.jobsBump}
            onSelect={(id) => void pipeline.loadJob(id)}
            onNew={onNew}
            onCollapse={onToggleJobs}
            onDelete={async (id) => {
              const deleted = await deleteJob(id);
              // If the active project (or one of its revisions) was deleted,
              // drop back to the welcome pane.
              pipeline.clearActiveIfDeleted(deleted);
              // Bump to re-fetch — keeps any other tabs / lineage state in sync.
              pipeline.bumpJobs();
              return deleted;
            }}
          />
        )}
        {hasProject ? (
          <>
            {pipelineCollapsed ? (
              <CollapsedRail label="Pipeline" onExpand={onTogglePipeline} />
            ) : (
              <PipelineProgress
                stageStatus={pipeline.stageStatus}
                stageLogs={pipeline.stageLogs}
                activeStage={pipeline.activeStage}
                onCollapse={onTogglePipeline}
              />
            )}
            <div className="min-h-0 flex flex-col">
              <LineageBreadcrumb
                entries={pipeline.lineage}
                activeJobId={pipeline.activeJobId}
                onSelect={(id) => void pipeline.loadJob(id)}
              />
              <DesignNotes decisions={pipeline.designNotes} />
              <div className="flex-1 min-h-0">
                <ViewerTabs
                  data={pipeline.data}
                  schematic={pipeline.schematic}
                  gerber={pipeline.gerber}
                  bom={pipeline.bom}
                  firmware={pipeline.firmware}
                  jobId={pipeline.jobId}
                />
              </div>
              <RefinePanel
                parentJobId={pipeline.activeJobId}
                running={pipeline.running}
                recentInstructions={recentInstructions}
                onRefine={(inst) => void pipeline.refine(inst)}
              />
            </div>
          </>
        ) : (
          <WelcomePane
            description={description}
            image={image}
            running={pipeline.running}
            hasJobs={hasJobs}
            onDescriptionChange={onDescriptionChange}
            onImageChange={onImageChange}
            onSubmit={onSubmit}
          />
        )}
      </main>
    </div>
  );
};

// ── Root ────────────────────────────────────────────────────────────────
// Persist sidebar collapse state across reloads — once a user finds the
// layout they like, it should stick. localStorage keeps it client-only
// so each user can have their own preference without DB plumbing.
const COLLAPSE_STORAGE_KEY = "boardsmith.layout.v1";

interface CollapseState {
  jobs: boolean;
  pipeline: boolean;
}

function readCollapseState(): CollapseState {
  if (typeof window === "undefined") return { jobs: false, pipeline: false };
  try {
    const raw = window.localStorage.getItem(COLLAPSE_STORAGE_KEY);
    if (!raw) return { jobs: false, pipeline: false };
    const parsed = JSON.parse(raw) as Partial<CollapseState>;
    return {
      jobs: Boolean(parsed.jobs),
      pipeline: Boolean(parsed.pipeline),
    };
  } catch {
    return { jobs: false, pipeline: false };
  }
}

const AppInner = () => {
  const { session, loading } = useAuth();
  const [description, setDescription] = useState(DEMO_PROMPT);
  const [image, setImage] = useState<File | null>(null);
  const [hasJobs, setHasJobs] = useState(false);
  const [autoOpened, setAutoOpened] = useState(false);
  const [collapse, setCollapse] = useState<CollapseState>(readCollapseState);
  const pipeline = useRealPipeline();

  // Mirror collapse state to localStorage so the layout persists between
  // sessions / reloads.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(
        COLLAPSE_STORAGE_KEY,
        JSON.stringify(collapse),
      );
    } catch {
      // ignore quota / privacy mode errors
    }
  }, [collapse]);

  const toggleJobs = () =>
    setCollapse((prev) => ({ ...prev, jobs: !prev.jobs }));
  const togglePipeline = () =>
    setCollapse((prev) => ({ ...prev, pipeline: !prev.pipeline }));

  const submit = async () => {
    await pipeline.start(description, image);
    setImage(null);
  };

  const newProject = () => {
    pipeline.reset();
    setDescription(DEMO_PROMPT);
    setImage(null);
  };

  // Auto-open the most recent project on first sign-in so returning users
  // land where they left off. Subsequent jobs/refinements update via the
  // jobsBump signal but don't trigger another auto-open.
  useEffect(() => {
    if (!session || autoOpened) return;
    let cancelled = false;
    listJobs()
      .then((jobs) => {
        if (cancelled) return;
        setHasJobs(jobs.length > 0);
        if (jobs.length > 0 && !pipeline.activeJobId) {
          void pipeline.loadJob(jobs[0].job_id);
        }
        setAutoOpened(true);
      })
      .catch(() => {
        if (!cancelled) setAutoOpened(true);
      });
    return () => {
      cancelled = true;
    };
  }, [session, autoOpened, pipeline]);

  // Keep the empty-state copy fresh when jobs are added/removed.
  useEffect(() => {
    if (!session) return;
    listJobs()
      .then((jobs) => setHasJobs(jobs.length > 0))
      .catch(() => {});
  }, [session, pipeline.jobsBump]);

  if (loading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center font-mono text-[11px]"
        style={{ color: "var(--bs-fg-dim)" }}
      >
        Loading session…
      </div>
    );
  }

  if (!session) {
    return <AuthGate />;
  }

  return (
    <Dashboard
      description={description}
      image={image}
      hasJobs={hasJobs}
      pipeline={pipeline}
      jobsCollapsed={collapse.jobs}
      pipelineCollapsed={collapse.pipeline}
      onSubmit={submit}
      onDescriptionChange={setDescription}
      onImageChange={setImage}
      onNew={newProject}
      onToggleJobs={toggleJobs}
      onTogglePipeline={togglePipeline}
    />
  );
};

const App = () => (
  <AuthProvider>
    <Routes>
      {/* Public read-only share view — no auth gate so anyone with the
          link can see the design. The backend gates on is_public. */}
      <Route path="/p/:id" element={<PublicViewer />} />
      {/* Authenticated dashboard for everything else. */}
      <Route path="*" element={<AppInner />} />
    </Routes>
  </AuthProvider>
);

export default App;
