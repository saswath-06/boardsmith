from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class StageStatus(str, Enum):
    running = "running"
    complete = "complete"
    error = "error"


class PipelineEvent(BaseModel):
    stage: str
    status: StageStatus
    data: Any = None
    message: str


class JobRequest(BaseModel):
    description: str = Field(..., min_length=3)


class JobCreateResponse(BaseModel):
    job_id: str


class ArtifactInfo(BaseModel):
    name: str
    url: str


class JobSnapshot(BaseModel):
    job_id: str
    complete: bool
    events: list[PipelineEvent]
    artifacts: list[ArtifactInfo]
    parent_job_id: str | None = None
    instruction: str | None = None
    revision: int = 0
    description: str = ""
    created_at: float = 0.0


class JobSummary(BaseModel):
    """Lightweight row for the sidebar list (`GET /api/jobs`)."""

    job_id: str
    description: str
    instruction: str | None = None
    parent_job_id: str | None = None
    revision: int = 0
    complete: bool = False
    components: int = 0
    nets: int = 0
    created_at: float = 0.0


class LineageEntry(BaseModel):
    """One node in a refinement chain (root → leaf)."""

    job_id: str
    revision: int
    title: str
    complete: bool


class RefineRequest(BaseModel):
    instruction: str = Field(..., min_length=3)


class BomLine(BaseModel):
    """One row of the bill of materials — one or more identical parts."""

    line_id: int
    references: list[str]
    quantity: int
    type: str
    value: str | None = None
    description: str
    package: str | None = None
    category: str = ""
    notes: str | None = None
    # JLCPCB / LCSC enrichment (populated by app.lcsc when a match exists).
    lcsc_part_number: str | None = None
    manufacturer_pn: str | None = None
    manufacturer: str | None = None
    # USD pricing (best-effort hand-curated; null when no match).
    unit_price_usd: float | None = None
    extended_price_usd: float | None = None


class CostEstimate(BaseModel):
    """All-in build cost for one quantity tier (mirror of cost.CostEstimate)."""

    qty: int
    parts: float = 0.0
    pcb_fab: float = 0.0
    smt_setup: float = 0.0
    smt_placement: float = 0.0
    stencil: float = 0.0
    shipping: float = 0.0
    total: float = 0.0
    smt_joints: int = 0


class BomData(BaseModel):
    project_name: str
    lines: list[BomLine]
    total_unique: int
    total_quantity: int
    # Build cost rollup (sum of extended_price_usd over all priced lines).
    total_unit_cost_usd: float = 0.0
    priced_line_count: int = 0
    currency: str = "USD"
    # SMT joint count (sum of pads on assembled SMT components) — feeds
    # the per-joint placement fee in the JLCPCB estimator.
    smt_joints: int = 0
    # All-in cost tiers (5 / 30 / 100 boards). Each entry is a complete
    # breakdown the frontend can render without recomputing.
    cost_estimates: list[CostEstimate] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)


class PinDefinition(BaseModel):
    name: str
    kind: str = "passive"


class LibraryComponent(BaseModel):
    key: str
    display_name: str
    category: str
    footprint: str
    width: float
    height: float
    pins: list[PinDefinition]
    color: str = "#334155"


class ComponentInstance(BaseModel):
    ref: str
    type: str
    label: str = ""
    value: str | None = None
    notes: str | None = None

    @field_validator("label", mode="before")
    @classmethod
    def _coerce_label(cls, v: Any) -> str:
        return "" if v is None else str(v)


class NetConnection(BaseModel):
    ref: str
    pin: str


class Net(BaseModel):
    name: str
    # Was a strict Literal — relaxed because Gemini emits arbitrary kinds like
    # "i2c", "data", "bus", which would explode Pydantic and crash the parse.
    # The validator below normalizes anything off-list into "signal".
    kind: str = "signal"
    connections: list[NetConnection]

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, v: Any) -> str:
        if v is None:
            return "signal"
        s = str(v).strip().lower()
        if s in {"power", "pwr", "vcc", "vdd"}:
            return "power"
        if s in {"ground", "gnd", "vss"}:
            return "ground"
        return "signal"


class CircuitDesign(BaseModel):
    project_name: str = "Boardsmith_Demo"
    description: str = ""
    components: list[ComponentInstance]
    nets: list[Net]
    warnings: list[str] = Field(default_factory=list)
    # Human-readable bullet points explaining the design choices the LLM
    # made — MCU pick, power chain, off-board breakouts, etc. Surfaced as
    # its own "Design notes" panel in the UI, separate from warnings.
    design_decisions: list[str] = Field(default_factory=list)


class Pad(BaseModel):
    ref: str
    pin: str
    net: str | None = None
    x: float
    y: float
    w: float = 1.4
    h: float = 1.4


class LayoutComponent(BaseModel):
    ref: str
    type: str
    label: str
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0
    color: str = "#334155"
    pads: list[Pad]


class Segment(BaseModel):
    net: str
    points: list[tuple[float, float]]
    routed: bool = True


class RatsnestLine(BaseModel):
    net: str
    from_point: tuple[float, float]
    to_point: tuple[float, float]


class BoardLayout(BaseModel):
    width: float
    height: float
    components: list[LayoutComponent]
    nets: list[Net]
    ratsnest: list[RatsnestLine]
    traces: list[Segment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
