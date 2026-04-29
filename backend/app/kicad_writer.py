"""Generate a native KiCad 10 (.kicad_sch) schematic from a `CircuitDesign`.

The writer pairs each library component with a `SymbolShape` from
``app.kicad_symbols`` (resistor zigzag/IEC, diode triangle, capacitor
parallel lines, regulator block, connector right-facing pin row, IC
labelled rectangle …) and lays them out in three columns:

  * power column (USB-C, regulators, decoupling caps)
  * logic column (microcontrollers, sensors)
  * IO column (LEDs, resistors, buttons, headers)

Net connections are drawn as short wire stubs out of each pin, ending in
a `(global_label …)` for power/ground nets and a `(label …)` for signals.
KiCad merges same-named labels on the same sheet, so this is a logically
complete schematic — no dangling rats nest.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.component_library import get_component
from app.kicad_symbols import PinGeom, SymbolShape, shape_for
from app.models import CircuitDesign, LibraryComponent

GRID_MM = 1.27
LABEL_FONT = "(font (size 1.27 1.27))"
PIN_FONT = "(effects (font (size 1.0 1.0)))"


def _snap(v: float) -> float:
    return round(round(v / GRID_MM) * GRID_MM, 6)


def _snap_pt(x: float, y: float) -> tuple[float, float]:
    return (_snap(x), _snap(y))


def _esc(value: str | None) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _safe_symbol_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "Part"


# ──────────────────────── lib_symbols block ────────────────────────────


def _label_offsets(shape: SymbolShape) -> tuple[tuple[float, float, int], tuple[float, float, int]]:
    """Return ((ref_dx, ref_dy, ref_angle), (val_dx, val_dy, val_angle))
    relative to the symbol centre. Lateral for shapes with top/bottom
    pins (so labels don't collide with vertical wire stubs); above/below
    for everything else."""
    has_vertical = any(p.angle in (90, 270) for p in shape.pins)
    if has_vertical:
        dx = _snap(shape.box_w / 2 + 2.54)
        return ((dx, 0.0, 0), (-dx, 0.0, 0))
    dy = _snap(shape.box_h / 2 + 1.524)
    return ((0.0, -dy, 0), (0.0, dy, 0))


def _emit_lib_symbol(lib: LibraryComponent) -> tuple[str, SymbolShape]:
    """Return (s-expression text, shape) for a `lib_symbols` entry."""
    safe = _safe_symbol_name(lib.key)
    name = f"Boardsmith:{safe}"
    shape = shape_for(lib)
    (ref_dx, ref_dy, ref_a), (val_dx, val_dy, val_a) = _label_offsets(shape)
    # 2-pin passives convey meaning through their shape, not pin numbers.
    # ICs/connectors/regulators should show pin names so the user can read
    # them inside the body box.
    is_simple_2pin = len(shape.pins) == 2 and lib.category in {"passive", "discrete"}
    pin_numbers_line = "\t(pin_numbers (hide yes))\n" if is_simple_2pin else ""
    pin_names_hide = " (hide yes)" if is_simple_2pin else ""

    parts: list[str] = [
        f'(symbol "{name}"',
        f"{pin_numbers_line}\t(pin_names (offset 0.762){pin_names_hide})",
        "\t(exclude_from_sim no) (in_bom yes) (on_board yes)",
        f'\t(property "Reference" "U" (at {ref_dx:.2f} {ref_dy:.2f} {ref_a}) '
        f"(effects (font (size 1.27 1.27))))",
        f'\t(property "Value" "{_esc(lib.display_name)}" (at {val_dx:.2f} {val_dy:.2f} {val_a}) '
        f"(effects (font (size 1.27 1.27))))",
        f'\t(property "Footprint" "{_esc(lib.footprint)}" (at 0 0 0) '
        f"(effects (font (size 1.27 1.27)) (hide yes)))",
        # Graphics — common to all units, body style 1.
        f'\t(symbol "{safe}_0_1"',
    ]
    for g in shape.graphics:
        parts.append(f"\t\t{g}")
    parts.append("\t)")

    # Pins — unit 1, body style 1.
    parts.append(f'\t(symbol "{safe}_1_1"')
    for pin in shape.pins:
        x = _snap(pin.x)
        y = _snap(pin.y)
        parts.append(
            f'\t\t(pin passive line (at {x:.2f} {y:.2f} {pin.angle}) '
            f'(length 2.54) (name "{_esc(pin.name)}" {PIN_FONT}) '
            f'(number "{pin.number}" {PIN_FONT}))'
        )
    parts.append("\t)")

    parts.append(")")
    return "\n".join(parts), shape


# ──────────────────────── component layout ────────────────────────────


_COLUMN_FOR_CATEGORY: dict[str, str] = {
    "power": "power",
    "microcontroller": "logic",
    "sensor": "logic",
    "passive": "io",
    "discrete": "io",
    "connector": "io",
}

_COLUMN_X: dict[str, float] = {
    "power": 60.96,
    "logic": 152.4,
    "io": 233.68,
}

_COLUMN_ORDER = ("power", "logic", "io")
_TOP_Y = 38.1
_GUTTER = 7.62
# Wire stub length + net label clearance, used when the body alone
# under-counts a part's true on-page footprint (e.g. capacitor with
# top/bottom pins, regulator with bottom GND pin).
_STUB_OUT = 5.08
_LABEL_PAD = 2.54


def _vertical_footprint(shape: SymbolShape) -> tuple[float, float]:
    """Return (top_extent, bot_extent) — distance above/below the symbol
    centre that the symbol occupies on the page once stubs and labels are
    drawn. ``top_extent`` is in the file ``-Y`` direction (visually up on
    screen, since KiCad's screen Y points down)."""
    body_half = shape.box_h / 2
    top_ext = body_half + _LABEL_PAD
    bot_ext = body_half + _LABEL_PAD
    for p in shape.pins:
        # Pin angle is the direction from pin tip → body.
        # angle 90  → body is in +Y from tip → tip is at negative file y, stub goes further -Y
        # angle 270 → body is in -Y from tip → tip is at positive file y, stub goes further +Y
        if p.angle == 90:
            top_ext = max(top_ext, abs(p.y) + _STUB_OUT + _LABEL_PAD)
        elif p.angle == 270:
            bot_ext = max(bot_ext, abs(p.y) + _STUB_OUT + _LABEL_PAD)
    return top_ext, bot_ext


def _is_decoupling(component) -> bool:
    """Caps tagged as decoupling/bypass belong with the power column."""
    blob = " ".join(filter(None, [
        component.label or "",
        component.notes or "",
        str(component.value) if component.value else "",
    ])).lower()
    return any(k in blob for k in ("decoupl", "bypass", "filter cap"))


def _columnize(design: CircuitDesign) -> dict[str, list[str]]:
    """Group component refs into power/logic/io columns, preserving order."""
    cols: dict[str, list[str]] = {c: [] for c in _COLUMN_ORDER}
    for c in design.components:
        try:
            lib = get_component(c.type)
            cat = lib.category
        except KeyError:
            cat = "discrete"
        col = _COLUMN_FOR_CATEGORY.get(cat, "io")
        # Caps wired only to power/ground rails count as decoupling and stay
        # with the regulator/USB-C in the power column.
        if cat == "passive" and lib.key == "Capacitor":
            connected_nets = {
                n.kind for n in design.nets
                for conn in n.connections
                if conn.ref == c.ref
            }
            only_power = connected_nets and connected_nets.issubset({"power", "ground"})
            if _is_decoupling(c) or only_power:
                col = "power"
        cols[col].append(c.ref)
    return cols


def _place_components(design: CircuitDesign, shapes: dict[str, SymbolShape]) -> dict[str, tuple[float, float]]:
    """Assign every component an (x, y) center; columns stack top-down with
    a footprint that includes wire stubs and net labels above/below."""
    columns = _columnize(design)
    positions: dict[str, tuple[float, float]] = {}
    for col_name in _COLUMN_ORDER:
        x = _COLUMN_X[col_name]
        y = _TOP_Y
        for ref in columns[col_name]:
            shape = shapes[ref]
            top_ext, bot_ext = _vertical_footprint(shape)
            cy = y + top_ext
            positions[ref] = _snap_pt(x, cy)
            y = cy + bot_ext + _GUTTER
    return positions


# ──────────────────────── wire / label emission ────────────────────────────


def _label_orientation(side: str) -> tuple[int, str]:
    """Return (rotation_angle, justify) for a label drawn at the stub end."""
    if side == "L":
        return 180, "right"
    if side == "R":
        return 0, "left"
    if side == "T":
        return 90, "left"
    return 270, "left"


def _stub_endpoint(pin: PinGeom, comp_x: float, comp_y: float) -> tuple[float, float]:
    """Where a 5.08 mm wire stub off this pin should terminate."""
    # The pin's tip in symbol-local coords is at (pin.x, pin.y) but extends
    # outward by `length` (we use 2.54 in the lib_symbol). Stub then runs
    # another ~5.08 mm further outward to reach the label.
    OUT = 5.08
    px, py = pin.x, pin.y
    if pin.side == "L":
        return _snap_pt(comp_x + px - OUT, comp_y + py)
    if pin.side == "R":
        return _snap_pt(comp_x + px + OUT, comp_y + py)
    if pin.side == "T":
        return _snap_pt(comp_x + px, comp_y + py + OUT)
    return _snap_pt(comp_x + px, comp_y + py - OUT)


def _pin_endpoint(pin: PinGeom, comp_x: float, comp_y: float) -> tuple[float, float]:
    """The actual electrical pin tip (where wire starts)."""
    return _snap_pt(comp_x + pin.x, comp_y + pin.y)


# ──────────────────────── main writer ────────────────────────


def write_kicad_schematic(
    design: CircuitDesign,
    output_path: Path,
    project_name: str | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    used_types: list[str] = []
    for component in design.components:
        if component.type not in used_types:
            used_types.append(component.type)

    root_uuid = str(uuid.uuid4())
    proj = _safe_symbol_name(project_name or design.project_name or "Boardsmith")

    text: list[str] = [
        "(kicad_sch",
        "\t(version 20260306)",
        '\t(generator "Boardsmith")',
        '\t(generator_version "10.0")',
        f'\t(uuid "{root_uuid}")',
        '\t(paper "A4")',
        "\t(lib_symbols",
    ]

    # Build lib_symbols and remember each type's shape (so placements can
    # find pin geometry without rebuilding the symbol).
    type_shapes: dict[str, SymbolShape] = {}
    for component_type in used_types:
        lib = get_component(component_type)
        body, shape = _emit_lib_symbol(lib)
        type_shapes[component_type] = shape
        text.append("\t\t" + body.replace("\n", "\n\t\t"))
    text.append("\t)")

    # Map each ref → its shape, then place components in three columns.
    ref_shape: dict[str, SymbolShape] = {
        c.ref: type_shapes[c.type] for c in design.components
    }
    positions = _place_components(design, ref_shape)

    net_kind: dict[str, str] = {net.name: net.kind for net in design.nets}
    net_for_pin: dict[tuple[str, str], str] = {}
    for net in design.nets:
        for conn in net.connections:
            net_for_pin[(conn.ref, conn.pin)] = net.name

    # ── symbol placements ────────────────────────────────────────────
    for component in design.components:
        lib = get_component(component.type)
        safe = _safe_symbol_name(lib.key)
        symbol_name = f"Boardsmith:{safe}"
        x, y = positions[component.ref]
        sym_uuid = str(uuid.uuid4())
        shape = ref_shape[component.ref]
        (ref_dx, ref_dy, ref_a), (val_dx, val_dy, val_a) = _label_offsets(shape)
        ref_x = _snap(x + ref_dx)
        ref_y = _snap(y + ref_dy)
        val_x = _snap(x + val_dx)
        val_y = _snap(y + val_dy)

        text.extend(
            [
                "\t(symbol",
                f'\t\t(lib_id "{symbol_name}")',
                f"\t\t(at {x:.2f} {y:.2f} 0)",
                "\t\t(unit 1)",
                "\t\t(exclude_from_sim no)",
                "\t\t(in_bom yes)",
                "\t\t(on_board yes)",
                "\t\t(dnp no)",
                f'\t\t(uuid "{sym_uuid}")',
                f'\t\t(property "Reference" "{_esc(component.ref)}" '
                f"(at {ref_x:.2f} {ref_y:.2f} {ref_a}) "
                f"(effects (font (size 1.524 1.524) (bold yes))))",
                f'\t\t(property "Value" "{_esc(component.value or component.label or lib.display_name)}" '
                f"(at {val_x:.2f} {val_y:.2f} {val_a}) "
                f"(effects (font (size 1.27 1.27))))",
                f'\t\t(property "Footprint" "{_esc(lib.footprint)}" '
                f"(at {x:.2f} {y:.2f} 0) "
                f"(effects (font (size 1.27 1.27)) (hide yes)))",
            ]
        )
        for pin in shape.pins:
            text.extend(
                [
                    f'\t\t(pin "{pin.number}"',
                    f'\t\t\t(uuid "{uuid.uuid4()}")',
                    "\t\t)",
                ]
            )
        text.extend(
            [
                "\t\t(instances",
                f'\t\t\t(project "{_esc(proj)}"',
                f'\t\t\t\t(path "/{root_uuid}"',
                f'\t\t\t\t\t(reference "{_esc(component.ref)}")',
                "\t\t\t\t\t(unit 1)",
                "\t\t\t\t)",
                "\t\t\t)",
                "\t\t)",
                "\t)",
            ]
        )

    # ── wire stubs + labels for connected pins ────────────────────────
    for component in design.components:
        shape = ref_shape[component.ref]
        comp_x, comp_y = positions[component.ref]
        for pin in shape.pins:
            net_name = net_for_pin.get((component.ref, pin.name))
            if not net_name:
                continue
            sx, sy = _pin_endpoint(pin, comp_x, comp_y)
            ex, ey = _stub_endpoint(pin, comp_x, comp_y)
            text.extend(
                [
                    "\t(wire",
                    f"\t\t(pts (xy {sx:.2f} {sy:.2f}) (xy {ex:.2f} {ey:.2f}))",
                    "\t\t(stroke (width 0) (type default))",
                    f'\t\t(uuid "{uuid.uuid4()}")',
                    "\t)",
                ]
            )
            angle, justify = _label_orientation(pin.side)
            kind = str(net_kind.get(net_name, "signal")).lower()
            tag = "global_label" if kind in {"power", "ground"} else "label"
            extras = "\n\t\t(shape bidirectional)" if tag == "global_label" else ""
            text.extend(
                [
                    f'\t({tag} "{_esc(net_name)}"' + extras,
                    f"\t\t(at {ex:.2f} {ey:.2f} {angle})",
                    f"\t\t(effects {LABEL_FONT} (justify {justify} bottom))",
                    f'\t\t(uuid "{uuid.uuid4()}")',
                    "\t)",
                ]
            )

    text.extend(
        [
            "\t(sheet_instances",
            '\t\t(path "/" (page "1"))',
            "\t)",
            "\t(embedded_fonts no)",
            ")",
            "",
        ]
    )

    output_path.write_text("\n".join(text), encoding="utf-8")
    return output_path
