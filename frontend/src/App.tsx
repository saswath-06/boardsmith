// Boardsmith — main app shell.
// Landing (idle) → Active dashboard with three-pane IDE layout.
import { useEffect, useRef, useState } from "react";
import AmbientPcb from "./components/AmbientPcb";
import LineageBreadcrumb from "./components/LineageBreadcrumb";
import BoardsmithLogo from "./components/Logo";
import PipelineProgress from "./components/PipelineProgress";
import PromptHistory from "./components/PromptHistory";
import RefinePanel from "./components/RefinePanel";
import ViewerTabs from "./components/Viewers";
import { createJob, getJob, getLineage, refineJob, subscribeToJob } from "./api";
import type {
  Board3DData,
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
  onSubmit: () => void;
  onDescriptionChange: (value: string) => void;
  onReset: () => void;
}

const TopBar = ({ description, running, jobId, onSubmit, onDescriptionChange, onReset }: TopBarProps) => {
  const breadcrumb = jobId ? jobId.slice(0, 8) : "—";
  return (
    <header className="flex items-center gap-4 px-4 h-12 border-b shrink-0"
      style={{ borderColor: "var(--bs-line-soft)", background: "var(--bs-bg-2)" }}>
      <button onClick={onReset} className="flex items-center gap-2.5 shrink-0">
        <BoardsmithLogo size={26} />
        <span className="text-[15px] font-semibold tracking-tight" style={{ color: "var(--bs-fg)" }}>
          Boardsmith
        </span>
        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider"
          style={{ color: "var(--bs-copper)", border: "1px solid var(--bs-copper)" }}>
          v0.1
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
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bs-pulse"
            style={{ background: running ? "var(--bs-cyan)" : "var(--bs-lime)" }}/>
          {running ? "Running" : "Ready"}
        </span>
        <span style={{ color: "var(--bs-line)" }}>·</span>
        <span>backend · 127.0.0.1:8000</span>
      </div>
    </header>
  );
};

// ── Landing / idle ───────────────────────────────────────────────────────
interface LandingProps {
  description: string;
  running: boolean;
  onDescriptionChange: (value: string) => void;
  onSubmit: () => void;
  ambient?: boolean;
}

