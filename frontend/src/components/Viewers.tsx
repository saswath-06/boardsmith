// Three viewers + tabs + EDA-tool footer.
import { Fragment, useState } from "react";
import type { BomData, Board3DData, GerberData, SchematicData } from "../types";
import { artifactUrl } from "../api";
import { useAuth } from "../lib/auth";
import Board3DViewer from "./Board3DViewer";

// ── PCB layout viewer — top-down board render with traces, pads, components.
interface PcbLayoutViewerProps {
  data: Board3DData | null;
}

export const PcbLayoutViewer = ({ data }: PcbLayoutViewerProps) => {
  if (!data) return <div className="bs-skeleton h-full w-full" />;
  const sx = 10; // mm → px
  const W = data.board.width * sx;
  const H = data.board.height * sx;
  return (
    <svg
      className="block"
      width="100%"
      height="100%"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: "100%", height: "100%" }}
    >
      <defs>
        <pattern id="board-tex" width="6" height="6" patternUnits="userSpaceOnUse">
          <rect width="6" height="6" fill="var(--bs-substrate)"/>
          <circle cx="3" cy="3" r="0.4" fill="rgba(255,255,255,0.04)"/>
        </pattern>
      </defs>
      <rect width={W} height={H} fill="url(#board-tex)" stroke="var(--bs-fg-dim)" strokeWidth="0.5"/>
      {/* corner fiducials */}
      {[[3,3],[W-3,3],[3,H-3],[W-3,H-3]].map(([cx,cy],i) => (
        <g key={i}>
          <circle cx={cx} cy={cy} r="2" fill="none" stroke="var(--bs-silk)" strokeWidth="0.4"/>
          <circle cx={cx} cy={cy} r="0.6" fill="var(--bs-silk)"/>
        </g>
      ))}
      {/* ratsnest */}
      {data.ratsnest.map((line, i) => (
        <line key={`rn-${i}`}
          x1={line.from_point[0]*sx} y1={line.from_point[1]*sx}
          x2={line.to_point[0]*sx}   y2={line.to_point[1]*sx}
          stroke="var(--bs-cyan)" strokeDasharray="3 3" strokeOpacity="0.6" strokeWidth="0.6"/>
      ))}
      {/* traces */}
      {data.traces.map((trace, i) => (
        <polyline key={`tr-${i}`}
          points={trace.points.map(([x,y]) => `${x*sx},${y*sx}`).join(" ")}
          fill="none" stroke="var(--bs-copper)" strokeWidth="2.4"
          strokeLinecap="round" strokeLinejoin="round"/>
      ))}
      {/* trace highlights */}
      {data.traces.map((trace, i) => (
        <polyline key={`th-${i}`}
          points={trace.points.map(([x,y]) => `${x*sx},${y*sx}`).join(" ")}
          fill="none" stroke="var(--bs-copper-2)" strokeWidth="0.8"
          strokeLinecap="round" strokeLinejoin="round" opacity="0.6"/>
      ))}
      {/* components */}
      {data.components.map((comp) => {
        const x = (comp.x - comp.width/2) * sx;
        const y = (comp.y - comp.height/2) * sx;
        const w = comp.width * sx;
        const h = comp.height * sx;
        return (
          <g key={comp.ref}>
            {/* silkscreen outline */}
            <rect x={x-1} y={y-1} width={w+2} height={h+2}
              fill="none" stroke="var(--bs-silk)" strokeWidth="0.4" strokeDasharray="2 1.5" opacity="0.55"/>
            {/* body */}
            <rect x={x} y={y} width={w} height={h} rx="1"
              fill={comp.color} stroke="rgba(255,255,255,0.2)" strokeWidth="0.4"/>
            {/* label */}
            <text x={comp.x*sx} y={comp.y*sx-1} textAnchor="middle"
              fontSize="7" fontWeight="600" fontFamily="IBM Plex Sans" fill="var(--bs-silk)">
              {comp.type}
            </text>
            <text x={comp.x*sx} y={comp.y*sx+7} textAnchor="middle"
              fontSize="5" fontFamily="IBM Plex Mono" fill="rgba(245,234,211,0.6)">
              {comp.ref}
            </text>
            {/* pads */}
            {comp.pads.map((pad, j) => (
              <g key={j}>
                <circle cx={pad.x*sx} cy={pad.y*sx} r="2.4" fill="var(--bs-gold)" stroke="var(--bs-copper)" strokeWidth="0.4"/>
                <circle cx={pad.x*sx} cy={pad.y*sx} r="0.8" fill="var(--bs-substrate)"/>
              </g>
            ))}
          </g>
        );
      })}
    </svg>
  );
};

