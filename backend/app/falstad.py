"""Convert a CircuitDesign into a Falstad circuitjs1 simulation.

Falstad's circuit simulator (https://falstad.com/circuit/) is a browser-based
SPICE-style simulator with animated current flow and LEDs that visually
illuminate proportional to current. Perfect for the "watch it work" demo:
plain English → schematic → click button → live simulation in the browser.

Format reference (from circuitjs1 source):
  Line 1:    $ <flags> <timestep> <speedDelay> <simSpeed> <currentScale>
             <powerScale> <gridSize>
  Elements:  <type> <x1> <y1> <x2> <y2> <flags> <element-specific-params>
  - r  = resistor          (... resistance Ω)
  - c  = capacitor         (... capacitance F, voltage)
  - l  = inductor          (... inductance H, current A)
  - d  = diode             (... model_name)
  - 162 = LED              (... fwdrop  current_unused  max_current)
  - s  = SPST switch       (... position momentary)
  - v  = voltage source    (... waveform freq amplitude offset phase damp)
  - g  = ground            (... earth-symbol coords)
  - w  = wire              (just connects two grid points)

The URL ?ctz=<lz-encoded text> auto-loads the circuit when opened.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

import lzstring  # type: ignore[import-untyped]

from app.component_library import normalize_component_type
from app.models import CircuitDesign, ComponentInstance, Net

GRID = 16  # Falstad snaps everything to a 16px grid


def _snap(v: float) -> int:
    """Round to Falstad's 16px grid."""
    return int(round(v / GRID) * GRID)


# ─────────────────────────────────────────────────────────────────────────
# Net classification
# ─────────────────────────────────────────────────────────────────────────

_POWER_NAMES = {"VCC", "VDD", "VBUS", "+5V", "5V", "+3V3", "+3.3V", "3V3", "3.3V"}
_GND_NAMES = {"GND", "VSS", "0", "GROUND"}


def _is_power_net(net: Net) -> bool:
    return net.kind == "power" or net.name.upper().replace(" ", "") in _POWER_NAMES


def _is_ground_net(net: Net) -> bool:
    return net.kind == "ground" or net.name.upper().replace(" ", "") in _GND_NAMES


def _supply_voltage(design: CircuitDesign) -> float:
    """Pick a sensible simulation supply voltage based on the design.

    Default is 5V — the most common breadboard / USB voltage and the one
    that gives indicator LEDs (~1.8V Vf, ~330Ω limiter) enough headroom
    to be visibly bright in Falstad. Drop to 3.3V only when the design
    explicitly targets a 3V3 microcontroller rail.
    """
    types = {normalize_component_type(c.type) for c in design.components}
    if "JST-XH" in types:
        return 3.7  # LiPo single-cell nominal
    # ESP32 / STM32 default to 3V3; otherwise 5V is the sensible default.
    if "USB-C Input" in types:
        return 5.0
    if {"ESP32", "STM32F103"} & types:
        return 3.3
    return 5.0


# ─────────────────────────────────────────────────────────────────────────
# Value parsing — converts "10k", "100nF", "10uH" into SI base units
# ─────────────────────────────────────────────────────────────────────────

_MULT = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6}


def _parse_si(value: str | None, unit_letter: str | None = None) -> float | None:
    """Parse '10k', '4.7uF', '100nH' to a float in base SI units."""
    if not value:
        return None
    s = str(value).strip().replace("Ω", "").replace("ohm", "").replace(" ", "")
    if unit_letter:
        s = re.sub(rf"{unit_letter}$", "", s, flags=re.IGNORECASE)
    s = s.rstrip("HhFfRr")
    if not s:
        return None
    try:
        if s[-1] in _MULT:
            return float(s[:-1]) * _MULT[s[-1]]
        return float(s)
    except (ValueError, IndexError):
        return None


def _resistance_ohms(value: str | None) -> float:
    return _parse_si(value) or 1000.0


def _capacitance_farads(value: str | None) -> float:
    return _parse_si(value, "F") or 1e-7  # default 100nF


def _inductance_henries(value: str | None) -> float:
    return _parse_si(value, "H") or 1e-3  # default 1mH


# ─────────────────────────────────────────────────────────────────────────
# LED forward voltage + RGB color
# ─────────────────────────────────────────────────────────────────────────

