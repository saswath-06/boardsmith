// DesignNotes — surfaces the LLM's design rationale (MCU choice, power
// chain, off-board breakouts, etc.) as its own panel above the viewer
// tabs. Separate from warnings so design decisions don't get lost in
// a list of actual problems.
import { useState } from "react";

interface DesignNotesProps {
  decisions: string[];
}

const DesignNotes = ({ decisions }: DesignNotesProps) => {
  const [expanded, setExpanded] = useState(true);
  if (!decisions.length) return null;

  return (
    <div
      className="rounded mb-2 overflow-hidden"
      style={{
        background: "var(--bs-panel)",
        border: "1px solid var(--bs-line-soft)",
      }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
        style={{
          background: "var(--bs-panel-2)",
          borderBottom: expanded ? "1px solid var(--bs-line-soft)" : "none",
        }}
        title={expanded ? "Collapse design notes" : "Expand design notes"}
      >
        <svg
          width="11"
          height="11"
          viewBox="0 0 16 16"
          fill="none"
          style={{
            transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
            transition: "transform 120ms ease",
            color: "var(--bs-fg-dim)",
          }}
        >
          <path
            d="M5 3l6 5-6 5"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span
          className="bs-pill"
          style={{ color: "var(--bs-cyan)", borderColor: "var(--bs-cyan)" }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: "var(--bs-cyan)" }}
          />
          Design notes
        </span>
        <span
          className="font-mono text-[11px]"
          style={{ color: "var(--bs-fg-mute)" }}
        >
          {decisions.length} {decisions.length === 1 ? "decision" : "decisions"}
        </span>
        <span
          className="ml-auto font-mono text-[10px] uppercase tracking-widest"
          style={{ color: "var(--bs-fg-dim)" }}
        >
          {expanded ? "Hide" : "Show"}
        </span>
      </button>
      {expanded && (
        <ul className="px-4 py-2.5 space-y-1.5">
          {decisions.map((line, idx) => (
            <li
              key={idx}
              className="flex items-start gap-2.5 text-[12.5px] leading-snug"
              style={{ color: "var(--bs-fg)" }}
            >
              <span
                className="mt-1.5 h-1 w-1 rounded-full shrink-0"
                style={{ background: "var(--bs-copper)" }}
              />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default DesignNotes;
