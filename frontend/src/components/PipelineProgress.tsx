// Vertical timeline with streaming logs under each step.
import type { LogEntry, StageStatus } from "../types";

type StageRowStatus = StageStatus | "waiting";

const STAGES: Array<[string, string, string]> = [
  ["parse",      "Parse intent",     "gemini-2.0-flash"],
  ["schematic",  "Schematic",        "schemdraw + skidl"],
  ["pcb_layout", "PCB layout",       "force-directed placement"],
  ["routing",    "Auto-route",       "lee · grid 0.25mm"],
  ["3d",         "3D visualization", "three.js"],
  ["gerber",     "Gerber export",    "RS-274X"],
];

interface StepIconProps {
  status: StageRowStatus;
}

const StepIcon = ({ status }: StepIconProps) => {
  const base = "flex h-4 w-4 shrink-0 items-center justify-center rounded-full";
  if (status === "running") {
    return (
      <span className={`${base} relative`} style={{ background: "var(--bs-cyan)" }}>
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-50"
          style={{ background: "var(--bs-cyan)" }} />
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--bs-bg)" }} />
      </span>
    );
  }
  if (status === "complete") {
    return (
      <span className={base} style={{ background: "var(--bs-lime)", color: "var(--bs-bg)" }}>
        <svg width="9" height="9" viewBox="0 0 8 8" fill="none">
          <path d="M1 4l2 2 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className={base} style={{ background: "var(--bs-red)" }}>
        <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
          <path d="M2 2l4 4M6 2L2 6" stroke="var(--bs-bg)" strokeWidth="1.6" strokeLinecap="round"/>
        </svg>
      </span>
    );
  }
  return <span className={`${base} border`} style={{ borderColor: "var(--bs-line)", background: "var(--bs-bg-2)" }} />;
};

interface LogLineProps {
  entry: LogEntry;
}

const LogLine = ({ entry }: LogLineProps) => {
  const color =
    entry.level === "ok"   ? "var(--bs-lime)" :
    entry.level === "warn" ? "var(--bs-amber)" :
    entry.level === "err"  ? "var(--bs-red)"  :
                             "var(--bs-fg-dim)";
  const tag =
    entry.level === "ok"   ? "ok " :
    entry.level === "warn" ? "warn" :
    entry.level === "err"  ? "err " :
                             "    ";
  return (
    <div className="font-mono text-[11px] leading-[1.55] flex gap-2 bs-fade-up">
      <span style={{ color: "var(--bs-fg-dim)" }}>·</span>
      <span style={{ color }} className="shrink-0 select-none">{tag}</span>
      <span className="truncate" style={{ color: "var(--bs-fg-mute)" }}>{entry.msg}</span>
    </div>
  );
};

interface PipelineStepProps {
  stage: string;
  label: string;
  sub: string;
  status: StageRowStatus;
  logs: LogEntry[];
  isLast: boolean;
  isActive: boolean;
}

const PipelineStep = ({ stage, label, sub, status, logs, isLast, isActive }: PipelineStepProps) => {
  const colorByStatus: Record<StageRowStatus, string> = {
    waiting:  "var(--bs-fg-dim)",
    running:  "var(--bs-cyan)",
    complete: "var(--bs-lime)",
    error:    "var(--bs-red)",
  };
  return (
    <li className={`relative flex gap-3 ${isLast ? "" : "pb-4"}`}>
      {!isLast && (
        <span className="absolute left-[7px] top-4 w-px"
          style={{ height: "calc(100% - 8px)", background: "var(--bs-line)" }} />
      )}
      <div className="relative z-10 pt-0.5"><StepIcon status={status} /></div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
              {String(STAGES.findIndex(s => s[0] === stage) + 1).padStart(2, "0")}
            </span>
            <span className="text-sm font-medium tracking-tight" style={{ color: status === "waiting" ? "var(--bs-fg-dim)" : "var(--bs-fg)" }}>
              {label}
            </span>
          </div>
          {status !== "waiting" && (
            <span className="font-mono text-[10px] uppercase tracking-widest shrink-0"
              style={{ color: colorByStatus[status] }}>
              {status}
            </span>
          )}
        </div>
        <div className="font-mono text-[10px] mt-0.5" style={{ color: "var(--bs-fg-dim)" }}>{sub}</div>

        {/* Streaming logs */}
        {(isActive || status === "complete" || status === "running") && logs?.length > 0 && (
          <div className="mt-2 space-y-0.5 border-l pl-3"
            style={{ borderColor: "var(--bs-line-soft)" }}>
            {logs.map((entry, i) => <LogLine key={i} entry={entry} />)}
            {status === "running" && (
              <div className="font-mono text-[11px]" style={{ color: "var(--bs-cyan)" }}>
                <span className="bs-cursor">·</span>
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  );
};

interface PipelineProgressProps {
  stageStatus: Record<string, StageRowStatus>;
  stageLogs: Record<string, LogEntry[]>;
  activeStage: string | null;
}

const PipelineProgress = ({ stageStatus, stageLogs, activeStage }: PipelineProgressProps) => {
  return (
    <aside className="bs-panel flex flex-col h-full">
      {/* header */}
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--bs-line-soft)" }}>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em]" style={{ color: "var(--bs-fg-mute)" }}>
            Pipeline
          </span>
        </div>
        <span className="bs-pill" style={{ color: "var(--bs-cyan)" }}>
          <span className="h-1.5 w-1.5 rounded-full bs-pulse" style={{ background: "var(--bs-cyan)" }} />
          SSE
        </span>
      </div>
      {/* steps */}
      <ol className="flex-1 px-4 py-4 overflow-y-auto bs-scroll">
        {STAGES.map(([stage, label, sub], i) => (
          <PipelineStep
            key={stage}
            stage={stage}
            label={label}
            sub={sub}
            status={stageStatus[stage] ?? "waiting"}
            logs={stageLogs[stage] ?? []}
            isLast={i === STAGES.length - 1}
            isActive={stage === activeStage}
          />
        ))}
      </ol>
    </aside>
  );
};

export default PipelineProgress;
export { STAGES as PIPELINE_STAGES };