# (forward voltage in V, R, G, B) — values per LEDElm.java in circuitjs1.
_LED_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "red":     (1.8, 1.0, 0.0, 0.0),
    "yellow":  (2.0, 1.0, 1.0, 0.0),
    "amber":   (2.0, 1.0, 0.7, 0.0),
    "orange":  (2.0, 1.0, 0.5, 0.0),
    "green":   (2.1, 0.0, 1.0, 0.0),
    "blue":    (3.1, 0.0, 0.4, 1.0),
    "white":   (3.0, 1.0, 1.0, 1.0),
}


def _led_preset(value: str | None) -> tuple[float, float, float, float]:
    """Look up (Vf, R, G, B) for an LED. Defaults to red if unknown."""
    if value:
        v = value.strip().lower()
        for color, preset in _LED_PRESETS.items():
            if color in v:
                return preset
    return _LED_PRESETS["red"]


# ─────────────────────────────────────────────────────────────────────────
# Pair detection — find LED + current-limiting resistor combinations
# ─────────────────────────────────────────────────────────────────────────

_SIMULATABLE = {
    "Resistor", "Capacitor", "Inductor", "LED", "Diode", "Push Button",
}


@dataclass
class _Branch:
    """A vertical column in the Falstad layout: rail+ → component(s) → rail-."""
    label: str
    components: list[ComponentInstance] = field(default_factory=list)


def _build_branches(
    design: CircuitDesign,
    sim_comps: list[ComponentInstance],
    power_net_name: str | None,
    ground_net_name: str | None,
) -> tuple[list[_Branch], list[str]]:
    """Group simulatable components into vertical branches.

    Strategy:
    1. For each LED, find a Resistor that shares a non-power/non-GND net.
       That resistor is the LED's current limiter — render in series so
       the LED doesn't burn out at full supply voltage.
    2. For each push button, try to attach it to an existing LED+R branch
       it shares a net with. The button goes at the TOP of the branch so
       pressing it completes the path → LED lights up.
    3. Remaining standalone passives become their own parallel branches.
    4. Standalone push buttons / standalone diodes are dropped — they would
       short the supply when closed (button) or clamp it (diode).
    """
    refs_to_nets: dict[str, set[str]] = defaultdict(set)
    for net in design.nets:
        for conn in net.connections:
            refs_to_nets[conn.ref].add(net.name)

    rails = {power_net_name, ground_net_name} - {None}

    used: set[str] = set()
    branches: list[_Branch] = []
    skipped_nonsim: list[str] = []
    leds = [c for c in sim_comps if normalize_component_type(c.type) == "LED"]
    resistors = [c for c in sim_comps if normalize_component_type(c.type) == "Resistor"]
    buttons = [c for c in sim_comps if normalize_component_type(c.type) == "Push Button"]

    # ── Pass 1: pair each LED with a current-limiting resistor ──────────
    led_r_pairs: list[tuple[ComponentInstance, ComponentInstance]] = []
    for led in leds:
        led_signal_nets = {n for n in refs_to_nets.get(led.ref, set()) if n not in rails}
        partner: ComponentInstance | None = None
        for r in resistors:
            if r.ref in used:
                continue
            r_nets = refs_to_nets.get(r.ref, set())
            if led_signal_nets & r_nets:
                partner = r
                break
        # If no shared signal net, fall back to any unused resistor — better
        # than letting the LED burn out at full supply.
        if partner is None:
            for r in resistors:
                if r.ref not in used:
                    partner = r
                    break
        if partner is not None:
            used.add(partner.ref)
            used.add(led.ref)
            led_r_pairs.append((partner, led))

    # ── Pass 2: try to attach each button to an LED+R branch ────────────
    pair_button: dict[int, ComponentInstance] = {}
    for btn in buttons:
        btn_nets = refs_to_nets.get(btn.ref, set())
        for idx, (r, led) in enumerate(led_r_pairs):
            if idx in pair_button:
                continue
            shared = btn_nets & (
                refs_to_nets.get(r.ref, set()) | refs_to_nets.get(led.ref, set())
            )
            if shared - rails:
                pair_button[idx] = btn
                used.add(btn.ref)
                break
        else:
            # No paired LED branch exists — but if there's any LED+R pair
            # at all, attach the button to the first one anyway. That makes
            # "5V + button + R + LED" prompts work even when the LLM's
            # netlist doesn't share a signal net between button and LED.
            if led_r_pairs and not any(
                pair_button.get(i) is btn for i in range(len(led_r_pairs))
            ):
                for idx in range(len(led_r_pairs)):
                    if idx not in pair_button:
                        pair_button[idx] = btn
                        used.add(btn.ref)
                        break

    # ── Build the LED branches (with optional button on top) ────────────
    for idx, (r, led) in enumerate(led_r_pairs):
        comps: list[ComponentInstance] = []
        if idx in pair_button:
            comps.append(pair_button[idx])
        comps.extend([r, led])
        branches.append(_Branch(
            label="+".join(c.ref for c in comps),
            components=comps,
        ))

    # ── Pass 3: remaining simulatable components ────────────────────────
    for c in sim_comps:
        if c.ref in used:
            continue
        norm = normalize_component_type(c.type) or c.type
        # Standalone push button or diode would short / clamp the supply
        # if put in parallel between rails → drop and surface as skipped.
        if norm in {"Push Button", "Diode"}:
            skipped_nonsim.append(f"{c.ref} (floating)")
            continue
        branches.append(_Branch(label=c.ref, components=[c]))
        used.add(c.ref)

    # ── Components Falstad has no model for at all ──────────────────────
    for c in design.components:
        norm = normalize_component_type(c.type) or c.type
        if norm not in _SIMULATABLE:
            skipped_nonsim.append(c.ref)

    return branches, skipped_nonsim


