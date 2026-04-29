"""KiCad symbol shape registry.

Each library component maps to a `SymbolShape` containing:
  * the s-expression graphics for the symbol's `_0_1` body sub-symbol,
  * a list of `PinGeom` rows for the `_1_1` pin sub-symbol,
  * a bounding-box width/height for layout spacing.

The graphics try to follow the IEC/IEEE conventions you'd see in a
hand-drawn KiCad schematic: zigzag/IEC-rectangle resistors, parallel-line
capacitors, diode triangles for LEDs/diodes, etc. Microcontrollers and
sensors stay as labelled rectangles (which is what they look like in
KiCad's Device library too).

All coordinates are in millimetres and snapped to the 1.27 mm
connection grid by the writer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.models import LibraryComponent, PinDefinition

GRID_MM = 1.27
PIN_LEN = 2.54


@dataclass(frozen=True)
class PinGeom:
    name: str
    number: str
    x: float
    y: float
    angle: int  # KiCad pin angle: 0=right, 90=up, 180=left, 270=down
    side: str   # 'L', 'R', 'T', 'B' — direction of the wire stub leaving the symbol


@dataclass
class SymbolShape:
    graphics: list[str]
    pins: list[PinGeom]
    box_w: float
    box_h: float


def _esc(value: str | None) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _stroke(width: float = 0.254) -> str:
    return f"(stroke (width {width}) (type default))"


def _fill_none() -> str:
    return "(fill (type none))"


def _fill_bg() -> str:
    return "(fill (type background))"


def _polyline(points: list[tuple[float, float]], filled: bool = False, width: float = 0.254) -> str:
    pts = " ".join(f"(xy {x:.3f} {y:.3f})" for x, y in points)
    fill = _fill_bg() if filled else _fill_none()
    return f"(polyline (pts {pts}) {_stroke(width)} {fill})"


def _rectangle(x1: float, y1: float, x2: float, y2: float, *, filled_bg: bool = True, width: float = 0.254) -> str:
    fill = _fill_bg() if filled_bg else _fill_none()
    return f"(rectangle (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) {_stroke(width)} {fill})"


def _circle(cx: float, cy: float, r: float, *, filled_bg: bool = False) -> str:
    fill = _fill_bg() if filled_bg else _fill_none()
    return f"(circle (center {cx:.3f} {cy:.3f}) (radius {r:.3f}) {_stroke()} {fill})"


def _arc(start: tuple[float, float], mid: tuple[float, float], end: tuple[float, float]) -> str:
    return (
        f"(arc (start {start[0]:.3f} {start[1]:.3f}) "
        f"(mid {mid[0]:.3f} {mid[1]:.3f}) "
        f"(end {end[0]:.3f} {end[1]:.3f}) {_stroke()} {_fill_none()})"
    )


# ───────────────────────── 2-pin horizontal shapes ─────────────────────────


def _horizontal_2pin_pins(pins: list[PinDefinition]) -> list[PinGeom]:
    """Pin 1 on the left, pin 2 on the right; pin endpoints at ±5.08 mm."""
    if len(pins) < 2:
        pins = list(pins) + [PinDefinition(name="2", kind="passive")] * (2 - len(pins))
    return [
        PinGeom(name=pins[0].name, number="1", x=-5.08, y=0.0, angle=0, side="L"),
        PinGeom(name=pins[1].name, number="2", x=5.08, y=0.0, angle=180, side="R"),
    ]


def _shape_resistor(lib: LibraryComponent) -> SymbolShape:
    # IEC rectangle resistor: thin rectangle aligned horizontally between pins.
    graphics = [_rectangle(-2.286, -0.762, 2.286, 0.762, filled_bg=True)]
    return SymbolShape(graphics=graphics, pins=_horizontal_2pin_pins(lib.pins),
                       box_w=12.0, box_h=4.0)


def _shape_inductor(lib: LibraryComponent) -> SymbolShape:
    # Four humps drawn as half-arcs.
    pts = []
    bumps = 4
    span = 4.0
    step = span / bumps
    x0 = -span / 2
    for i in range(bumps):
        s = (x0 + i * step, 0.0)
        m = (x0 + i * step + step / 2, -1.0)
        e = (x0 + (i + 1) * step, 0.0)
        # We approximate the loop with a polyline through several points to
        # avoid emitting four separate arcs (KiCad accepts arcs but polyline
        # is more compact and shows the same way at small sizes).
        pts.extend([s, m])
    pts.append((span / 2, 0.0))
    graphics = [_polyline(pts, filled=False)]
    return SymbolShape(graphics=graphics, pins=_horizontal_2pin_pins(lib.pins),
                       box_w=12.0, box_h=4.0)


def _shape_diode_body(filled_arrows: bool) -> list[str]:
    """Common diode body: triangle pointing right + cathode bar on the right."""
    triangle = _polyline([(-1.27, 1.27), (-1.27, -1.27), (1.27, 0.0), (-1.27, 1.27)],
                         filled=True)
    cathode = _polyline([(1.27, 1.27), (1.27, -1.27)], width=0.3)
    body: list[str] = [triangle, cathode]
    return body


def _shape_diode(lib: LibraryComponent) -> SymbolShape:
    return SymbolShape(graphics=_shape_diode_body(filled_arrows=False),
                       pins=_horizontal_2pin_pins(lib.pins),
                       box_w=10.0, box_h=4.0)


def _shape_led(lib: LibraryComponent) -> SymbolShape:
    body = _shape_diode_body(filled_arrows=True)
    # Two outward-pointing emission arrows.
    body.append(_polyline([(0.5, 1.6), (1.6, 2.7)]))
    body.append(_polyline([(1.6, 2.7), (1.0, 2.5)]))
    body.append(_polyline([(1.6, 2.7), (1.4, 2.0)]))
    body.append(_polyline([(1.5, 2.4), (2.6, 3.5)]))
    body.append(_polyline([(2.6, 3.5), (2.0, 3.3)]))
    body.append(_polyline([(2.6, 3.5), (2.4, 2.8)]))
    return SymbolShape(graphics=body,
                       pins=_horizontal_2pin_pins(lib.pins),
                       box_w=10.0, box_h=8.0)


def _shape_button(lib: LibraryComponent) -> SymbolShape:
    # Two contact pads on the pin axis + a horizontal actuator bar above.
    body = [
        _circle(-2.286, 0.0, 0.508),
        _circle(2.286, 0.0, 0.508),
        _polyline([(-2.286, 1.524), (2.286, 1.524)], width=0.3),
        _polyline([(0.0, 1.524), (0.0, 2.794)]),
        _polyline([(-0.762, 2.794), (0.762, 2.794)]),
    ]
    return SymbolShape(graphics=body,
                       pins=_horizontal_2pin_pins(lib.pins),
                       box_w=12.0, box_h=6.0)


# ───────────────────────── 2-pin vertical (capacitor) ─────────────────────


def _shape_capacitor(lib: LibraryComponent) -> SymbolShape:
    body = [
        _polyline([(-1.778, 0.508), (1.778, 0.508)], width=0.4),
        _polyline([(-1.778, -0.508), (1.778, -0.508)], width=0.4),
    ]
    pins: list[PinGeom] = []
    if len(lib.pins) >= 1:
        pins.append(PinGeom(name=lib.pins[0].name, number="1", x=0.0, y=2.54,
                            angle=270, side="T"))
    if len(lib.pins) >= 2:
        pins.append(PinGeom(name=lib.pins[1].name, number="2", x=0.0, y=-2.54,
                            angle=90, side="B"))
    return SymbolShape(graphics=body, pins=pins, box_w=6.0, box_h=8.0)


# ───────────────────────── regulator (3-pin) ─────────────────────────


def _shape_regulator3(lib: LibraryComponent) -> SymbolShape:
    w_half = 5.08
    h_half = 3.81
    body = [_rectangle(-w_half, -h_half, w_half, h_half, filled_bg=True)]
    pins: list[PinGeom] = []
    # AMS1117 library order: VIN, GND, VOUT
    if len(lib.pins) >= 3:
        pins.append(PinGeom(name=lib.pins[0].name, number="1",
                            x=-(w_half + PIN_LEN), y=0.0, angle=0, side="L"))
        pins.append(PinGeom(name=lib.pins[1].name, number="2",
                            x=0.0, y=-(h_half + PIN_LEN), angle=90, side="B"))
        pins.append(PinGeom(name=lib.pins[2].name, number="3",
                            x=(w_half + PIN_LEN), y=0.0, angle=180, side="R"))
    else:
        for i, p in enumerate(lib.pins):
            pins.append(PinGeom(name=p.name, number=str(i + 1),
                                x=-(w_half + PIN_LEN), y=(i - len(lib.pins) / 2) * 2.54,
                                angle=0, side="L"))
    return SymbolShape(graphics=body, pins=pins,
                       box_w=2 * w_half + 2 * PIN_LEN + 4.0,
                       box_h=2 * h_half + 2 * PIN_LEN + 4.0)


# ───────────────────────── connectors (right-facing) ─────────────────────────


def _shape_connector_right(lib: LibraryComponent) -> SymbolShape:
    n = len(lib.pins)
    pitch = 2.54
    body_h = max(n * pitch + pitch, 5.08)
    body_w = 5.08
    body = [_rectangle(-body_w, -body_h / 2, 0.0, body_h / 2, filled_bg=True)]
    pins: list[PinGeom] = []
    top = (n - 1) * pitch / 2
    for i, p in enumerate(lib.pins):
        y = top - i * pitch
        pins.append(PinGeom(name=p.name, number=str(i + 1),
                            x=PIN_LEN, y=y, angle=180, side="R"))
    return SymbolShape(graphics=body, pins=pins,
                       box_w=body_w + 2 * PIN_LEN + 6.0,
                       box_h=body_h + 4.0)


# ───────────────────────── ICs (dual-inline labelled rectangle) ─────────────


def _shape_ic(lib: LibraryComponent) -> SymbolShape:
    n = len(lib.pins)
    pitch = 2.54
    rows = (n + 1) // 2
    body_h = max(rows * pitch + pitch, 5.08)
    body_w = 7.62
    body = [_rectangle(-body_w, -body_h / 2, body_w, body_h / 2, filled_bg=True)]
    pins: list[PinGeom] = []
    top = (rows - 1) * pitch / 2
    for i, p in enumerate(lib.pins):
        row = i // 2
        side_left = (i % 2 == 0)
        y = top - row * pitch
        if side_left:
            pins.append(PinGeom(name=p.name, number=str(i + 1),
                                x=-(body_w + PIN_LEN), y=y, angle=0, side="L"))
        else:
            pins.append(PinGeom(name=p.name, number=str(i + 1),
                                x=(body_w + PIN_LEN), y=y, angle=180, side="R"))
    return SymbolShape(graphics=body, pins=pins,
                       box_w=2 * (body_w + PIN_LEN) + 6.0,
                       box_h=body_h + 4.0)


# ───────────────────────── dispatch ─────────────────────────


_BUILDERS: dict[str, Callable[[LibraryComponent], SymbolShape]] = {
    "Resistor": _shape_resistor,
    "Capacitor": _shape_capacitor,
    "Inductor": _shape_inductor,
    "LED": _shape_led,
    "Diode": _shape_diode,
    "Push Button": _shape_button,
    "AMS1117": _shape_regulator3,
    "USB-C Input": _shape_connector_right,
    "Pin Header": _shape_connector_right,
    "JST-XH": _shape_connector_right,
}


def shape_for(lib: LibraryComponent) -> SymbolShape:
    return _BUILDERS.get(lib.key, _shape_ic)(lib)
