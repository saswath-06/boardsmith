from __future__ import annotations

import math

from app.component_library import get_component
from app.models import BoardLayout, CircuitDesign, LayoutComponent, Pad, RatsnestLine, Segment
from app.router import lee_route

GRID_MM = 2.0


def _pad_positions(cx: float, cy: float, width: float, height: float, pins: list[str]) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    if len(pins) <= 2:
        if len(pins) >= 1:
            positions[pins[0]] = (cx - width / 2 - 1.2, cy)
        if len(pins) >= 2:
            positions[pins[1]] = (cx + width / 2 + 1.2, cy)
        return positions

    left = pins[::2]
    right = pins[1::2]
    for idx, pin in enumerate(left):
        y = cy - height / 2 + (idx + 1) * height / (len(left) + 1)
        positions[pin] = (cx - width / 2 - 1.2, y)
    for idx, pin in enumerate(right):
        y = cy - height / 2 + (idx + 1) * height / (len(right) + 1)
        positions[pin] = (cx + width / 2 + 1.2, y)
    return positions


def _seed_position(category: str, index: int, board_w: float = 120.0, board_h: float = 85.0) -> tuple[float, float]:
    """Category-based seed positions, scaled relative to the board.

    Seeds were originally hardcoded for a 120×85mm board, which crammed
    everything into one corner of larger boards. Now expressed as fractions
    of board dimensions so they spread across whatever size we picked.
    """
    cx, cy = board_w / 2, board_h / 2
    margin = max(12.0, board_w * 0.08)

    if category == "power":
        return (margin + index * (board_w * 0.10), margin)
    if category == "microcontroller":
        return (cx, cy - board_h * 0.05 + index * (board_h * 0.18))
    if category == "sensor":
        return (board_w - margin - 13.0, margin + index * (board_h * 0.22))
    if category == "connector":
        return (margin, cy + index * (board_h * 0.14))
    if category == "passive":
        cols = max(4, int(board_w / 18))
        return (cx - board_w * 0.15 + (index % cols) * (board_w / (cols + 1)),
                board_h - margin - (index // cols) * 14.0)
    if category == "discrete":
        cols = max(3, int(board_w / 22))
        return (board_w - margin - 5.0 - (index % cols) * (board_w / (cols + 2)),
                board_h - margin - (index // cols) * 10.0)
    return (cx + (index % 3) * 18.0, cy + (index // 3) * 16.0)


def _force_place(design: CircuitDesign, board_w: float, board_h: float) -> dict[str, tuple[float, float]]:
    """Spring force-directed placement over 80 iterations.

    Seeds from category-based positions for fast, readable convergence.
    Repulsion keeps components apart; attraction pulls net-connected pairs
    together; boundary clamping keeps everything inside the board margins.
    """
    # ── Seed positions ────────────────────────────────────────────────────────
    category_counts: dict[str, int] = {}
    pos: dict[str, list[float]] = {}
    min_sep: dict[str, float] = {}

    for comp in design.components:
        lib = get_component(comp.type)
        cat = lib.category
        idx = category_counts.get(cat, 0)
        category_counts[cat] = idx + 1
        sx, sy = _seed_position(cat, idx)
        # Tiny deterministic jitter breaks exact symmetry without randomness
        jx = (hash(comp.ref) % 9) - 4.0
        jy = (hash(comp.ref + "_y") % 9) - 4.0
        pos[comp.ref] = [sx + jx * 0.5, sy + jy * 0.5]
        min_sep[comp.ref] = max(lib.width, lib.height) / 2.0 + 2.5

    # ── Net adjacency pairs for attraction ───────────────────────────────────
    net_pairs: list[tuple[str, str]] = []
    for net in design.nets:
        refs = list({conn.ref for conn in net.connections})
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                net_pairs.append((refs[i], refs[j]))

    refs = [c.ref for c in design.components]
    MARGIN = 12.0
    K_REPEL = 600.0
    K_ATTRACT = 0.03
    DAMPING = 0.75
    MAX_STEP = 6.0

    # Pre-compute component sizes for overlap avoidance
    comp_sizes: dict[str, tuple[float, float]] = {}
    for comp in design.components:
        lib = get_component(comp.type)
        comp_sizes[comp.ref] = (lib.width, lib.height)

    # More components = needs more iterations to settle; cap so very large
    # boards don't take forever.
    iterations = min(400, 120 + len(refs) * 6)
    for _iter in range(iterations):
        forces: dict[str, list[float]] = {r: [0.0, 0.0] for r in refs}

        # Repulsion — every pair pushes apart ∝ 1/d²
        # With hard overlap penalty: if bounding boxes overlap, push apart strongly
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                ri, rj = refs[i], refs[j]
                dx = pos[rj][0] - pos[ri][0]
                dy = pos[rj][1] - pos[ri][1]
                dist = math.sqrt(dx * dx + dy * dy) + 0.01

                # Minimum distance based on component sizes
                wi, hi = comp_sizes[ri]
                wj, hj = comp_sizes[rj]
                min_dist = (max(wi, hi) + max(wj, hj)) / 2.0 + 4.0

                if dist < min_dist:
                    # Hard push — overlapping components get a huge force
                    f = K_REPEL * 4.0 / (dist * dist)
                else:
                    f = K_REPEL / (dist * dist)

                fx, fy = f * dx / dist, f * dy / dist
                forces[ri][0] -= fx
                forces[ri][1] -= fy
                forces[rj][0] += fx
                forces[rj][1] += fy

        # Attraction — net-connected components pull toward each other ∝ d
        # But only if they're already far enough apart (don't attract into overlap)
        for ra, rb in net_pairs:
            if ra not in pos or rb not in pos:
                continue
            dx = pos[rb][0] - pos[ra][0]
            dy = pos[rb][1] - pos[ra][1]
            dist = math.sqrt(dx * dx + dy * dy) + 0.01
            wa, ha = comp_sizes.get(ra, (5, 5))
            wb, hb = comp_sizes.get(rb, (5, 5))
            min_dist = (max(wa, ha) + max(wb, hb)) / 2.0 + 3.0
            if dist > min_dist:
                f = K_ATTRACT * (dist - min_dist)
                fx, fy = f * dx / dist, f * dy / dist
                forces[ra][0] += fx
                forces[ra][1] += fy
                forces[rb][0] -= fx
                forces[rb][1] -= fy

        # Apply forces with step-size clamping and boundary clamping
        for comp in design.components:
            lib = get_component(comp.type)
            half_w = lib.width / 2.0
            half_h = lib.height / 2.0
            fx, fy = forces[comp.ref]
            step = math.sqrt(fx * fx + fy * fy)
            if step > MAX_STEP:
                fx, fy = fx / step * MAX_STEP, fy / step * MAX_STEP
            pos[comp.ref][0] = max(MARGIN + half_w, min(board_w - MARGIN - half_w, pos[comp.ref][0] + fx * DAMPING))
            pos[comp.ref][1] = max(MARGIN + half_h, min(board_h - MARGIN - half_h, pos[comp.ref][1] + fy * DAMPING))

    return {ref: (p[0], p[1]) for ref, p in pos.items()}


def _board_size_for(design: CircuitDesign) -> tuple[float, float]:
    """Pick a board size based on total component area.

    Aims for ~22% component packing density (rest is room for traces, vias,
    silkscreen, and breathing space) at a 1.4:1 aspect ratio (close to a
    typical hobbyist PCB shape). Clamped to 80×60mm minimum and 280×200mm
    maximum so we never produce a postage-stamp board or a serving tray.
    Rounded to nearest 5mm so the footer stat reads cleanly.
    """
    total_area = 0.0
    for comp in design.components:
        try:
            lib = get_component(comp.type)
        except KeyError:
            continue
        total_area += lib.width * lib.height

    target_density = 0.22
    board_area = max(total_area / target_density, 4800.0)
    aspect = 1.4
    h = (board_area / aspect) ** 0.5
    w = aspect * h

    w = max(80.0, min(280.0, w))
    h = max(60.0, min(200.0, h))
    w = round(w / 5.0) * 5.0
    h = round(h / 5.0) * 5.0
    return w, h


def generate_layout(design: CircuitDesign) -> BoardLayout:
    width, height = _board_size_for(design)
    net_lookup = {(conn.ref, conn.pin): net.name for net in design.nets for conn in net.connections}
    components: list[LayoutComponent] = []

    # Compute force-directed positions for all components in one pass
    force_positions = _force_place(design, width, height)

    for component in design.components:
        lib = get_component(component.type)
        cx, cy = force_positions.get(component.ref, (60.0, 42.0))
        pin_names = [pin.name for pin in lib.pins]
        pad_map = _pad_positions(cx, cy, lib.width, lib.height, pin_names)
        pads = [
            Pad(ref=component.ref, pin=pin, net=net_lookup.get((component.ref, pin)), x=px, y=py)
            for pin, (px, py) in pad_map.items()
        ]
        components.append(
            LayoutComponent(
                ref=component.ref,
                type=component.type,
                label=component.label,
                x=cx,
                y=cy,
                width=lib.width,
                height=lib.height,
                color=lib.color,
                pads=pads,
            )
        )

    pad_by_ref_pin = {(pad.ref, pad.pin): pad for comp in components for pad in comp.pads}
    ratsnest: list[RatsnestLine] = []
    for net in design.nets:
        pads = [pad_by_ref_pin.get((conn.ref, conn.pin)) for conn in net.connections]
        real_pads = [pad for pad in pads if pad is not None]
        if len(real_pads) < 2:
            continue
        anchor = real_pads[0]
        for pad in real_pads[1:]:
            ratsnest.append(
                RatsnestLine(
                    net=net.name,
                    from_point=(anchor.x, anchor.y),
                    to_point=(pad.x, pad.y),
                )
            )
    return BoardLayout(width=width, height=height, components=components, nets=design.nets, ratsnest=ratsnest)


def _blocked_cells(layout: BoardLayout) -> set[tuple[int, int]]:
    blocked: set[tuple[int, int]] = set()
    for comp in layout.components:
        min_x = int(max(0, (comp.x - comp.width / 2) / GRID_MM))
        max_x = int(min(layout.width / GRID_MM, (comp.x + comp.width / 2) / GRID_MM))
        min_y = int(max(0, (comp.y - comp.height / 2) / GRID_MM))
        max_y = int(min(layout.height / GRID_MM, (comp.y + comp.height / 2) / GRID_MM))
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                blocked.add((x, y))
    return blocked


def route_layout(layout: BoardLayout) -> BoardLayout:
    grid_w = int(layout.width / GRID_MM) + 1
    grid_h = int(layout.height / GRID_MM) + 1

    # Cells occupied by component bodies — these are hard obstacles that no
    # net can cross. Pads sit just outside component bounding boxes, so they
    # remain reachable.
    component_blocked = _blocked_cells(layout)

    # Net-aware cell ownership: a cell already used by some net N is "blocked"
    # only for routes belonging to a *different* net. Same-net cells are fine
    # to share — they're electrically connected anyway, and reusing copper is
    # exactly what real autorouters do (think ground pours).
    cell_owner: dict[tuple[int, int], str] = {}

    # Sort ratsnest lines shortest-first so quick wins finish before long
    # sprawling routes start eating cells.
    def length(line: RatsnestLine) -> float:
        dx = line.to_point[0] - line.from_point[0]
        dy = line.to_point[1] - line.from_point[1]
        return abs(dx) + abs(dy)

    sorted_rats = sorted(layout.ratsnest, key=length)

    traces: list[Segment] = []
    failed = 0

    for line in sorted_rats:
        start = (round(line.from_point[0] / GRID_MM), round(line.from_point[1] / GRID_MM))
        goal = (round(line.to_point[0] / GRID_MM), round(line.to_point[1] / GRID_MM))
        if start == goal:
            continue

        local_blocked: set[tuple[int, int]] = set(component_blocked)
        for cell, owner in cell_owner.items():
            if owner != line.net:
                local_blocked.add(cell)
        local_blocked.discard(start)
        local_blocked.discard(goal)

        # Search budget scales with grid area so big boards don't choke.
        budget = max(8000, grid_w * grid_h * 4)
        path = lee_route(start, goal, local_blocked, grid_w, grid_h, max_steps=budget)
        if not path:
            failed += 1
            continue

        traces.append(Segment(net=line.net, points=[(x * GRID_MM, y * GRID_MM) for x, y in path], routed=True))
        # Claim the path's interior cells for this net (start/goal are pads,
        # already net-owned implicitly).
        for cell in path[1:-1]:
            cell_owner[cell] = line.net

    warnings = list(layout.warnings)
    if failed:
        warnings.append(f"{failed} connection(s) could not be auto-routed; showing ratsnest fallback.")
    return layout.model_copy(update={"traces": traces, "warnings": warnings})


def layout_svg(layout: BoardLayout) -> str:
    sx = 6
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {layout.width * sx:.0f} {layout.height * sx:.0f}" class="w-full h-full">',
        f'<rect x="0" y="0" width="{layout.width * sx:.0f}" height="{layout.height * sx:.0f}" rx="18" fill="#166534"/>',
    ]
    for line in layout.ratsnest:
        parts.append(
            f'<line x1="{line.from_point[0] * sx:.1f}" y1="{line.from_point[1] * sx:.1f}" '
            f'x2="{line.to_point[0] * sx:.1f}" y2="{line.to_point[1] * sx:.1f}" stroke="#e2e8f0" '
            'stroke-width="1.2" stroke-dasharray="5 5" opacity="0.55"/>'
        )
    for trace in layout.traces:
        pts = " ".join(f"{x * sx:.1f},{y * sx:.1f}" for x, y in trace.points)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="#c0842b" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>')
    for comp in layout.components:
        parts.append(
            f'<rect x="{(comp.x - comp.width / 2) * sx:.1f}" y="{(comp.y - comp.height / 2) * sx:.1f}" '
            f'width="{comp.width * sx:.1f}" height="{comp.height * sx:.1f}" rx="5" fill="{comp.color}" stroke="#f8fafc" stroke-width="1.2"/>'
        )
        parts.append(
            f'<text x="{comp.x * sx:.1f}" y="{comp.y * sx:.1f}" text-anchor="middle" font-family="Inter, Arial" '
            'font-size="10" fill="#fff" font-weight="700">'
            f"{comp.ref}</text>"
        )
        for pad in comp.pads:
            parts.append(f'<circle cx="{pad.x * sx:.1f}" cy="{pad.y * sx:.1f}" r="3.2" fill="#fbbf24" stroke="#78350f"/>')
    parts.append("</svg>")
    return "\n".join(parts)