# ─────────────────────────────────────────────────────────────────────────
# Element line emitters — produce one Falstad text line per component
# ─────────────────────────────────────────────────────────────────────────

def _emit_element(
    comp: ComponentInstance,
    x1: int, y1: int, x2: int, y2: int,
) -> str:
    norm = normalize_component_type(comp.type) or comp.type
    if norm == "Resistor":
        return f"r {x1} {y1} {x2} {y2} 0 {_resistance_ohms(comp.value):.6g}"
    if norm == "Capacitor":
        return f"c {x1} {y1} {x2} {y2} 0 {_capacitance_farads(comp.value):.6g} 0 0.001"
    if norm == "Inductor":
        return f"l {x1} {y1} {x2} {y2} 0 {_inductance_henries(comp.value):.6g} 0"
    if norm == "LED":
        _, r, g, b = _led_preset(comp.value)
        # Falstad LED format (LEDElm.java in circuitjs1):
        #   162 x1 y1 x2 y2 flags maxBrightness colorR colorG colorB
        # Forward voltage drop (~2.1V) comes from the built-in "default-led"
        # diode model — there's no fwdrop slot in this line. Putting one
        # there shifts every later field and causes Falstad to use bogus
        # values for maxBrightness/colors → LED renders grey.
        # 5mA threshold is calibrated for indicator LEDs: a 5V/220Ω/LED
        # series chain runs ~13mA → ~115% → fully saturated bright.
        return (
            f"162 {x1} {y1} {x2} {y2} 0 "
            f"0.005 {r:.2f} {g:.2f} {b:.2f}"
        )
    if norm == "Diode":
        return f"d {x1} {y1} {x2} {y2} 0 default"
    if norm == "Push Button":
        # Switch fields: position (0=open, 1=closed), momentary (0/1).
        # Momentary buttons spring open when released — exactly what a
        # tactile pushbutton does on a board.
        return f"s {x1} {y1} {x2} {y2} 0 0 1"
    return f"w {x1} {y1} {x2} {y2} 0"  # safe fallback: a wire


# ─────────────────────────────────────────────────────────────────────────
# Top-level: design → Falstad text → URL
# ─────────────────────────────────────────────────────────────────────────

# Layout grid (Falstad pixel coords).
_LEFT = 96            # x of the voltage source
_TOP_RAIL = 96        # y of the +V rail
_BOT_RAIL = 304       # y of the GND rail
_COL = 96             # spacing between branches


