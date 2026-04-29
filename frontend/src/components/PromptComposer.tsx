// PromptComposer — the rich textarea + image attach surface used by the
// welcome pane and top bar. Handles file picker, drag-and-drop, and
// paste-from-clipboard for sketches/breadboard photos that get sent to
// Gemini Vision alongside (optional) text.
import { useEffect, useRef, useState } from "react";

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const MAX_BYTES = 10 * 1024 * 1024;

interface PromptComposerProps {
  description: string;
  image: File | null;
  running: boolean;
  onDescriptionChange: (value: string) => void;
  onImageChange: (file: File | null) => void;
  onSubmit: () => void;
}

const PromptComposer = ({
  description,
  image,
  running,
  onDescriptionChange,
  onImageChange,
  onSubmit,
}: PromptComposerProps) => {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Build a preview URL whenever an image is attached. Revoke it on
  // change/unmount so the browser doesn't leak blobs.
  useEffect(() => {
    if (!image) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(image);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  const validate = (file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return `Unsupported image type: ${file.type || "unknown"}. Use PNG, JPEG, WebP, or GIF.`;
    }
    if (file.size > MAX_BYTES) {
      return `Image too large (${(file.size / (1024 * 1024)).toFixed(1)} MB > 10 MB).`;
    }
    return null;
  };

  const acceptFile = (file: File) => {
    const issue = validate(file);
    if (issue) {
      setError(issue);
      return;
    }
    setError(null);
    onImageChange(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) acceptFile(file);
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items ?? [];
    for (const item of items) {
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) {
          e.preventDefault();
          acceptFile(file);
          return;
        }
      }
    }
  };

  const canSubmit =
    !running && (description.trim().length >= 3 || image !== null);
  const charCount = description.trim().length;

  return (
    <div className="w-full bs-brackets bs-panel p-3" style={{ background: "var(--bs-bg)" }}>
      <div
        className="flex items-center gap-2 px-1 pb-2 font-mono text-[10px] uppercase tracking-widest"
        style={{ color: "var(--bs-fg-dim)" }}
      >
        <span style={{ color: "var(--bs-copper)" }}>▍</span>
        <span>{image ? "describe.or.attach" : "describe.your.circuit"}</span>
        <span className="ml-auto">
          {image ? `image attached · ${charCount} chars` : `${charCount} chars`}
        </span>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className="relative rounded"
        style={{
          border: dragOver
            ? "1px dashed var(--bs-copper)"
            : "1px solid var(--bs-line-soft)",
          background: dragOver ? "var(--bs-panel-2)" : "var(--bs-bg-2)",
          transition: "border-color 120ms ease, background-color 120ms ease",
        }}
      >
        {previewUrl && (
          <div
            className="flex items-center gap-3 px-3 pt-3"
          >
            <img
              src={previewUrl}
              alt="attached sketch"
              className="rounded object-cover"
              style={{
                width: 64,
                height: 64,
                border: "1px solid var(--bs-line)",
                background: "var(--bs-bg)",
              }}
            />
            <div className="flex-1 min-w-0">
              <div
                className="text-[12px] truncate"
                style={{ color: "var(--bs-fg)" }}
              >
                {image?.name ?? "image"}
              </div>
              <div
                className="font-mono text-[10px]"
                style={{ color: "var(--bs-fg-dim)" }}
              >
                {image
                  ? `${(image.size / 1024).toFixed(1)} KB · ${image.type.replace("image/", "")}`
                  : ""}
                {" · Gemini Vision will parse this into a circuit"}
              </div>
            </div>
            <button
              type="button"
              onClick={() => onImageChange(null)}
              className="font-mono text-[10px] uppercase tracking-widest hover:text-[color:var(--bs-red)]"
              style={{ color: "var(--bs-fg-dim)" }}
              title="Remove image"
            >
              Remove ×
            </button>
          </div>
        )}

        <textarea
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          onPaste={handlePaste}
          placeholder={
            image
              ? "Optional: add notes (e.g. 'this is a 3.3V design, ignore the buzzer')…"
              : "An ESP32 connected to a DHT22 temperature sensor, USB-C power input… or drop a sketch."
          }
          className="w-full min-h-[110px] resize-none p-3 outline-none rounded text-[13.5px] leading-[1.55] font-mono"
          style={{
            background: "transparent",
            border: "none",
            color: "var(--bs-fg)",
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && canSubmit) {
              e.preventDefault();
              onSubmit();
            }
          }}
        />

        {dragOver && (
          <div
            className="pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-[11px] uppercase tracking-widest rounded"
            style={{
              color: "var(--bs-copper)",
              background: "color-mix(in srgb, var(--bs-bg) 70%, transparent)",
            }}
          >
            Drop sketch to attach
          </div>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(",")}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) acceptFile(file);
          if (e.target) e.target.value = "";
        }}
      />

      {error && (
        <div
          className="mt-2 px-2 py-1 rounded font-mono text-[11px]"
          style={{
            color: "var(--bs-red)",
            border: "1px solid var(--bs-red)",
            background: "var(--bs-bg-2)",
          }}
        >
          {error}
        </div>
      )}

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-2 px-2.5 py-1.5 rounded font-mono text-[11px] transition-colors"
          style={{
            border: "1px solid var(--bs-line-soft)",
            color: "var(--bs-fg-mute)",
            background: "var(--bs-bg-2)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--bs-copper)";
            e.currentTarget.style.color = "var(--bs-copper-2)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--bs-line-soft)";
            e.currentTarget.style.color = "var(--bs-fg-mute)";
          }}
          title="Attach sketch / breadboard photo"
        >
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
            <path
              d="M11.5 4.5l-5 5a2 2 0 102.83 2.83l5.5-5.5a3.5 3.5 0 10-4.95-4.95L4.4 7.36a5 5 0 107.07 7.07l4.5-4.5"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              strokeLinejoin="round"
              transform="translate(-1 -1)"
            />
          </svg>
          {image ? "Replace image" : "Attach sketch"}
        </button>

        <div
          className="flex items-center gap-2 font-mono text-[10px]"
          style={{ color: "var(--bs-fg-dim)" }}
        >
          <span style={{ color: "var(--bs-lime)" }}>●</span> gemini-2.5-pro
          <span style={{ color: "var(--bs-line)" }}>·</span>
          <span>~10s avg</span>
        </div>

        <button
          onClick={onSubmit}
          disabled={!canSubmit}
          className="bs-btn-primary ml-auto px-5 py-2.5 rounded flex items-center gap-2 text-[13px]"
        >
          {running ? (
            <>
              <span className="bs-spin" />
              Building PCB…
            </>
          ) : (
            <>Generate PCB →</>
          )}
        </button>
      </div>
    </div>
  );
};

export default PromptComposer;
