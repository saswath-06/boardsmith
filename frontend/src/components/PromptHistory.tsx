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
  /** Returns the list of cascaded job_ids actually removed (parent + revisions). */
  onDelete: (jobId: string) => Promise<string[]>;
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
  deleting: boolean;
  onClick: () => void;
  onDeleteClick: () => void;
}

const JobRow = ({ job, active, isRevision, deleting, onClick, onDeleteClick }: RowProps) => {
  const status: "running" | "complete" | "error" = job.complete ? "complete" : "running";
  const dot =
    status === "running" ? "var(--bs-cyan)" :
    status === "complete" ? "var(--bs-lime)" : "var(--bs-red)";
  const title = isRevision && job.instruction ? job.instruction : job.description;

  return (
    <div
      className="group w-full relative"
      style={{ marginLeft: isRevision ? 12 : 0 }}
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
      <button
        onClick={onClick}
        className="w-full text-left px-3 py-2 rounded transition-colors"
        style={{
          background: active ? "var(--bs-panel-2)" : "transparent",
          borderLeft: active ? "2px solid var(--bs-copper)" : "2px solid transparent",
          opacity: deleting ? 0.45 : 1,
        }}
        disabled={deleting}
      >
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
          className="text-[12.5px] leading-snug truncate pr-6"
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
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDeleteClick();
        }}
        disabled={deleting}
        aria-label={`Delete ${isRevision ? "revision" : "project"}`}
        title={isRevision ? "Delete this revision" : "Delete project (and all revisions)"}
        className="absolute top-1.5 right-1.5 h-5 w-5 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
        style={{
          color: "var(--bs-fg-dim)",
          background: "var(--bs-bg-2)",
          border: "1px solid var(--bs-line-soft)",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = "var(--bs-red)";
          e.currentTarget.style.borderColor = "var(--bs-red)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = "var(--bs-fg-dim)";
          e.currentTarget.style.borderColor = "var(--bs-line-soft)";
        }}
      >
        <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden>
          <path d="M2.5 2.5l7 7M9.5 2.5l-7 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      </button>
    </div>
  );
};

const PromptHistory = ({ activeId, bump, onSelect, onNew, onDelete }: PromptHistoryProps) => {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());

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

  const handleDelete = async (job: JobSummary, isRoot: boolean) => {
    const label = isRoot
      ? "Delete this project and all its revisions?\n\nThis is permanent — Gerbers, BOM, and all generated artifacts will be removed."
      : "Delete this revision?\n\nThis is permanent — its generated artifacts will be removed.";
    if (!window.confirm(label)) return;

    // Mark this job (and any descendants we know about locally) as deleting
    // so the row dims and click is disabled while the request is in flight.
    setDeletingIds((prev) => {
      const next = new Set(prev);
      next.add(job.job_id);
      return next;
    });

    try {
      const deletedIds = await onDelete(job.job_id);
      // Optimistically drop deleted rows so the sidebar updates instantly
      // without waiting for the parent's bump-driven refetch to land.
      setJobs((prev) => prev.filter((j) => !deletedIds.includes(j.job_id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(job.job_id);
        return next;
      });
    }
  };

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
              deleting={deletingIds.has(root.job_id)}
              onClick={() => onSelect(root.job_id)}
              onDeleteClick={() => void handleDelete(root, true)}
            />
            {children.map((child) => (
              <JobRow
                key={child.job_id}
                job={child}
                active={child.job_id === activeId}
                isRevision
                deleting={deletingIds.has(child.job_id)}
                onClick={() => onSelect(child.job_id)}
                onDeleteClick={() => void handleDelete(child, false)}
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
