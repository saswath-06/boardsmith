// Revision strip rendered above the viewer tabs when a job has refinements.
// Each chip is clickable; the active one is copper-bordered.
import type { LineageEntry } from "../types";

interface LineageBreadcrumbProps {
  entries: LineageEntry[];
  activeJobId: string | null;
  onSelect: (jobId: string) => void;
}

const LineageBreadcrumb = ({ entries, activeJobId, onSelect }: LineageBreadcrumbProps) => {
  if (entries.length < 2) return null;

  return (
    <div
      className="flex items-center gap-1.5 px-3 py-1.5 rounded mb-2 overflow-x-auto bs-scroll"
      style={{
        background: "var(--bs-bg-2)",
        border: "1px solid var(--bs-line-soft)",
      }}
    >
      <span
        className="font-mono text-[10px] uppercase tracking-[0.2em] shrink-0 mr-1"
        style={{ color: "var(--bs-fg-dim)" }}
      >
        revisions
      </span>
      {entries.map((entry, idx) => {
        const active = entry.job_id === activeJobId;
        const label = entry.revision === 0 ? "root" : `r${entry.revision}`;
        return (
          <div key={entry.job_id} className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => onSelect(entry.job_id)}
              className="px-2 py-0.5 rounded flex items-center gap-1.5 max-w-[260px]"
              style={{
                background: active ? "var(--bs-panel-2)" : "transparent",
                border: active
                  ? "1px solid var(--bs-copper)"
                  : "1px solid var(--bs-line)",
                color: active ? "var(--bs-fg)" : "var(--bs-fg-mute)",
              }}
              title={entry.title}
            >
              <span
                className="font-mono text-[10px] shrink-0"
                style={{ color: active ? "var(--bs-copper)" : "var(--bs-fg-dim)" }}
              >
                {label}
              </span>
              <span className="text-[11px] truncate">{entry.title}</span>
            </button>
            {idx < entries.length - 1 && (
              <span
                className="font-mono text-[10px]"
                style={{ color: "var(--bs-line)" }}
              >
                →
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default LineageBreadcrumb;
