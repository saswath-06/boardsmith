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
