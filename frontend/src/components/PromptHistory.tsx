// Prompt history sidebar — left pane in the IDE three-pane layout.
// Backed by GET /api/jobs. Roots render at the top level; revisions nest
// under their parent with a left rail accent.
import { useEffect, useState } from "react";
import { listJobs } from "../api";
import type { JobSummary } from "../types";

interface PromptHistoryProps {
  activeId: string | null;
  bump: number;
  onSelect: (jobId: string) => void;
  onNew: () => void;
}

interface Thread {
  root: JobSummary;
  children: JobSummary[];
}

function buildThreads(jobs: JobSummary[]): Thread[] {
  const byId = new Map(jobs.map((j) => [j.job_id, j]));
  const threads = new Map<string, Thread>();

  // First pass: every job gets a thread under its root.
  for (const job of jobs) {
    let cursor: JobSummary | undefined = job;
    let rootId = cursor.job_id;
    while (cursor && cursor.parent_job_id) {
      const parent = byId.get(cursor.parent_job_id);
      if (!parent) break;
      cursor = parent;
      rootId = cursor.job_id;
    }
    const rootJob = byId.get(rootId) ?? job;
    if (!threads.has(rootId)) {
      threads.set(rootId, { root: rootJob, children: [] });
    }
    if (job.job_id !== rootId) {
      threads.get(rootId)!.children.push(job);
    }
  }

  for (const t of threads.values()) {
    t.children.sort((a, b) => a.revision - b.revision);
  }

  // Roots: newest first by created_at.
  return Array.from(threads.values()).sort(
    (a, b) => b.root.created_at - a.root.created_at,
  );
}

function relTime(ts: number): string {
  if (!ts) return "—";
  const delta = Date.now() / 1000 - ts;
  if (delta < 60) return "now";
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

interface RowProps {
  job: JobSummary;
  active: boolean;
  isRevision: boolean;
  onClick: () => void;
}

const JobRow = ({ job, active, isRevision, onClick }: RowProps) => {
  const status: "running" | "complete" | "error" = job.complete ? "complete" : "running";
  const dot =
    status === "running" ? "var(--bs-cyan)" :
    status === "complete" ? "var(--bs-lime)" : "var(--bs-red)";
  const title = isRevision && job.instruction ? job.instruction : job.description;

  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-2 rounded transition-colors"
      style={{
        background: active ? "var(--bs-panel-2)" : "transparent",
        borderLeft: active ? "2px solid var(--bs-copper)" : "2px solid transparent",
        marginLeft: isRevision ? 12 : 0,
        position: "relative",
      }}
    >
      {isRevision && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: 0,
            top: -4,
            bottom: -4,
            width: 1,
            background: "var(--bs-copper)",
            opacity: 0.45,
          }}
        />
      )}
      <div className="flex items-center gap-2 mb-0.5">
        <span
          className="h-1.5 w-1.5 rounded-full shrink-0"
          style={{
            background: dot,
            animation: status === "running" ? "bs-pulse 1.6s ease-in-out infinite" : "none",
          }}
        />
        <span className="font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
          {isRevision ? `r${job.revision}` : job.job_id.slice(0, 6)}
        </span>
        <span
          className="font-mono text-[10px] ml-auto"
          style={{ color: "var(--bs-fg-dim)" }}
        >
          {relTime(job.created_at)}
        </span>
      </div>
      <div
        className="text-[12.5px] leading-snug truncate"
        style={{ color: active ? "var(--bs-fg)" : "var(--bs-fg-mute)" }}
        title={title}
      >
        {title || "(empty)"}
      </div>
      {!isRevision && (job.components > 0 || job.nets > 0) && (
        <div className="flex gap-3 mt-0.5 font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
          <span>{job.components} comp</span>
          <span>{job.nets} nets</span>
        </div>
      )}
    </button>
  );
};

const PromptHistory = ({ activeId, bump, onSelect, onNew }: PromptHistoryProps) => {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listJobs()
      .then((rows) => {
        if (!cancelled) {
          setJobs(rows);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [bump]);

  const threads = buildThreads(jobs);

  return (
    <aside className="bs-panel flex flex-col h-full">
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ borderColor: "var(--bs-line-soft)" }}
      >
        <span
          className="font-mono text-[10px] uppercase tracking-[0.18em]"
          style={{ color: "var(--bs-fg-mute)" }}
        >
          Jobs
        </span>
        <button
          onClick={onNew}
          className="font-mono text-[10px] uppercase tracking-widest hover:text-[color:var(--bs-copper)]"
          style={{ color: "var(--bs-fg-dim)" }}
        >
          + New
        </button>
      </div>
      <div className="flex-1 overflow-y-auto bs-scroll px-2 py-2 space-y-2">
        {error && (
          <div
            className="px-3 py-2 font-mono text-[10px] rounded"
            style={{
              color: "var(--bs-red)",
              border: "1px solid var(--bs-red)",
              background: "var(--bs-bg-2)",
            }}
          >
            {error}
          </div>
        )}
        {!error && threads.length === 0 && (
          <div
            className="px-3 py-6 text-center font-mono text-[10px]"
            style={{ color: "var(--bs-fg-dim)" }}
          >
            no jobs yet — generate one to get started
          </div>
        )}
        {threads.map(({ root, children }) => (
          <div key={root.job_id} className="space-y-0.5">
            <JobRow
              job={root}
              active={root.job_id === activeId}
              isRevision={false}
              onClick={() => onSelect(root.job_id)}
            />
            {children.map((child) => (
              <JobRow
                key={child.job_id}
                job={child}
                active={child.job_id === activeId}
                isRevision
                onClick={() => onSelect(child.job_id)}
              />
            ))}
          </div>
        ))}
      </div>
      <div
        className="px-4 py-3 border-t font-mono text-[10px]"
        style={{ borderColor: "var(--bs-line-soft)", color: "var(--bs-fg-dim)" }}
      >
        <div className="flex justify-between">
          <span>API · gemini</span>
          <span style={{ color: "var(--bs-lime)" }}>
            {jobs.length} job{jobs.length === 1 ? "" : "s"}
          </span>
        </div>
      </div>
    </aside>
  );
};

export default PromptHistory;