// ── Schematic viewer — render schemdraw-style SVG.
interface SchematicViewerProps {
  svg: string | null | undefined;
}

export const SchematicViewer = ({ svg }: SchematicViewerProps) => {
  if (!svg) return <div className="bs-skeleton h-full w-full" />;
  // Strip any fixed width/height attrs from the backend SVG so it scales to
  // its container; the .bs-schematic-host CSS rule then forces 100%/100%.
  const responsive = svg
    .replace(/<svg([^>]*?)\swidth="[^"]*"/i, "<svg$1")
    .replace(/<svg([^>]*?)\sheight="[^"]*"/i, "<svg$1");
  return (
    <div
      className="bs-schematic-host h-full w-full bg-[#fafaf7] flex items-center justify-center overflow-hidden p-4"
      dangerouslySetInnerHTML={{ __html: responsive }}
    />
  );
};

// ── BOM viewer — bill-of-materials table.
interface BomViewerProps {
  bom: BomData | null;
}

const CATEGORY_BADGE: Record<string, string> = {
  microcontroller: "var(--bs-cyan)",
  sensor:          "var(--bs-lime)",
  power:           "var(--bs-amber)",
  discrete:        "var(--bs-red)",
  passive:         "var(--bs-fg-dim)",
  connector:       "var(--bs-copper)",
};

