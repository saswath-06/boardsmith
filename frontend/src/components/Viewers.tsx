// Three viewers + tabs + EDA-tool footer.
import { Fragment, useState } from "react";
import type {
  BomData,
  Board3DData,
  FirmwareData,
  GerberData,
  SchematicData,
} from "../types";
import { artifactUrl } from "../api";
import { useAuth } from "../lib/auth";
import Board3DViewer from "./Board3DViewer";
import FirmwareViewer from "./FirmwareViewer";

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
  readOnly?: boolean;
}

interface CostLineProps {
  label: string;
  value: number;
  hint?: string;
}

const CostLine = ({ label, value, hint }: CostLineProps) => (
  <div className="flex items-baseline gap-3 py-0.5">
    <span style={{ color: "var(--bs-fg)" }}>{label}</span>
    {hint && (
      <span className="text-[10px]" style={{ color: "var(--bs-fg-dim)" }}>
        {hint}
      </span>
    )}
    <span className="ml-auto" />
    <span className="tabular-nums" style={{ color: "var(--bs-fg-mute)" }}>
      ${value.toFixed(2)}
    </span>
  </div>
);

const CATEGORY_BADGE: Record<string, string> = {
  microcontroller: "var(--bs-cyan)",
  sensor:          "var(--bs-lime)",
  power:           "var(--bs-amber)",
  discrete:        "var(--bs-red)",
  passive:         "var(--bs-fg-dim)",
  connector:       "var(--bs-copper)",
};

// ── Live JLCPCB cost model ────────────────────────────────────────────────
// Mirrors backend/app/cost.py so the slider/input can recompute the
// estimate every keystroke without a backend round-trip. Numbers match
// JLCPCB's 100×100 mm 2-layer green soldermask + 1-side SMT pricing.
const QTY_MIN = 1;
const QTY_MAX = 500;
const SCRAP_BUFFER = 1.05;
const SMT_SETUP_USD = 8.0;
const SMT_PLACEMENT_PER_JOINT = 0.0017;
const STENCIL_USD = 8.0;
const SHIPPING_USD = 5.0;

// Tiered PCB fab cost (USD). Sorted by qty; we pick the smallest tier
// at-or-above the requested quantity so the estimate stays conservative.
const PCB_FAB_TIERS: Array<[number, number]> = [
  [5, 2.0],
  [30, 8.0],
  [100, 25.0],
  [200, 45.0],
  [500, 95.0],
];

function pickPcbFabCost(qty: number): number {
  for (const [tier, price] of PCB_FAB_TIERS) {
    if (qty <= tier) return price;
  }
  return PCB_FAB_TIERS[PCB_FAB_TIERS.length - 1][1];
}

interface LiveCostEstimate {
  qty: number;
  parts: number;
  pcb_fab: number;
  smt_setup: number;
  smt_placement: number;
  stencil: number;
  shipping: number;
  total: number;
  smt_joints: number;
}

function buildLiveEstimate(
  unitCostUsd: number,
  smtJoints: number,
  rawQty: number,
): LiveCostEstimate {
  const qty = Math.max(QTY_MIN, Math.min(QTY_MAX, Math.round(rawQty || 1)));
  const parts = unitCostUsd * qty * SCRAP_BUFFER;
  const pcbFab = pickPcbFabCost(qty);
  const hasSmt = smtJoints > 0;
  const smtSetup = hasSmt ? SMT_SETUP_USD : 0;
  const smtPlacement = hasSmt ? smtJoints * qty * SMT_PLACEMENT_PER_JOINT : 0;
  const stencil = hasSmt ? STENCIL_USD : 0;
  const total =
    parts + pcbFab + smtSetup + smtPlacement + stencil + SHIPPING_USD;
  const round2 = (n: number) => Math.round(n * 100) / 100;
  return {
    qty,
    parts: round2(parts),
    pcb_fab: round2(pcbFab),
    smt_setup: round2(smtSetup),
    smt_placement: round2(smtPlacement),
    stencil: round2(stencil),
    shipping: round2(SHIPPING_USD),
    total: round2(total),
    smt_joints: smtJoints,
  };
}

