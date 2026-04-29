from __future__ import annotations

import html
from pathlib import Path

from app.component_library import get_component
from app.models import CircuitDesign


# Symbol shapes for different categories
CATEGORY_SHAPES = {
    "passive": "two_pin",
    "discrete": "two_pin",
    "power": "ic",
    "microcontroller": "ic",
    "sensor": "ic",
    "connector": "ic",
}


def _place_components(design: CircuitDesign) -> dict[str, dict]:
    """Compute positions for components in a schematic-like layout.
    
    MCUs in the center, power on the left, sensors/peripherals on the right,
    passives below.
    """
    placements: dict[str, dict] = {}

    categories: dict[str, list] = {}
    for comp in design.components:
        lib = get_component(comp.type)
        cat = lib.category
        categories.setdefault(cat, []).append(comp)

    # Layout regions (x, y starting positions)
    col_x = {"power": 100, "connector": 100, "microcontroller": 380, "sensor": 660, "passive": 280, "discrete": 540}
    col_y_start = {"power": 100, "connector": 300, "microcontroller": 80, "sensor": 100, "passive": 450, "discrete": 450}

    for cat, comps in categories.items():
        base_x = col_x.get(cat, 400)
        base_y = col_y_start.get(cat, 200)
        spacing_y = 120 if cat in ("microcontroller", "sensor") else 90

        for idx, comp in enumerate(comps):
            lib = get_component(comp.type)
            pin_names = [p.name for p in lib.pins]
            shape = CATEGORY_SHAPES.get(cat, "ic")

            if shape == "two_pin":
                w, h = 80, 30
            else:
                n_pins = len(pin_names)
                w = 120
                h = max(60, n_pins * 18 + 20)

            cx = base_x
            cy = base_y + idx * spacing_y

            # Compute pin positions
            pins: dict[str, tuple[float, float]] = {}
            if shape == "two_pin":
                pins[pin_names[0]] = (cx - w / 2 - 25, cy)
                if len(pin_names) > 1:
                    pins[pin_names[1]] = (cx + w / 2 + 25, cy)
            else:
                left_pins = pin_names[::2]
                right_pins = pin_names[1::2]
                for i, pn in enumerate(left_pins):
                    py = cy - h / 2 + (i + 1) * h / (len(left_pins) + 1)
                    pins[pn] = (cx - w / 2 - 25, py)
                for i, pn in enumerate(right_pins):
                    py = cy - h / 2 + (i + 1) * h / (len(right_pins) + 1)
                    pins[pn] = (cx + w / 2 + 25, py)

            placements[comp.ref] = {
                "comp": comp,
                "lib": lib,
                "cx": cx,
                "cy": cy,
                "w": w,
                "h": h,
                "shape": shape,
                "pins": pins,
                "cat": cat,
            }

    return placements


