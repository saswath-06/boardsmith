// Prompt history sidebar — left pane in the IDE three-pane layout.
// TODO(api): replace HISTORY_SAMPLES with `GET /api/jobs` once the backend
// exposes a job-list endpoint. The shape below is the contract.

interface JobSample {
  id: string;
  title: string;
  time: string;
  status: "running" | "complete" | "error";
  components: number;
  nets: number;
}

const HISTORY_SAMPLES: JobSample[] = [
  { id: "j7", title: "ESP32 + DHT22 + LED + USB-C", time: "now",      status: "running",  components: 8, nets: 11 },
  { id: "j6", title: "Arduino Nano + MPU6050 IMU", time: "12m ago",   status: "complete", components: 6, nets: 9 },
  { id: "j5", title: "STM32F103 + BMP280 pressure", time: "1h ago",   status: "complete", components: 7, nets: 10 },
  { id: "j4", title: "ATtiny85 blinker · 3 LEDs",   time: "yesterday", status: "complete", components: 5, nets: 6 },
  { id: "j3", title: "USB-C breakout · 5V/3.3V",   time: "2d ago",    status: "complete", components: 4, nets: 5 },
  { id: "j2", title: "Servo driver · L293D + headers", time: "3d ago", status: "error",   components: 3, nets: 4 },
];

interface PromptHistoryProps {
  activeId?: string;
}

const PromptHistory = ({ activeId = "j7" }: PromptHistoryProps) => {
  return (
    <aside className="bs-panel flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--bs-line-soft)" }}>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em]" style={{ color: "var(--bs-fg-mute)" }}>
          Jobs
        </span>
        <button className="font-mono text-[10px] uppercase tracking-widest hover:text-[color:var(--bs-copper)]"
          style={{ color: "var(--bs-fg-dim)" }}>
          + New
        </button>
      </div>
      <div className="flex-1 overflow-y-auto bs-scroll px-2 py-2 space-y-0.5">
        {HISTORY_SAMPLES.map((job) => {
          const active = job.id === activeId;
          const dotColor =
            job.status === "running"  ? "var(--bs-cyan)" :
            job.status === "complete" ? "var(--bs-lime)" :
            job.status === "error"    ? "var(--bs-red)"  : "var(--bs-fg-dim)";
          return (
            <button key={job.id}
              className="w-full text-left px-3 py-2.5 rounded transition-colors"
              style={{
                background: active ? "var(--bs-panel-2)" : "transparent",
                borderLeft: active ? "2px solid var(--bs-copper)" : "2px solid transparent",
              }}>
              <div className="flex items-center gap-2 mb-1">
                <span className="h-1.5 w-1.5 rounded-full shrink-0"
                  style={{ background: dotColor, animation: job.status === "running" ? "bs-pulse 1.6s ease-in-out infinite" : "none" }} />
                <span className="font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>{job.id}</span>
                <span className="font-mono text-[10px] ml-auto" style={{ color: "var(--bs-fg-dim)" }}>{job.time}</span>
              </div>
              <div className="text-[13px] leading-snug truncate"
                style={{ color: active ? "var(--bs-fg)" : "var(--bs-fg-mute)" }}>
                {job.title}
              </div>
              <div className="flex gap-3 mt-1 font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
                <span>{job.components} comp</span>
                <span>{job.nets} nets</span>
              </div>
            </button>
          );
        })}
      </div>
      {/* Footer: usage indicator */}
      <div className="px-4 py-3 border-t font-mono text-[10px]"
        style={{ borderColor: "var(--bs-line-soft)", color: "var(--bs-fg-dim)" }}>
        <div className="flex justify-between">
          <span>API · gemini</span>
          <span style={{ color: "var(--bs-lime)" }}>42 / 100</span>
        </div>
        <div className="mt-1.5 h-0.5 rounded-full overflow-hidden" style={{ background: "var(--bs-line-soft)" }}>
          <div className="h-full" style={{ width: "42%", background: "var(--bs-lime)" }} />
        </div>
      </div>
    </aside>
  );
};

export default PromptHistory;