const QTY_PRESETS: number[] = [5, 30, 100, 250, 500];

export const BomViewer = ({ bom, readOnly = false }: BomViewerProps) => {
  // Default to 5 boards — the JLCPCB minimum — so the estimate is never
  // empty even on the first render before the user touches the input.
  const [selectedQty, setSelectedQty] = useState<number>(5);
  // Allow an in-flight empty / partial input without overwriting the
  // committed quantity. The text mirror is what the <input> shows;
  // selectedQty is what we actually price against.
  const [qtyText, setQtyText] = useState<string>("5");

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
  const totalCost =
    typeof bom.total_unit_cost_usd === "number" && bom.total_unit_cost_usd > 0
      ? bom.total_unit_cost_usd
      : null;

  const activeEstimate =
    totalCost !== null
      ? buildLiveEstimate(totalCost, bom.smt_joints ?? 0, selectedQty)
      : null;

  const commitQty = (raw: number) => {
    const clamped = Math.max(QTY_MIN, Math.min(QTY_MAX, Math.round(raw || 1)));
    setSelectedQty(clamped);
    setQtyText(String(clamped));
  };

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
        <div className="flex items-center gap-3 font-mono text-[11px] flex-wrap">
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
              <span style={{ color: "var(--bs-fg-dim)" }}>LCSC</span>
              <span className="text-[15px] font-semibold" style={{ color: "var(--bs-lime)" }}>
                {matched}/{bom.total_unique}
              </span>
            </>
          )}
          {totalCost !== null && (
            <>
              <span style={{ color: "var(--bs-line)" }}>·</span>
              <span style={{ color: "var(--bs-fg-dim)" }}>PARTS / BOARD</span>
              <span
                className="text-[15px] font-semibold"
                style={{ color: "var(--bs-copper)" }}
                title={`${bom.priced_line_count ?? 0}/${bom.total_unique} lines priced`}
              >
                ${totalCost.toFixed(2)}
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

      {/* All-in build cost breakdown (parts + JLCPCB fab + assembly) */}
      {activeEstimate && (
        <div
          className="mx-4 my-3 rounded overflow-hidden"
          style={{
            background: "var(--bs-panel)",
            border: "1px solid var(--bs-line-soft)",
          }}
        >
          <div
            className="flex items-center gap-3 px-4 py-2.5 border-b flex-wrap"
            style={{ borderColor: "var(--bs-line-soft)" }}
          >
            <span
              className="font-mono text-[10px] uppercase tracking-widest"
              style={{ color: "var(--bs-fg-dim)" }}
            >
              All-in build estimate
            </span>

            {/* Direct number input — type any qty between 1 and 500. */}
            <div className="flex items-center gap-1.5">
              <input
                type="number"
                min={QTY_MIN}
                max={QTY_MAX}
                step={1}
                value={qtyText}
                onChange={(e) => {
                  const v = e.target.value;
                  setQtyText(v);
                  if (v === "") return;
                  const n = Number(v);
                  if (Number.isFinite(n) && n >= QTY_MIN && n <= QTY_MAX) {
                    setSelectedQty(Math.round(n));
                  }
                }}
                onBlur={(e) => commitQty(Number(e.target.value))}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.currentTarget.blur();
                  }
                }}
                className="w-16 px-2 py-1 rounded font-mono text-[12px] text-right tabular-nums outline-none"
                style={{
                  background: "var(--bs-bg)",
                  color: "var(--bs-fg)",
                  border: "1px solid var(--bs-copper)",
                }}
                aria-label="Board quantity"
              />
              <span
                className="font-mono text-[11px]"
                style={{ color: "var(--bs-fg-mute)" }}
              >
                boards
              </span>
            </div>

            {/* Slider — drag to scrub from 1 to 500. */}
            <input
              type="range"
              min={QTY_MIN}
              max={QTY_MAX}
              step={1}
              value={selectedQty}
              onChange={(e) => {
                const n = Number(e.target.value);
                setSelectedQty(n);
                setQtyText(String(n));
              }}
              className="bs-qty-slider flex-1 min-w-[120px] max-w-[260px] accent-current"
              style={{ accentColor: "var(--bs-copper)" }}
              aria-label="Board quantity slider"
            />

            {/* Quick preset chips — common JLCPCB order sizes. */}
            <div className="flex items-center gap-1">
              {QTY_PRESETS.map((q) => {
                const isActive = q === selectedQty;
                return (
                  <button
                    key={q}
                    type="button"
                    onClick={() => commitQty(q)}
                    className="px-2 py-0.5 rounded font-mono text-[10.5px] transition-colors"
                    style={{
                      background: isActive ? "var(--bs-copper)" : "transparent",
                      color: isActive ? "var(--bs-bg)" : "var(--bs-fg-dim)",
                      border: `1px solid ${
                        isActive ? "var(--bs-copper)" : "var(--bs-line-soft)"
                      }`,
                    }}
                  >
                    {q}
                  </button>
                );
              })}
            </div>

            <span
              className="ml-auto font-mono text-[10px]"
              style={{ color: "var(--bs-fg-dim)" }}
            >
              JLCPCB · 100×100 mm 2-layer · 1 side SMT
            </span>
          </div>
          <div className="px-4 py-3 font-mono text-[12px]">
            <CostLine
              label={`Parts (${activeEstimate.qty} × $${(totalCost ?? 0).toFixed(2)})`}
              value={activeEstimate.parts}
              hint="× 1.05 scrap buffer"
            />
            <CostLine
              label={`PCB fabrication (${activeEstimate.qty} boards)`}
              value={activeEstimate.pcb_fab}
            />
            {activeEstimate.smt_setup > 0 && (
              <CostLine
                label="SMT setup + stencil"
                value={activeEstimate.smt_setup + activeEstimate.stencil}
                hint={`$${activeEstimate.smt_setup.toFixed(2)} setup + $${activeEstimate.stencil.toFixed(2)} stencil`}
              />
            )}
            {activeEstimate.smt_placement > 0 && (
              <CostLine
                label={`Component placement (${activeEstimate.smt_joints} joints × ${activeEstimate.qty})`}
                value={activeEstimate.smt_placement}
                hint="$0.0017 per joint"
              />
            )}
            <CostLine
              label="Shipping (DHL economy estimate)"
              value={activeEstimate.shipping}
            />
            <div
              className="my-2 border-t"
              style={{ borderColor: "var(--bs-line-soft)" }}
            />
            <div className="flex items-baseline gap-3">
              <span
                className="text-[12px] uppercase tracking-wider"
                style={{ color: "var(--bs-fg-dim)" }}
              >
                All-in build
              </span>
              <span className="ml-auto" />
              <span
                className="text-[10px]"
                style={{ color: "var(--bs-fg-dim)" }}
              >
                ${(activeEstimate.total / activeEstimate.qty).toFixed(2)}/board
              </span>
              <span
                className="text-[18px] font-semibold tabular-nums"
                style={{ color: "var(--bs-copper)" }}
              >
                ${activeEstimate.total.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* JLCPCB call-to-action — only when we have at least one LCSC match */}
      {matched > 0 && !readOnly && (
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
                Download the{" "}
                <span style={{ color: "var(--bs-copper)" }}>manufacturing bundle</span>{" "}
                from the bottom bar — one zip with Gerbers, BOM, JLCPCB BOM, and CPL.
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
                and upload the zip — the Gerber files inside are auto-detected.
              </li>
              <li>
                Enable <span style={{ color: "var(--bs-copper)" }}>SMT Assembly</span>;
                upload the JLCPCB BOM CSV and CPL CSV from the same zip.
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
            <th className="text-left px-3 py-2 w-36">Package</th>
            <th className="text-left px-3 py-2 w-24">LCSC #</th>
            <th className="text-right px-3 py-2 w-20">Unit $</th>
            <th className="text-right px-3 py-2 w-20">Ext $</th>
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
                <td
                  className="px-3 py-2 text-right font-mono text-[11px]"
                  style={{ color: "var(--bs-fg-mute)" }}
                >
                  {typeof line.unit_price_usd === "number"
                    ? `$${line.unit_price_usd.toFixed(4)}`
                    : "—"}
                </td>
                <td
                  className="px-3 py-2 text-right font-mono text-[11px]"
                  style={{ color: "var(--bs-fg)" }}
                >
                  {typeof line.extended_price_usd === "number"
                    ? `$${line.extended_price_usd.toFixed(2)}`
                    : "—"}
                </td>
              </tr>
            );
          })}
          {totalCost !== null && (
            <tr
              style={{
                background: "var(--bs-panel-2)",
                borderTop: "2px solid var(--bs-line)",
                color: "var(--bs-fg)",
              }}
            >
              <td colSpan={6} className="px-3 py-2 text-right font-mono text-[11px] uppercase tracking-wider"
                style={{ color: "var(--bs-fg-dim)" }}>
                Total ({bom.priced_line_count}/{bom.total_unique} lines priced)
              </td>
              <td colSpan={2} className="px-3 py-2 text-right font-mono text-[12px] font-semibold"
                style={{ color: "var(--bs-copper)" }}>
                Unit cost
              </td>
              <td className="px-3 py-2 text-right font-mono text-[13px] font-semibold"
                style={{ color: "var(--bs-copper)" }}>
                ${totalCost.toFixed(2)}
              </td>
            </tr>
          )}
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
  { id: "firmware",  label: "Firmware",   sub: "Arduino .ino · pin-aware" },
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
  firmware: FirmwareData | null;
  jobId: string | null;
  /** When true, hide all download/simulate/KiCad action bars. Used by
   *  the public-share viewer so anonymous visitors can browse but not
   *  pull manufacturing artifacts. */
  readOnly?: boolean;
}

