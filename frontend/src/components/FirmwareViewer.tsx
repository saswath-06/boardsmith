// Renders the auto-generated Arduino .ino sketch with line numbers + Copy.
import { useMemo, useState } from "react";
import type { FirmwareData } from "../types";

interface FirmwareViewerProps {
  firmware: FirmwareData | null;
}

const FirmwareViewer = ({ firmware }: FirmwareViewerProps) => {
  const [copied, setCopied] = useState(false);

  const lines = useMemo(() => {
    if (!firmware?.code) return [] as string[];
    return firmware.code.replace(/\r\n/g, "\n").split("\n");
  }, [firmware?.code]);

  if (!firmware) {
    return <div className="bs-skeleton h-full w-full" />;
  }

  // Stage explicitly skipped: the design didn't have an MCU, so a sketch
  // would just be cosmetic. Show a friendly "nothing to flash here" panel
  // instead of an empty editor.
  if (firmware.code === null) {
    return (
      <div
        className="h-full w-full flex flex-col items-center justify-center gap-2 px-6 text-center"
        style={{ background: "var(--bs-bg)" }}
      >
        <div
          className="font-mono text-[10px] uppercase tracking-widest"
          style={{ color: "var(--bs-fg-dim)" }}
        >
          No firmware needed
        </div>
        <div className="text-[14px]" style={{ color: "var(--bs-fg)" }}>
          {firmware.reason ??
            "This design has no MCU, so the firmware stage was skipped."}
        </div>
        <div
          className="font-mono text-[11px] mt-2"
          style={{ color: "var(--bs-fg-mute)" }}
        >
          Add an ESP32, Arduino Nano, or STM32 to the design and re-run the
          pipeline to get a starter sketch here.
        </div>
      </div>
    );
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(firmware.code ?? "");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      // clipboard API can be blocked in some contexts; just fail silently
      // — the download bar still gives the user the file.
    }
  };

  const lineCount = lines.length;

  return (
    <div
      className="h-full w-full flex flex-col"
      style={{ background: "var(--bs-bg)" }}
    >
      {/* meta strip — target board / framework / copy */}
      <div
        className="sticky top-0 z-10 flex items-center gap-3 px-4 py-2 border-b flex-wrap"
        style={{
          background: "var(--bs-panel-2)",
          borderColor: "var(--bs-line-soft)",
        }}
      >
        <span className="bs-pill" style={{ color: "var(--bs-cyan)" }}>
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: "var(--bs-cyan)" }}
          />
          {firmware.filename ?? "main.ino"}
        </span>
        {firmware.target_board && (
          <div className="flex items-baseline gap-2 font-mono text-[11px]">
            <span style={{ color: "var(--bs-fg-dim)" }}>BOARD</span>
            <span style={{ color: "var(--bs-fg)" }}>{firmware.target_board}</span>
          </div>
        )}
        {firmware.framework && (
          <>
            <span style={{ color: "var(--bs-line)" }}>·</span>
            <div className="flex items-baseline gap-2 font-mono text-[11px]">
              <span style={{ color: "var(--bs-fg-dim)" }}>FRAMEWORK</span>
              <span style={{ color: "var(--bs-fg)" }}>{firmware.framework}</span>
            </div>
          </>
        )}
        <span style={{ color: "var(--bs-line)" }}>·</span>
        <div className="flex items-baseline gap-2 font-mono text-[11px]">
          <span style={{ color: "var(--bs-fg-dim)" }}>LINES</span>
          <span style={{ color: "var(--bs-fg)" }}>{lineCount}</span>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="ml-auto bs-btn-ghost px-3 py-1.5 rounded text-[12px] flex items-center gap-2"
          title="Copy the full sketch to your clipboard"
        >
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
            <rect
              x="4.5"
              y="4.5"
              width="8"
              height="9"
              rx="1"
              stroke="currentColor"
              strokeWidth="1.4"
            />
            <path
              d="M2.5 11V3.5A1 1 0 013.5 2.5H10"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>

      {firmware.summary && (
        <div
          className="px-4 py-1.5 font-mono text-[10.5px] border-b"
          style={{
            color: "var(--bs-fg-dim)",
            background: "var(--bs-bg-2)",
            borderColor: "var(--bs-line-soft)",
          }}
        >
          {firmware.summary}
        </div>
      )}

      {/* code body — gutter + monospace pre */}
      <div className="flex-1 min-h-0 overflow-auto bs-scroll">
        <div className="flex font-mono text-[12px] leading-[1.55]">
          <pre
            aria-hidden
            className="select-none px-3 py-3 text-right tabular-nums shrink-0"
            style={{
              color: "var(--bs-fg-dim)",
              background: "var(--bs-bg-2)",
              borderRight: "1px solid var(--bs-line-soft)",
              minWidth: "3.5rem",
              fontFamily:
                "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
            }}
          >
            {lines.map((_, i) => `${i + 1}\n`).join("")}
          </pre>
          <pre
            className="px-4 py-3 whitespace-pre"
            style={{
              color: "var(--bs-fg)",
              fontFamily:
                "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
            }}
          >
            {firmware.code}
          </pre>
        </div>
      </div>
    </div>
  );
};

export default FirmwareViewer;
