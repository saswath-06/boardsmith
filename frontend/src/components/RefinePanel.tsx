// Refine panel — chat-style follow-up input that lives below the viewer when
// a job is complete. Submitting kicks off `POST /api/jobs/{id}/refine` which
// creates a child job; the parent `useRealPipeline` then streams the new run.
import { useState } from "react";

interface RefinePanelProps {
  parentJobId: string | null;
  running: boolean;
  recentInstructions: string[];
  onRefine: (instruction: string) => void;
}

const RefinePanel = ({ parentJobId, running, recentInstructions, onRefine }: RefinePanelProps) => {
  const [value, setValue] = useState("");
  const disabled = running || !parentJobId || value.trim().length < 3;

  const submit = () => {
    if (disabled) return;
    onRefine(value.trim());
    setValue("");
  };

  return (
    <div
      className="bs-panel mt-2 px-3 py-2"
      style={{ background: "var(--bs-panel)" }}
    >
      <div className="flex items-center gap-2">
        <span
          className="font-mono text-[10px] uppercase tracking-[0.2em] shrink-0"
          style={{ color: "var(--bs-copper)" }}
        >
          refine
        </span>
        <span
          className="font-mono text-[10px] shrink-0"
          style={{ color: "var(--bs-fg-dim)" }}
        >
          chat with the board
        </span>
        <div
          className="flex-1 flex items-center gap-2 px-3 h-8 rounded ml-2"
          style={{
            background: "var(--bs-bg)",
            border: "1px solid var(--bs-line)",
            opacity: parentJobId && !running ? 1 : 0.55,
          }}
        >
          <span
            className="font-mono text-[11px] shrink-0"
            style={{ color: "var(--bs-copper)" }}
          >
            $
          </span>
          <input
            type="text"
            value={value}
            disabled={!parentJobId || running}
            onChange={(e) => setValue(e.target.value)}
            placeholder={
              running
                ? "refinement running…"
                : parentJobId
                  ? "add a buzzer driven by GPIO5…"
                  : "generate a board first"
            }
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            className="flex-1 bg-transparent outline-none text-[13px] font-mono"
            style={{ color: "var(--bs-fg)" }}
          />
        </div>
        <button
          onClick={submit}
          disabled={disabled}
          className="bs-btn-primary px-4 h-8 rounded text-[13px] flex items-center gap-2 shrink-0"
        >
          {running ? (
            <>
              <span className="bs-spin" />
              Refining…
            </>
          ) : (
            "Send"
          )}
        </button>
      </div>

      {recentInstructions.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span
            className="font-mono text-[10px] uppercase tracking-widest shrink-0"
            style={{ color: "var(--bs-fg-dim)" }}
          >
            recent
          </span>
          {recentInstructions.slice(0, 3).map((inst, i) => (
            <button
              key={`${i}-${inst}`}
              onClick={() => setValue(inst)}
              className="px-2 py-0.5 rounded font-mono text-[10px] truncate max-w-[220px]"
              style={{
                border: "1px solid var(--bs-line)",
                color: "var(--bs-fg-mute)",
                background: "var(--bs-bg-2)",
              }}
              title={inst}
            >
              {inst}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default RefinePanel;
