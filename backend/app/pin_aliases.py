"""Map free-form pin names (as emitted by Gemini) onto the canonical pin names
used by `component_library.COMPONENT_LIBRARY`.

The LLM does not know our exact pin-name conventions, so it routinely produces
things like `ANODE` for an LED (we use `A`), `vcc`/`vdd` for `VCC`, `+5V` for
`VBUS`, etc. Without normalization those connections are silently dropped by
downstream consumers (schematic renderer, PCB layout, KiCad writer), leaving
parts visually disconnected.

This module exposes:

* ``normalize_pin(component_type, raw)`` — best-effort canonical pin name.
* ``normalize_design(design)`` — mutates a CircuitDesign in-place and appends
  a warning for any pin that could not be resolved.
"""

from __future__ import annotations

from app.component_library import COMPONENT_LIBRARY, get_component, normalize_component_type
from app.models import CircuitDesign


# ── Aliases that apply to any component type ────────────────────────────────
# Keys are lowercase variants the LLM might emit; values are canonical names.
# The canonical name only "wins" if the component's library actually has a pin
# with that name — otherwise we keep the original string and surface a warning.
UNIVERSAL_ALIASES: dict[str, str] = {
    # power
    "vcc": "VCC", "v+": "VCC", "vdd": "VCC", "v_dd": "VCC",
    "vss": "GND", "v-": "GND", "0v": "GND", "ground": "GND", "gnd": "GND",
    "+3v3": "3V3", "3v3": "3V3", "+3.3v": "3V3", "3.3v": "3V3",
    "+5v": "5V", "5v": "5V",
    # diodes / LEDs
    "anode": "A", "anode+": "A", "+": "A", "plus": "A", "in": "A",
    "cathode": "K", "cathode-": "K", "-": "K", "minus": "K", "out": "K",
    # generic two-terminal
    "p1": "1", "pin1": "1", "t1": "1", "terminal1": "1", "a": "1",
    "p2": "2", "pin2": "2", "t2": "2", "terminal2": "2", "b": "2",
}


# ── Per-component overrides ────────────────────────────────────────────────
# These take precedence over UNIVERSAL_ALIASES for the listed component type.
PER_TYPE_ALIASES: dict[str, dict[str, str]] = {
    "USB-C Input": {
        "vbus": "VBUS", "+5v": "VBUS", "5v": "VBUS", "vcc": "VBUS", "vin": "VBUS",
        "gnd": "GND", "vss": "GND", "0v": "GND", "-": "GND",
        "cc1": "CC1", "cc2": "CC2",
    },
    "AMS1117": {
        "vin": "VIN", "in": "VIN", "input": "VIN", "+5v": "VIN", "5v": "VIN",
        "gnd": "GND", "vss": "GND",
        "vout": "VOUT", "out": "VOUT", "output": "VOUT",
        "+3v3": "VOUT", "3v3": "VOUT", "+3.3v": "VOUT", "3.3v": "VOUT",
    },
    "LED": {"anode": "A", "+": "A", "1": "A", "cathode": "K", "-": "K", "2": "K"},
    "Diode": {"anode": "A", "+": "A", "1": "A", "cathode": "K", "-": "K", "2": "K"},
    "ESP32": {"vcc": "3V3", "vdd": "3V3", "+3v3": "3V3", "3.3v": "3V3", "5v": "EN"},
    "Arduino Nano": {"vcc": "5V", "vdd": "5V", "+5v": "5V"},
    "STM32F103": {"vcc": "3V3", "vdd": "3V3", "+3v3": "3V3"},
    "DHT22": {"vcc": "VCC", "vdd": "VCC", "+5v": "VCC", "5v": "VCC", "data": "DATA", "out": "DATA", "gnd": "GND"},
    "MPU6050": {"vcc": "VCC", "vdd": "VCC", "+3v3": "VCC", "gnd": "GND", "scl": "SCL", "sda": "SDA", "int": "INT"},
    "BMP280": {"vcc": "VCC", "vdd": "VCC", "+3v3": "VCC", "gnd": "GND", "scl": "SCL", "sda": "SDA"},
    "HC-SR04": {"vcc": "VCC", "vdd": "VCC", "+5v": "VCC", "trig": "TRIG", "echo": "ECHO", "gnd": "GND"},
}


def _library_pin_set(component_type: str) -> dict[str, str]:
    """Return {lowercase_name: canonical_name} for the part's library pins."""
    try:
        lib = get_component(component_type)
    except KeyError:
        return {}
    return {p.name.lower(): p.name for p in lib.pins}


def normalize_pin(component_type: str, raw: str) -> str:
    """Best-effort map ``raw`` to a canonical pin name in the part's library.

    Resolution order:

    1. Already a valid library pin (case-insensitive) → return canonical case.
    2. Per-component alias hits a valid library pin → return that.
    3. Universal alias hits a valid library pin → return that.
    4. Otherwise → return ``raw`` unchanged (caller can decide to warn / drop).
    """
    canonical_type = normalize_component_type(component_type) or component_type
    lib_pins = _library_pin_set(canonical_type)
    if not lib_pins:
        return raw

    raw_low = raw.strip().lower()

    if raw_low in lib_pins:
        return lib_pins[raw_low]

    per_type = PER_TYPE_ALIASES.get(canonical_type, {})
    aliased = per_type.get(raw_low)
    if aliased and aliased.lower() in lib_pins:
        return lib_pins[aliased.lower()]

    aliased = UNIVERSAL_ALIASES.get(raw_low)
    if aliased and aliased.lower() in lib_pins:
        return lib_pins[aliased.lower()]

    # Strip non-alnum and retry (handles `+5V`, `pin-1`, `GPIO_5`, etc.)
    stripped = "".join(ch for ch in raw_low if ch.isalnum())
    if stripped and stripped in lib_pins:
        return lib_pins[stripped]
    aliased = UNIVERSAL_ALIASES.get(stripped) or per_type.get(stripped)
    if aliased and aliased.lower() in lib_pins:
        return lib_pins[aliased.lower()]

    return raw


def normalize_design(design: CircuitDesign) -> CircuitDesign:
    """Rewrite every connection's pin to its canonical library name in place.

    Adds a warning for any connection whose pin still doesn't match a known
    library pin after normalization (so the UI/log can surface it without the
    pipeline crashing).
    """
    comp_types: dict[str, str] = {c.ref: c.type for c in design.components}
    unresolved: list[str] = []

    for net in design.nets:
        for conn in net.connections:
            ctype = comp_types.get(conn.ref)
            if not ctype:
                continue
            canonical = normalize_pin(ctype, conn.pin)
            if canonical != conn.pin:
                conn.pin = canonical
            valid_pins = _library_pin_set(ctype)
            if canonical.lower() not in valid_pins:
                unresolved.append(f"{conn.ref}.{conn.pin} (net {net.name})")

    if unresolved:
        msg = "Unresolved pin name(s) — connection may render disconnected: " + ", ".join(unresolved[:8])
        if len(unresolved) > 8:
            msg += f" (+{len(unresolved) - 8} more)"
        if msg not in design.warnings:
            design.warnings.append(msg)

    return design


__all__ = ["normalize_pin", "normalize_design", "UNIVERSAL_ALIASES", "PER_TYPE_ALIASES", "COMPONENT_LIBRARY"]