const ViewerTabs = ({
  data,
  schematic,
  gerber,
  bom,
  firmware,
  jobId,
  readOnly = false,
}: ViewerTabsProps) => {
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
  const cplHref = gerber?.cpl_url ? artifactUrl(gerber.cpl_url, token) : "";
  const bundleIncludes = gerber?.bundle_includes ?? [];
  const firmwareHref = firmware?.artifacts?.firmware_ino
    ? artifactUrl(firmware.artifacts.firmware_ino, token)
    : "";
  const firmwareFilename = firmware?.filename ?? "main.ino";
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
        <div className={`absolute inset-0 ${active === "firmware" ? "block" : "hidden"}`}><FirmwareViewer firmware={firmware}/></div>
        <div className={`absolute inset-0 ${active === "bom" ? "block" : "hidden"}`}><BomViewer bom={bom} readOnly={readOnly}/></div>
      </div>

      {/* footer */}
      <ViewerFooter data={data} />

      {/* Schematic actions: simulate in browser + KiCad export */}
      {!readOnly && kicadHref && (
        <div className="flex items-center gap-3 px-4 py-2.5 border-t"
          style={{ borderColor: "var(--bs-line-soft)", background: "var(--bs-panel-2)" }}>
          <span className="bs-pill" style={{ color: "var(--bs-copper)" }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--bs-copper)" }}/>
            Schematic
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium truncate" style={{ color: "var(--bs-fg)" }}>
              {schematic?.simulate_url
                ? `Live SPICE simulation ready · ${kicadFilename}`
                : `KiCad schematic · ${kicadFilename}`}
            </div>
            <div className="font-mono text-[10px] truncate" style={{ color: "var(--bs-fg-dim)" }}>
              {schematic?.simulate_url && schematic?.simulate_summary
                ? `Falstad: ${schematic.simulate_summary.simulatable_count ?? 0}/${schematic.simulate_summary.total_components ?? 0} parts modeled · ${(schematic.simulate_summary.supply_voltage ?? 5).toFixed(1)}V supply${
                    (schematic.simulate_summary.skipped_refs ?? []).length > 0
                      ? ` · skipped ${(schematic.simulate_summary.skipped_refs ?? []).join(", ")}`
                      : ""
                  }`
                : schematic?.simulate_summary?.reason
                ? schematic.simulate_summary.reason
                : "lib_symbols · wires · net labels · A4 paper"}
            </div>
          </div>
          <a href={kicadHref} download={kicadFilename}
            className="bs-btn-ghost px-3 py-2 rounded text-[12px] flex items-center gap-2 no-underline"
            title="Download KiCad-compatible .kicad_sch schematic">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path d="M8 2v8m0 0l-3-3m3 3l3-3M3 13h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            KiCad
          </a>
          {schematic?.simulate_url && (
            <a
              href={schematic.simulate_url}
              target="_blank"
              rel="noreferrer"
              className="bs-btn-primary px-4 py-2 rounded text-[13px] flex items-center gap-2 no-underline"
              title="Open the circuit running live in Falstad — animated current flow, LEDs light up by current"
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <path d="M5 3l8 5-8 5V3z" fill="currentColor"/>
              </svg>
              Simulate
            </a>
          )}
        </div>
      )}

      {/* BOM download bar */}
      {!readOnly && bom && bom.lines.length > 0 && bomCsvHref && (
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
              className="bs-btn-ghost px-3 py-2 rounded text-[12px] flex items-center gap-2 no-underline"
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
          {cplHref && (
            <a
              href={cplHref}
              download={`${bom.project_name}_CPL.csv`}
              className="bs-btn-ghost px-3 py-2 rounded text-[12px] flex items-center gap-2 no-underline"
              title="Pick-and-place file for SMT assembly"
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
              CPL
            </a>
          )}
        </div>
      )}

      {/* Firmware download bar — Arduino .ino with the actual pin assignments */}
      {!readOnly && firmware?.code && firmwareHref && (
        <div
          className="flex items-center gap-3 px-4 py-2.5 border-t"
          style={{ borderColor: "var(--bs-line-soft)", background: "var(--bs-panel-2)" }}
        >
          <span className="bs-pill" style={{ color: "var(--bs-cyan)" }}>
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: "var(--bs-cyan)" }}
            />
            Firmware
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium truncate" style={{ color: "var(--bs-fg)" }}>
              Starter Arduino sketch · {firmwareFilename}
            </div>
            <div className="font-mono text-[10px] truncate" style={{ color: "var(--bs-fg-dim)" }}>
              {firmware.target_board
                ? `${firmware.target_board}${
                    firmware.framework ? ` · ${firmware.framework}` : ""
                  }`
                : "pin-aware sketch ready to flash"}
            </div>
          </div>
          <a
            href={firmwareHref}
            download={firmwareFilename}
            className="bs-btn-ghost px-3 py-2 rounded text-[12px] flex items-center gap-2 no-underline"
            title="Download the Arduino .ino sketch — also bundled inside the manufacturing zip under firmware/"
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
            main.ino
          </a>
        </div>
      )}

      {/* manufacturing bundle download bar — Gerbers + BOMs + CPL all-in-one */}
      {!readOnly && gerber && gerber.download_url && (
        <div className="flex items-center gap-3 px-4 py-2.5 border-t"
          style={{ borderColor: "var(--bs-line-soft)", background: "var(--bs-panel-2)" }}>
          <span className="bs-pill" style={{ color: "var(--bs-lime)" }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--bs-lime)" }}/>
            JLCPCB-Ready
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium truncate" style={{ color: "var(--bs-fg)" }}>
              Manufacturing bundle · {filename}
            </div>
            <div className="font-mono text-[10px] truncate" style={{ color: "var(--bs-fg-dim)" }}>
              {bundleIncludes.length > 0
                ? `Gerbers · drill · ${bundleIncludes.join(" · ")}`
                : "Gerbers · drill · BOM · JLCPCB BOM · CPL"}
            </div>
          </div>
          <a href={downloadHref} download={filename}
            className="bs-btn-primary px-4 py-2 rounded text-[13px] flex items-center gap-2 no-underline"
            title="One zip with everything JLCPCB needs: Gerbers, drills, BOM, JLCPCB BOM, and CPL pick-and-place">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path d="M8 2v8m0 0l-3-3m3 3l3-3M3 13h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Download bundle
          </a>
        </div>
      )}
    </section>
  );
};

export default ViewerTabs;
