// Read-only viewer for /p/:id share links. No auth required, no
// download bars — just the visualization tabs (3D / PCB / Schematic /
// BOM cost breakdown). Pulls from /api/public/jobs/:id, which only
// returns snapshots for jobs whose is_public flag is set.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getPublicJob } from "../api";
import BoardsmithLogo from "./Logo";
import ViewerTabs from "./Viewers";
import type {
  Board3DData,
  BomData,
  GerberData,
  JobSnapshot,
  SchematicData,
} from "../types";

interface ProjectedSnapshot {
  data: Board3DData | null;
  schematic: SchematicData | null;
  gerber: GerberData | null;
  bom: BomData | null;
}

function projectPublicSnapshot(snapshot: JobSnapshot): ProjectedSnapshot {
  let data: Board3DData | null = null;
  let schematic: SchematicData | null = null;
  let gerber: GerberData | null = null;
  let bom: BomData | null = null;

  for (const event of snapshot.events) {
    if (event.status !== "complete") continue;
    const payload = event.data as Record<string, unknown> | null | undefined;
    if (event.stage === "schematic" && payload && typeof payload === "object" && "svg" in payload) {
      schematic = payload as unknown as SchematicData;
    }
    if (event.stage === "3d" && payload && typeof payload === "object" && "components" in payload) {
      data = payload as unknown as Board3DData;
    }
    if (event.stage === "gerber" && payload && typeof payload === "object" && "download_url" in payload) {
      gerber = payload as unknown as GerberData;
    }
    if (event.stage === "bom" && payload && typeof payload === "object" && "lines" in payload) {
      bom = payload as unknown as BomData;
    }
  }

  return { data, schematic, gerber, bom };
}

const PublicViewer = () => {
  const { id } = useParams<{ id: string }>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<JobSnapshot | null>(null);
  const [projected, setProjected] = useState<ProjectedSnapshot>({
    data: null,
    schematic: null,
    gerber: null,
    bom: null,
  });

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    getPublicJob(id)
      .then((snap) => {
        setSnapshot(snap);
        setProjected(projectPublicSnapshot(snap));
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center font-mono text-[11px]"
        style={{ color: "var(--bs-fg-dim)" }}
      >
        Loading shared board…
      </div>
    );
  }

  if (error || !snapshot) {
    return (
      <div
        className="min-h-screen flex flex-col items-center justify-center px-6 text-center gap-3"
        style={{ color: "var(--bs-fg)" }}
      >
        <BoardsmithLogo size={42} />
        <h1 className="text-[20px] font-semibold tracking-tight">
          This board isn't shared publicly
        </h1>
        <p
          className="max-w-sm text-[13px]"
          style={{ color: "var(--bs-fg-mute)" }}
        >
          The owner may have unpublished it, or the link is invalid.
        </p>
        <Link
          to="/"
          className="bs-btn-primary mt-2 px-4 py-2 rounded text-[13px] no-underline"
        >
          Make your own →
        </Link>
      </div>
    );
  }

  const created = new Date(snapshot.created_at * 1000);
  const dateLabel = created.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <div className="h-screen flex flex-col">
      <header
        className="flex items-center gap-4 px-4 h-12 border-b shrink-0"
        style={{
          borderColor: "var(--bs-line-soft)",
          background: "var(--bs-bg-2)",
        }}
      >
        <Link to="/" className="flex items-center gap-2.5 shrink-0 no-underline">
          <BoardsmithLogo size={26} />
          <span
            className="text-[15px] font-semibold tracking-tight"
            style={{ color: "var(--bs-fg)" }}
          >
            Boardsmith
          </span>
        </Link>

        <div
          className="flex items-center gap-2 font-mono text-[11px]"
          style={{ color: "var(--bs-fg-dim)" }}
        >
          <span>/</span>
          <span style={{ color: "var(--bs-fg-mute)" }}>shared</span>
          <span>/</span>
          <span style={{ color: "var(--bs-copper)" }}>
            {snapshot.job_id.slice(0, 8)}
          </span>
        </div>

        <div className="flex-1 min-w-0">
          <div
            className="text-[13px] truncate"
            style={{ color: "var(--bs-fg)" }}
          >
            {snapshot.description || "Shared circuit"}
          </div>
          <div
            className="font-mono text-[10px] uppercase tracking-widest"
            style={{ color: "var(--bs-fg-dim)" }}
          >
            Read-only · shared {dateLabel}
          </div>
        </div>

        <Link
          to="/"
          className="bs-btn-primary px-4 h-8 rounded text-[12px] flex items-center gap-2 shrink-0 no-underline"
        >
          Make your own →
        </Link>
      </header>

      <main className="flex-1 grid gap-2 p-2 min-h-0" style={{ gridTemplateColumns: "1fr" }}>
        <ViewerTabs
          data={projected.data}
          schematic={projected.schematic}
          gerber={projected.gerber}
          bom={projected.bom}
          jobId={snapshot.job_id}
          readOnly
        />
      </main>
    </div>
  );
};

export default PublicViewer;