const Landing = ({ description, running, onDescriptionChange, onSubmit, ambient = true }: LandingProps) => {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center px-6 py-16 overflow-hidden bs-bg-grid">
      {ambient && <AmbientPcb />}

      <div className="relative z-10 w-full max-w-2xl flex flex-col items-center text-center">
        <div className="flex items-center gap-3 mb-8">
          <BoardsmithLogo size={48} />
          <div className="flex flex-col items-start">
            <span className="text-[26px] font-semibold tracking-tight leading-none" style={{ color: "var(--bs-fg)" }}>
              Boardsmith
            </span>
            <span className="font-mono text-[10px] mt-1 uppercase tracking-[0.2em]" style={{ color: "var(--bs-copper)" }}>
              PCB · forged in plain English
            </span>
          </div>
        </div>

        <div className="mb-6 inline-flex items-center gap-2 px-3 py-1 rounded-full font-mono text-[11px]"
          style={{ border: "1px solid var(--bs-line)", background: "var(--bs-bg-2)", color: "var(--bs-fg-mute)" }}>
          <span className="h-1.5 w-1.5 rounded-full bs-pulse" style={{ background: "var(--bs-cyan)" }}/>
          <span style={{ color: "var(--bs-cyan)" }}>READY</span>
          <span style={{ color: "var(--bs-line)" }}>·</span>
          <span>natural language → manufacturable PCB</span>
        </div>

        <h1 className="mb-4 max-w-xl text-[42px] leading-[1.05] font-semibold tracking-tight"
          style={{ color: "var(--bs-fg)" }}>
          Describe a circuit.<br/>
          <span style={{ color: "var(--bs-copper)" }}>Get a board you can fab.</span>
        </h1>

        <p className="mb-10 max-w-lg text-[15px] leading-relaxed" style={{ color: "var(--bs-fg-mute)" }}>
          Boardsmith turns plain English into the full pipeline — schematic, layout, 3D
          render, and Gerbers — live in your browser. Refine with follow-ups, then upload to JLCPCB.
        </p>

        <div className="w-full bs-brackets bs-panel p-3" style={{ background: "var(--bs-panel)" }}>
          <div className="flex items-center gap-2 px-1 pb-2 font-mono text-[10px] uppercase tracking-widest"
            style={{ color: "var(--bs-fg-dim)" }}>
            <span style={{ color: "var(--bs-copper)" }}>▍</span>
            <span>describe.your.circuit</span>
            <span className="ml-auto">{description.trim().length} chars</span>
          </div>
          <textarea
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            placeholder="An ESP32 connected to a DHT22 temperature sensor, USB-C power input…"
            className="w-full min-h-[110px] resize-none p-3 outline-none rounded text-[14px] leading-[1.55] font-mono"
            style={{
              background: "var(--bs-bg)",
              border: "1px solid var(--bs-line-soft)",
              color: "var(--bs-fg)",
            }}
          />
          <div className="mt-3 flex items-center gap-3">
            <div className="flex items-center gap-2 font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
              <span style={{ color: "var(--bs-lime)" }}>●</span> gemini-2.5-pro
              <span style={{ color: "var(--bs-line)" }}>·</span>
              <span>~10s avg</span>
            </div>
            <button
              onClick={onSubmit}
              disabled={running || description.trim().length < 3}
              className="bs-btn-primary ml-auto px-5 py-2.5 rounded flex items-center gap-2 text-[13px]">
              {running ? <><span className="bs-spin"/>Building PCB…</> : <>Generate PCB →</>}
            </button>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--bs-fg-dim)" }}>Try:</span>
          {SAMPLE_PROMPTS.map((p) => (
            <button key={p}
              onClick={() => onDescriptionChange(p)}
              className="px-3 py-1 rounded-full text-[12px] transition-colors"
              style={{ border: "1px solid var(--bs-line)", color: "var(--bs-fg-mute)", background: "var(--bs-bg-2)" }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--bs-copper)"; e.currentTarget.style.color = "var(--bs-copper-2)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--bs-line)"; e.currentTarget.style.color = "var(--bs-fg-mute)"; }}>
              {p}
            </button>
          ))}
        </div>

        <div className="mt-12 grid grid-cols-3 gap-6 max-w-xl">
          {[
            ["01", "Schematic", "schemdraw + skidl"],
            ["02", "PCB layout", "force-directed + lee"],
            ["03", "Gerber",    "RS-274X · JLCPCB-ready"],
          ].map(([n, t, s]) => (
            <div key={n} className="text-left">
              <div className="font-mono text-[10px] mb-1" style={{ color: "var(--bs-copper)" }}>STAGE {n}</div>
              <div className="text-[13px] font-medium" style={{ color: "var(--bs-fg)" }}>{t}</div>
              <div className="font-mono text-[10px] mt-0.5" style={{ color: "var(--bs-fg-dim)" }}>{s}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="absolute bottom-4 left-0 right-0 flex justify-between px-6 font-mono text-[10px] uppercase tracking-widest z-10"
        style={{ color: "var(--bs-fg-dim)" }}>
        <span>boardsmith · 2026</span>
        <span>natural language → fr4 · in seconds</span>
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
  lineage: LineageEntry[];
  jobsBump: number;
  start: (description: string) => Promise<void>;
  refine: (instruction: string) => Promise<void>;
  loadJob: (jobId: string) => Promise<void>;
  reset: () => void;
}

// Pure function: rebuild viewer state from a snapshot's stored events.
function projectSnapshot(snapshot: JobSnapshot): {
  stageStatus: Record<string, StageRowStatus>;
  stageLogs: Record<string, LogEntry[]>;
  data: Board3DData | null;
  schematic: SchematicData | null;
  gerber: GerberData | null;
} {
  const stageStatus: Record<string, StageRowStatus> = {};
  const stageLogs: Record<string, LogEntry[]> = {};
  let data: Board3DData | null = null;
  let schematic: SchematicData | null = null;
  let gerber: GerberData | null = null;

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
      if (stage === "schematic" && payload && typeof payload === "object" && "svg" in payload) {
        schematic = payload as unknown as SchematicData;
      }
      if (stage === "3d" && payload && typeof payload === "object" && "components" in payload) {
        data = payload as unknown as Board3DData;
      }
      if (stage === "gerber" && payload && typeof payload === "object" && "download_url" in payload) {
        gerber = payload as unknown as GerberData;
      }
      continue;
    }
    if (event.status === "error") {
      (stageLogs[stage] ??= []).push({ level: "warn", msg: event.message });
    }
  }

  return { stageStatus, stageLogs, data, schematic, gerber };
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
      if (stage === "schematic" && payload && typeof payload === "object" && "svg" in payload) {
        setSchematic(payload as unknown as SchematicData);
      }
      if (stage === "3d" && payload && typeof payload === "object" && "components" in payload) {
        setData(payload as unknown as Board3DData);
      }
      if (stage === "gerber" && payload && typeof payload === "object" && "download_url" in payload) {
        setGerber(payload as unknown as GerberData);
      }
      return;
    }

    if (event.status === "error") {
      appendLog(stage, { level: "warn", msg: event.message });
    }
  };

  const stream = (newJobId: string) => {
    closeSource();
    streamingJobRef.current = newJobId;
    setJobId(newJobId);
    setActiveJobId(newJobId);
    clearViewerState();
    setRunning(true);
    setJobsBump((n) => n + 1);
    void refreshLineage(newJobId);
    const source = subscribeToJob(newJobId, handleEvent, () => {
      closeSource();
      setRunning(false);
    });
    sourceRef.current = source;
  };

  const start = async (description: string) => {
    try {
      const { job_id } = await createJob(description);
      stream(job_id);
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
      stream(job_id);
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
      void refreshLineage(id);
      // If this snapshot is still in progress, hop on its event stream.
      if (!snapshot.complete) {
        streamingJobRef.current = id;
        setRunning(true);
        const source = subscribeToJob(id, handleEvent, () => {
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
    lineage,
    jobsBump,
    start,
    refine,
    loadJob,
    reset,
  };
}

// ── Active dashboard: three-pane IDE layout ──────────────────────────────
interface ActiveDashboardProps {
  description: string;
  pipeline: PipelineState;
  onSubmit: () => void;
  onDescriptionChange: (value: string) => void;
  onReset: () => void;
}

const ActiveDashboard = ({
  description,
  pipeline,
  onSubmit,
  onDescriptionChange,
  onReset,
}: ActiveDashboardProps) => {
  const recentInstructions = pipeline.lineage
    .filter((entry) => entry.revision > 0)
    .map((entry) => entry.title);

  return (
    <div className="h-screen flex flex-col">
      <TopBar
        description={description}
        running={pipeline.running}
        jobId={pipeline.jobId}
        onSubmit={onSubmit}
        onDescriptionChange={onDescriptionChange}
        onReset={onReset}
      />
      <main className="flex-1 grid gap-2 p-2 min-h-0"
        style={{ gridTemplateColumns: "240px 320px 1fr" }}>
        <PromptHistory
          activeId={pipeline.activeJobId}
          bump={pipeline.jobsBump}
          onSelect={(id) => void pipeline.loadJob(id)}
          onNew={onReset}
        />
        <PipelineProgress
          stageStatus={pipeline.stageStatus}
          stageLogs={pipeline.stageLogs}
          activeStage={pipeline.activeStage}
        />
        <div className="min-h-0 flex flex-col">
          <LineageBreadcrumb
            entries={pipeline.lineage}
            activeJobId={pipeline.activeJobId}
            onSelect={(id) => void pipeline.loadJob(id)}
          />
          <div className="flex-1 min-h-0">
            <ViewerTabs
              data={pipeline.data}
              schematic={pipeline.schematic}
              gerber={pipeline.gerber}
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
      </main>
    </div>
  );
};

// ── Root ────────────────────────────────────────────────────────────────
const App = () => {
  const [description, setDescription] = useState(DEMO_PROMPT);
  const [mode, setMode] = useState<"idle" | "active">("idle");
  const pipeline = useRealPipeline();

  const submit = async () => {
    setMode("active");
    await pipeline.start(description);
  };

  const reset = () => {
    setMode("idle");
    pipeline.reset();
  };

  return (
    <div className="min-h-screen" data-screen-label={mode === "idle" ? "Landing" : "Active dashboard"}>
      {mode === "idle" ? (
        <Landing
          description={description}
          running={pipeline.running}
          onDescriptionChange={setDescription}
          onSubmit={submit}
          ambient
        />
      ) : (
        <ActiveDashboard
          description={description}
          pipeline={pipeline}
          onSubmit={submit}
          onDescriptionChange={setDescription}
          onReset={reset}
        />
      )}
    </div>
  );
};

export default App;