export const BomViewer = ({ bom }: BomViewerProps) => {
  if (!bom) return <div className="bs-skeleton h-full w-full" />;
  if (!bom.lines.length) {
    return (
      <div className="h-full w-full flex items-center justify-center font-mono text-[11px]"
        style={{ color: "var(--bs-fg-dim)" }}>
        No components in design.
      </div>
    );
  }

  const matched = bom.lines.filter((l) => l.lcsc_part_number).length;
  const matchPct = bom.total_unique
    ? Math.round((matched / bom.total_unique) * 100)
    : 0;

  return (
    <div className="h-full w-full overflow-auto bs-scroll" style={{ background: "var(--bs-bg)" }}>
      {/* totals banner */}
      <div
        className="sticky top-0 z-10 flex items-center gap-4 px-4 py-2 border-b"
        style={{
          background: "var(--bs-panel-2)",
          borderColor: "var(--bs-line-soft)",
        }}
      >
        <div className="flex items-center gap-3 font-mono text-[11px]">
          <span style={{ color: "var(--bs-fg-dim)" }}>UNIQUE</span>
          <span className="text-[15px] font-semibold" style={{ color: "var(--bs-fg)" }}>
            {bom.total_unique}
          </span>
          <span style={{ color: "var(--bs-line)" }}>·</span>
          <span style={{ color: "var(--bs-fg-dim)" }}>TOTAL PARTS</span>
          <span className="text-[15px] font-semibold" style={{ color: "var(--bs-fg)" }}>
            {bom.total_quantity}
          </span>
          {matched > 0 && (
            <>
              <span style={{ color: "var(--bs-line)" }}>·</span>
              <span style={{ color: "var(--bs-fg-dim)" }}>LCSC MATCHED</span>
              <span className="text-[15px] font-semibold" style={{ color: "var(--bs-lime)" }}>
                {matched}/{bom.total_unique}
              </span>
            </>
          )}
        </div>
        <span
          className="ml-auto font-mono text-[10px] uppercase tracking-widest"
          style={{ color: "var(--bs-fg-dim)" }}
        >
          {bom.project_name}
        </span>
      </div>

      {/* JLCPCB call-to-action — only when we have at least one LCSC match */}
      {matched > 0 && (
        <div
          className="mx-4 my-3 px-4 py-3 rounded flex items-start gap-3"
          style={{
            background: "var(--bs-panel)",
            border: "1px solid var(--bs-copper)",
          }}
        >
          <div
            className="flex h-7 w-7 items-center justify-center rounded shrink-0 font-bold text-[11px] mt-0.5"
            style={{ background: "var(--bs-copper)", color: "var(--bs-bg)" }}
            aria-hidden
          >
            JL
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold mb-1" style={{ color: "var(--bs-fg)" }}>
              Ready to fab on JLCPCB
              <span
                className="ml-2 font-mono text-[10px] px-1.5 py-0.5 rounded"
                style={{
                  color: "var(--bs-lime)",
                  border: "1px solid var(--bs-lime)",
                }}
              >
                {matchPct}% PARTS MATCHED
              </span>
            </div>
            <ol
              className="font-mono text-[11px] leading-relaxed list-decimal pl-4 space-y-0.5"
              style={{ color: "var(--bs-fg-mute)" }}
            >
              <li>
                Download the Gerber zip and the{" "}
                <span style={{ color: "var(--bs-copper)" }}>JLCPCB BOM CSV</span>{" "}
                from the bars below.
              </li>
              <li>
                Open{" "}
                <a
                  href="https://cart.jlcpcb.com/quote"
                  target="_blank"
                  rel="noreferrer"
                  className="hover:underline"
                  style={{ color: "var(--bs-cyan)" }}
                >
                  cart.jlcpcb.com/quote
                </a>{" "}
                and upload the Gerber zip.
              </li>
              <li>
                Enable <span style={{ color: "var(--bs-copper)" }}>SMT Assembly</span>{" "}
                and upload the BOM CSV plus a CPL (centroid) file.
              </li>
              <li>
                Confirm pricing and place the order. Boards typically ship in 5–7 days.
              </li>
            </ol>
          </div>
          <a
            href="https://cart.jlcpcb.com/quote"
            target="_blank"
            rel="noreferrer"
            className="bs-btn-primary px-3 py-2 rounded text-[12px] flex items-center gap-2 shrink-0 no-underline"
          >
            Open JLCPCB →
          </a>
        </div>
      )}

      <table className="w-full text-[12px]" style={{ borderCollapse: "collapse" }}>
        <thead className="sticky z-[5]" style={{ top: 41, background: "var(--bs-bg-2)" }}>
          <tr style={{ color: "var(--bs-fg-dim)" }} className="font-mono text-[10px] uppercase tracking-wider">
            <th className="text-left px-3 py-2 w-10">#</th>
            <th className="text-left px-3 py-2">References</th>
            <th className="text-right px-3 py-2 w-12">Qty</th>
            <th className="text-left px-3 py-2 w-20">Value</th>
            <th className="text-left px-3 py-2">Description</th>
            <th className="text-left px-3 py-2 w-44">Package</th>
            <th className="text-left px-3 py-2 w-28">LCSC #</th>
          </tr>
        </thead>
        <tbody>
          {bom.lines.map((line, idx) => {
            const badgeColor =
              CATEGORY_BADGE[line.category] ?? "var(--bs-fg-dim)";
            return (
              <tr
                key={line.line_id}
                style={{
                  background: idx % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                  borderTop: "1px solid var(--bs-line-soft)",
                  color: "var(--bs-fg)",
                }}
              >
                <td className="px-3 py-2 font-mono text-[11px]" style={{ color: "var(--bs-fg-dim)" }}>
                  {line.line_id}
                </td>
                <td className="px-3 py-2 font-mono text-[11px]">
                  {line.references.join(", ")}
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  <span
                    className="px-1.5 py-0.5 rounded font-semibold"
                    style={{
                      background: "var(--bs-bg-2)",
                      color: "var(--bs-fg)",
                      border: "1px solid var(--bs-line-soft)",
                    }}
                  >
                    {line.quantity}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono" style={{ color: "var(--bs-copper)" }}>
                  {line.value || "—"}
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-1.5 w-1.5 rounded-full shrink-0"
                      style={{ background: badgeColor }}
                      title={line.category}
                    />
                    <span>{line.description}</span>
                  </div>
                </td>
                <td
                  className="px-3 py-2 font-mono text-[10.5px] truncate"
                  style={{ color: "var(--bs-fg-mute)" }}
                  title={line.package ?? ""}
                >
                  {line.package || "—"}
                </td>
                <td className="px-3 py-2 font-mono text-[11px]">
                  {line.lcsc_part_number ? (
                    <a
                      href={`https://www.lcsc.com/product-detail/${line.lcsc_part_number}.html`}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: "var(--bs-lime)" }}
                      className="hover:underline"
                      title={line.manufacturer_pn ?? undefined}
                    >
                      {line.lcsc_part_number}
                    </a>
                  ) : (
                    <span style={{ color: "var(--bs-fg-dim)" }}>—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ── Tab strip
const VIEWER_TABS = [
  { id: "3d",        label: "3D Board",   sub: "three.js · GL render" },
  { id: "pcb",       label: "PCB Layout", sub: "top view · F.Cu" },
  { id: "schematic", label: "Schematic",  sub: "schemdraw · SVG" },
  { id: "bom",       label: "BOM",        sub: "parts list · LCSC" },
] as const;

type TabId = typeof VIEWER_TABS[number]["id"];

// ── Status footer — real EDA-app vibe
interface ViewerFooterProps {
  data: Board3DData | null;
  drcStatus?: "pass" | "warn";
}

export const ViewerFooter = ({ data, drcStatus = "pass" }: ViewerFooterProps) => {
  const routed = data?.traces?.length ?? 0;
  const unrouted = data?.ratsnest?.length ?? 0;
  const stats: Array<[string, string | number]> = [
    ["Board",      data ? `${data.board.width} × ${data.board.height} mm` : "—"],
    ["Layers",     "2"],
    ["Components", data?.components.length ?? "—"],
    ["Nets",       data ? `${routed}/${routed + unrouted}` : "—"],
    ["Pads",       data ? data.components.reduce((s, c) => s + c.pads.length, 0) : "—"],
    ["Min trace",  "0.20 mm"],
    ["Min clear",  "0.15 mm"],
  ];
  return (
    <div className="flex items-center gap-0 px-3 py-1.5 border-t font-mono text-[10px] uppercase tracking-wider"
      style={{ borderColor: "var(--bs-line-soft)", background: "var(--bs-bg-2)" }}>
      {stats.map(([k, v], i) => (
        <Fragment key={k}>
          {i > 0 && <span style={{ color: "var(--bs-line)" }} className="px-3">·</span>}
          <span style={{ color: "var(--bs-fg-dim)" }}>{k}</span>
          <span className="ml-1.5" style={{ color: "var(--bs-fg)" }}>{v}</span>
        </Fragment>
      ))}
      <span className="ml-auto flex items-center gap-2">
        <span style={{ color: "var(--bs-fg-dim)" }}>DRC</span>
        <span className="bs-pill" style={{ color: drcStatus === "pass" ? "var(--bs-lime)" : "var(--bs-amber)" }}>
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: drcStatus === "pass" ? "var(--bs-lime)" : "var(--bs-amber)" }} />
          {drcStatus === "pass" ? "Pass" : "Warn"}
        </span>
      </span>
    </div>
  );
};

// ── ViewerTabs — top-level container
interface ViewerTabsProps {
  data: Board3DData | null;
  schematic: SchematicData | null;
  gerber: GerberData | null;
  bom: BomData | null;
  jobId: string | null;
}

const ViewerTabs = ({ data, schematic, gerber, bom, jobId }: ViewerTabsProps) => {
  const [active, setActive] = useState<TabId>("3d");
  const { session } = useAuth();
  const token = session?.access_token ?? null;
  const kicadArtifact = schematic?.artifacts?.kicad_schematic;
  const kicadHref = kicadArtifact ? artifactUrl(kicadArtifact, token) : "";
  const kicadFilename = schematic?.kicad_filename ?? "boardsmith.kicad_sch";
  const downloadHref = gerber?.download_url ? artifactUrl(gerber.download_url, token) : "";
  const filename = gerber?.filename ?? "boardsmith.zip";
  const bomCsvHref = bom?.artifacts?.bom_csv ? artifactUrl(bom.artifacts.bom_csv, token) : "";
  const bomCsvName = bom?.filenames?.bom_csv ?? "boardsmith_BOM.csv";
  const bomJlcpcbHref = bom?.artifacts?.bom_jlcpcb_csv ? artifactUrl(bom.artifacts.bom_jlcpcb_csv, token) : "";
  const bomJlcpcbName = bom?.filenames?.bom_jlcpcb_csv ?? "boardsmith_BOM_JLCPCB.csv";
  return (
    <section className="bs-panel flex flex-col h-full overflow-hidden">
      {/* tab bar */}
      <div className="flex items-stretch border-b" style={{ borderColor: "var(--bs-line-soft)" }}>
        {VIEWER_TABS.map((tab) => {
          const isActive = active === tab.id;
          return (
            <button key={tab.id} onClick={() => setActive(tab.id)}
              className="relative px-4 py-3 text-left transition-colors"
              style={{
                borderRight: "1px solid var(--bs-line-soft)",
                background: isActive ? "var(--bs-panel)" : "transparent",
                color: isActive ? "var(--bs-fg)" : "var(--bs-fg-mute)",
              }}>
              {isActive && (
                <span className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: "var(--bs-copper)" }}/>
              )}
              <div className="text-[13px] font-medium">{tab.label}</div>
              <div className="font-mono text-[10px] mt-0.5" style={{ color: "var(--bs-fg-dim)" }}>{tab.sub}</div>
            </button>
          );
        })}
        <div className="ml-auto flex items-center pr-3 gap-2">
          <span className="font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>Job</span>
          <span className="font-mono text-[11px]" style={{ color: "var(--bs-fg-mute)" }}>
            {jobId ? jobId.slice(0, 8) : "—"}
          </span>
        </div>
      </div>

      {/* canvas */}
      <div className="flex-1 relative overflow-hidden" style={{ background: "var(--bs-bg-2)" }}>
        <div className={`absolute inset-0 ${active === "3d" ? "block" : "hidden"}`}><Board3DViewer data={data}/></div>
        <div className={`absolute inset-0 ${active === "pcb" ? "block" : "hidden"}`}><PcbLayoutViewer data={data}/></div>
        <div className={`absolute inset-0 ${active === "schematic" ? "block" : "hidden"}`}><SchematicViewer svg={schematic?.svg}/></div>
        <div className={`absolute inset-0 ${active === "bom" ? "block" : "hidden"}`}><BomViewer bom={bom}/></div>
      </div>

      {/* footer */}
      <ViewerFooter data={data} />

      {/* KiCad schematic download */}
      {kicadHref && (
        <div className="flex items-center gap-3 px-4 py-2.5 border-t"
          style={{ borderColor: "var(--bs-line-soft)", background: "var(--bs-panel-2)" }}>
          <span className="bs-pill" style={{ color: "var(--bs-copper)" }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--bs-copper)" }}/>
            KiCad
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium truncate" style={{ color: "var(--bs-fg)" }}>
              KiCad schematic · {kicadFilename}
            </div>
            <div className="font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
              lib_symbols · wires · net labels · A4 paper
            </div>
          </div>
          <a href={kicadHref} download={kicadFilename}
            className="bs-btn-primary px-4 py-2 rounded text-[13px] flex items-center gap-2 no-underline">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path d="M8 2v8m0 0l-3-3m3 3l3-3M3 13h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Download
          </a>
        </div>
      )}

      {/* BOM download bar */}
      {bom && bom.lines.length > 0 && bomCsvHref && (
        <div
          className="flex items-center gap-3 px-4 py-2.5 border-t"
          style={{ borderColor: "var(--bs-line-soft)", background: "var(--bs-panel-2)" }}
        >
          <span className="bs-pill" style={{ color: "var(--bs-amber)" }}>
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: "var(--bs-amber)" }}
            />
            BOM
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium truncate" style={{ color: "var(--bs-fg)" }}>
              Bill of Materials · {bom.total_unique} unique · {bom.total_quantity} parts
            </div>
            <div className="font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
              engineering CSV · JLCPCB SMT-upload CSV
            </div>
          </div>
          <a
            href={bomCsvHref}
            download={bomCsvName}
            className="bs-btn-ghost px-3 py-2 rounded text-[12px] flex items-center gap-2 no-underline"
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path
                d="M8 2v8m0 0l-3-3m3 3l3-3M3 13h10"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            BOM.csv
          </a>
          {bomJlcpcbHref && (
            <a
              href={bomJlcpcbHref}
              download={bomJlcpcbName}
              className="bs-btn-primary px-4 py-2 rounded text-[13px] flex items-center gap-2 no-underline"
              title="Upload this CSV to JLCPCB when ordering SMT assembly"
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <path
                  d="M8 2v8m0 0l-3-3m3 3l3-3M3 13h10"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              JLCPCB BOM
            </a>
          )}
        </div>
      )}

      {/* gerber download bar */}
      {gerber && gerber.download_url && (
        <div className="flex items-center gap-3 px-4 py-2.5 border-t"
          style={{ borderColor: "var(--bs-line-soft)", background: "var(--bs-panel-2)" }}>
          <span className="bs-pill" style={{ color: "var(--bs-lime)" }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--bs-lime)" }}/>
            Ready
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium truncate" style={{ color: "var(--bs-fg)" }}>
              Gerber package · {filename}
            </div>
            <div className="font-mono text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
              F.Cu · B.Cu · F.Mask · B.Mask · F.SilkS · Edge.Cuts · .drl
            </div>
          </div>
          <a href={downloadHref} download={filename}
            className="bs-btn-primary px-4 py-2 rounded text-[13px] flex items-center gap-2 no-underline">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path d="M8 2v8m0 0l-3-3m3 3l3-3M3 13h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Download
          </a>
        </div>
      )}
    </section>
  );
};

export default ViewerTabs;