def circuit_to_falstad(design: CircuitDesign) -> str:
    """Render a CircuitDesign as Falstad's circuitjs1 text format."""
    voltage = _supply_voltage(design)

    power_net = next((n for n in design.nets if _is_power_net(n)), None)
    ground_net = next((n for n in design.nets if _is_ground_net(n)), None)

    sim_comps = [
        c for c in design.components
        if (normalize_component_type(c.type) or c.type) in _SIMULATABLE
    ]
    branches, skipped = _build_branches(
        design, sim_comps,
        power_net.name if power_net else None,
        ground_net.name if ground_net else None,
    )

    lines: list[str] = []
    # Header — typical Falstad simulation params (50 sim speed, etc.).
    lines.append("$ 1 0.000005 10.20027730826997 50 5 50 5e-11")

    # Voltage source (left edge) and ground at its negative terminal.
    lines.append(
        f"v {_LEFT} {_BOT_RAIL} {_LEFT} {_TOP_RAIL} 0 0 40 {voltage:.2f} 0 0 0.5"
    )
    lines.append(f"g {_LEFT} {_BOT_RAIL} {_LEFT} {_BOT_RAIL + GRID} 0")

    # Render each branch in its own column to the right of the source.
    branch_count = max(1, len(branches))
    rightmost_x = _LEFT + branch_count * _COL

    rail_height = _BOT_RAIL - _TOP_RAIL
    for i, branch in enumerate(branches, start=1):
        x = _LEFT + i * _COL
        # Connect this column to the rails via wires from the previous column.
        prev_x = _LEFT + (i - 1) * _COL
        lines.append(f"w {prev_x} {_TOP_RAIL} {x} {_TOP_RAIL} 0")
        lines.append(f"w {prev_x} {_BOT_RAIL} {x} {_BOT_RAIL} 0")

        # Spread N series components evenly across the rail height,
        # snapped to Falstad's 16px grid.
        n = max(1, len(branch.components))
        for j, comp in enumerate(branch.components):
            y1 = _TOP_RAIL + (j * rail_height) // n
            y2 = _TOP_RAIL + ((j + 1) * rail_height) // n
            y1 = (y1 // GRID) * GRID
            y2 = (y2 // GRID) * GRID
            if y2 == y1:  # safety: never emit a zero-length element
                y2 = y1 + GRID
            lines.append(_emit_element(comp, x, y1, x, y2))

    # Comment line listing what we couldn't simulate (Falstad ignores `% …`).
    if skipped:
        lines.append(f"% Skipped (no SPICE model): {', '.join(skipped)}")

    return "\n".join(lines) + "\n"


def is_simulatable(design: CircuitDesign) -> tuple[bool, str | None]:
    """Decide whether the design produces a meaningful Falstad simulation.

    Falstad has no models for MCUs/sensors/connectors, so a design composed
    entirely of those parts would produce just a voltage source dangling in
    space — Falstad raises 'Exception in stampCircuit()' on a short and the
    user sees an empty schematic. We avoid that by suppressing the URL.
    """
    sim_comps = [
        c for c in design.components
        if (normalize_component_type(c.type) or c.type) in _SIMULATABLE
    ]
    if not sim_comps:
        return False, (
            "No simulatable components — add a resistor, capacitor, "
            "inductor, LED, diode, or push button."
        )
    return True, None


def falstad_simulate_url(design: CircuitDesign) -> tuple[str | None, str]:
    """Return ``(url, raw text)`` for a CircuitDesign.

    Returns ``(None, text)`` when the design has nothing to simulate — the
    caller should hide the simulate button in that case.
    """
    text = circuit_to_falstad(design)
    ok, _ = is_simulatable(design)
    if not ok:
        return None, text
    compressed = lzstring.LZString().compressToEncodedURIComponent(text)
    url = f"https://www.falstad.com/circuit/circuitjs.html?ctz={compressed}"
    return url, text


def simulation_summary(design: CircuitDesign) -> dict:
    """Lightweight summary surfaced to the frontend alongside the URL."""
    sim_comps = [
        c for c in design.components
        if (normalize_component_type(c.type) or c.type) in _SIMULATABLE
    ]
    skipped = [
        c.ref for c in design.components
        if (normalize_component_type(c.type) or c.type) not in _SIMULATABLE
    ]
    voltage = _supply_voltage(design)
    ok, reason = is_simulatable(design)
    return {
        "supply_voltage": voltage,
        "simulatable_count": len(sim_comps),
        "skipped_refs": skipped,
        "total_components": len(design.components),
        "ok": ok,
        "reason": reason,
    }