def render_schematic_svg(design: CircuitDesign) -> str:
    """Render a proper circuit schematic SVG with symbols, pins, and net wires."""
    placements = _place_components(design)

    # Compute SVG bounds
    all_x = [p["cx"] for p in placements.values()]
    all_y = [p["cy"] for p in placements.values()]
    if not all_x:
        all_x, all_y = [400], [300]

    margin = 120
    min_x = min(all_x) - margin - 60
    max_x = max(all_x) + margin + 60
    min_y = min(all_y) - margin
    max_y = max(all_y) + margin
    width = max(900, max_x - min_x)
    height = max(600, max_y - min_y)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x:.0f} {min_y:.0f} {width:.0f} {height:.0f}" '
        f'width="100%" height="100%" style="background:#f8fafc; font-family: Inter, ui-sans-serif, system-ui, sans-serif;">',
    ]

    # Draw net wires first (behind components)
    net_colors = {
        "power": "#dc2626",
        "ground": "#1e293b",
        "signal": "#2563eb",
    }
    signal_colors = ["#2563eb", "#7c3aed", "#0891b2", "#16a34a", "#ea580c", "#be185d", "#4f46e5"]

    pin_positions: dict[tuple[str, str], tuple[float, float]] = {}
    for ref, info in placements.items():
        for pin_name, pos in info["pins"].items():
            pin_positions[(ref, pin_name)] = pos

    for net_idx, net in enumerate(design.nets):
        if net.kind == "power":
            color = "#dc2626"
        elif net.kind == "ground":
            color = "#1e293b"
        else:
            color = signal_colors[net_idx % len(signal_colors)]

        # Collect pin endpoints for this net
        endpoints = []
        for conn in net.connections:
            pos = pin_positions.get((conn.ref, conn.pin))
            if pos:
                endpoints.append(pos)

        if len(endpoints) < 2:
            continue

        # Draw orthogonal bus-style wires: vertical bus line, horizontal stubs to each pin
        xs = [p[0] for p in endpoints]
        ys = [p[1] for p in endpoints]
        bus_x = (min(xs) + max(xs)) / 2

        # If pins are mostly on one side, offset the bus
        left_count = sum(1 for x, _ in endpoints if x < bus_x)
        right_count = len(endpoints) - left_count
        if left_count == 0:
            bus_x = min(xs) - 15
        elif right_count == 0:
            bus_x = max(xs) + 15

        bus_y_min = min(ys) - 5
        bus_y_max = max(ys) + 5

        # Vertical bus line
        if bus_y_max - bus_y_min > 2:
            parts.append(
                f'<line x1="{bus_x:.1f}" y1="{bus_y_min:.1f}" x2="{bus_x:.1f}" y2="{bus_y_max:.1f}" '
                f'stroke="{color}" stroke-width="1.5" opacity="0.7"/>'
            )

        # Horizontal stubs from each pin to the bus
        for px, py in endpoints:
            parts.append(
                f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{bus_x:.1f}" y2="{py:.1f}" '
                f'stroke="{color}" stroke-width="1.5" opacity="0.7"/>'
            )
            # Junction dot
            parts.append(f'<circle cx="{bus_x:.1f}" cy="{py:.1f}" r="3" fill="{color}" opacity="0.8"/>')

        # Net label
        label_y = bus_y_min - 8
        parts.append(
            f'<text x="{bus_x:.1f}" y="{label_y:.1f}" text-anchor="middle" '
            f'font-size="11" font-weight="600" fill="{color}">{html.escape(net.name)}</text>'
        )

    # Draw components
    for ref, info in placements.items():
        cx, cy = info["cx"], info["cy"]
        w, h = info["w"], info["h"]
        comp = info["comp"]
        lib = info["lib"]
        shape = info["shape"]
        cat = info["cat"]

        # Component body
        if shape == "two_pin":
            # Draw a resistor/capacitor symbol-like rectangle
            fill = "#ffffff"
            stroke = "#334155"
            parts.append(
                f'<rect x="{cx - w/2:.1f}" y="{cy - h/2:.1f}" width="{w}" height="{h}" '
                f'rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            )
        else:
            # IC-style box
            fill = "#f1f5f9"
            stroke = lib.color or "#334155"
            parts.append(
                f'<rect x="{cx - w/2:.1f}" y="{cy - h/2:.1f}" width="{w}" height="{h}" '
                f'rx="6" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            )
            # Colored top bar
            parts.append(
                f'<rect x="{cx - w/2:.1f}" y="{cy - h/2:.1f}" width="{w}" height="8" '
                f'rx="6" fill="{stroke}" opacity="0.85"/>'
            )
            # Component corners fix (hide rounded top-bottom mismatch)
            parts.append(
                f'<rect x="{cx - w/2:.1f}" y="{cy - h/2 + 5:.1f}" width="{w}" height="3" '
                f'fill="{stroke}" opacity="0.85"/>'
            )

        # Ref and label text
        parts.append(
            f'<text x="{cx:.1f}" y="{cy - 3:.1f}" text-anchor="middle" '
            f'font-size="13" font-weight="700" fill="#0f172a">{html.escape(comp.ref)}</text>'
        )
        name_text = comp.label if len(comp.label) <= 16 else comp.type
        parts.append(
            f'<text x="{cx:.1f}" y="{cy + 13:.1f}" text-anchor="middle" '
            f'font-size="10" fill="#475569">{html.escape(name_text)}</text>'
        )
        if comp.value:
            parts.append(
                f'<text x="{cx:.1f}" y="{cy + 25:.1f}" text-anchor="middle" '
                f'font-size="9" fill="#64748b">{html.escape(comp.value)}</text>'
            )

        # Pin stubs and labels
        for pin_name, (px, py) in info["pins"].items():
            # Stub line from body edge to pin endpoint
            if px < cx:
                body_edge_x = cx - w / 2
            else:
                body_edge_x = cx + w / 2

            parts.append(
                f'<line x1="{body_edge_x:.1f}" y1="{py:.1f}" x2="{px:.1f}" y2="{py:.1f}" '
                f'stroke="#334155" stroke-width="1.5"/>'
            )
            # Pin endpoint circle
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.5" fill="#334155"/>')
            # Pin name
            if px < cx:
                parts.append(
                    f'<text x="{body_edge_x + 4:.1f}" y="{py + 3.5:.1f}" '
                    f'font-size="8" fill="#64748b">{html.escape(pin_name)}</text>'
                )
            else:
                parts.append(
                    f'<text x="{body_edge_x - 4:.1f}" y="{py + 3.5:.1f}" text-anchor="end" '
                    f'font-size="8" fill="#64748b">{html.escape(pin_name)}</text>'
                )

    # Title
    parts.append(
        f'<text x="{min_x + 20:.1f}" y="{min_y + 25:.1f}" '
        f'font-size="16" font-weight="700" fill="#0f172a">Boardsmith Schematic</text>'
    )
    parts.append(
        f'<text x="{min_x + 20:.1f}" y="{min_y + 44:.1f}" '
        f'font-size="11" fill="#64748b">{html.escape(design.description[:100])}</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


def write_schematic_svg(design: CircuitDesign, output_path: Path) -> str:
    svg = render_schematic_svg(design)
    output_path.write_text(svg, encoding="utf-8")
    return svg
