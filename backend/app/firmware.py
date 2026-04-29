"""Auto-generated starter firmware for Boardsmith designs.

Once the parser has a CircuitDesign, we hit Gemini one more time and
ask it to emit a single Arduino .ino sketch that exercises every
peripheral on the board using the *actual* pin assignments from the
nets list. The result is shown in a "Firmware" tab in the UI and
folded into the manufacturing zip as ``firmware/main.ino``, so the
JLCPCB-ready bundle becomes "PCB + flashable code" — not just copper.

If the design has no MCU (a sensor breakout, a passive divider, etc.)
we skip the stage cleanly. If Gemini fails we still emit a minimal
deterministic sketch so the user always has something to flash.
"""
from __future__ import annotations

import os
import re
import traceback
from pathlib import Path
from typing import Any

from app.component_library import normalize_component_type
from app.models import CircuitDesign, ComponentInstance

MODEL = "gemini-2.5-pro"

_DEBUG_DIR = Path(__file__).resolve().parents[1] / "generated" / "_llm_debug"


# Each entry tells Gemini which Arduino board to target and how to spell
# the pin numbers in the generated code. Anything outside this dict is
# not considered an MCU for firmware purposes.
_BOARD_HINTS: dict[str, dict[str, str]] = {
    "ESP32": {
        "board_name": "ESP32 Dev Module",
        "framework": "Arduino-ESP32",
        "pin_hint": (
            "Use raw GPIO numbers as ints (e.g. GPIO4 → 4, GPIO18 → 18). "
            "Available helpers: WiFi.h, analogRead/analogWrite, ledcWrite "
            "for PWM. Serial baud 115200."
        ),
    },
    "Arduino Nano": {
        "board_name": "Arduino Nano (ATmega328P)",
        "framework": "Arduino AVR",
        "pin_hint": (
            "Use D2..D13 for digital pins (just the integer, e.g. D2 → 2) "
            "and A0..A7 for analog inputs. Serial baud 9600."
        ),
    },
    "STM32F103": {
        "board_name": "STM32F103C8 (Blue Pill)",
        "framework": "Arduino-STM32 / STM32duino",
        "pin_hint": (
            "Use Arduino-STM32 pin macros: PA0, PA1, PB6, PB7, PC13, etc. "
            "Built-in LED is PC13 (active low). Serial baud 115200."
        ),
    },
}


def _locate_mcu(design: CircuitDesign) -> ComponentInstance | None:
    """Return the first component whose normalized type is in `_BOARD_HINTS`."""
    for comp in design.components:
        normalized = normalize_component_type(comp.type) or comp.type
        if normalized in _BOARD_HINTS:
            return comp
    return None


def _peripheral_summary(design: CircuitDesign, mcu: ComponentInstance) -> str:
    """Build a compact, human-readable summary of what's wired to the MCU.

    Walks each net, finds connections that touch the MCU, and lists the
    other parts on the same net. Helps Gemini produce code that uses
    the right pin for the right peripheral without having to interpret
    the raw nets array.
    """
    lines: list[str] = []
    for net in design.nets:
        mcu_pins = [c.pin for c in net.connections if c.ref == mcu.ref]
        if not mcu_pins:
            continue
        others = [
            f"{c.ref}.{c.pin}"
            for c in net.connections
            if c.ref != mcu.ref
        ]
        if not others:
            continue
        lines.append(
            f"- Net {net.name} ({net.kind}): {mcu.ref}.{mcu_pins[0]} "
            f"<-> {', '.join(others)}"
        )
    if not lines:
        return "(no MCU-connected nets — generate a minimal blink demo)"
    return "\n".join(lines)


def _system_prompt(mcu_type: str, board: dict[str, str]) -> str:
    return f"""You are Boardsmith's firmware co-pilot.

Generate ONE Arduino-flavored .ino sketch that turns the supplied
CircuitDesign into a working starter program. The sketch must:

Target board: {board['board_name']}
Framework:    {board['framework']}
Pin hints:    {board['pin_hint']}

Structure (in this exact order):
1. A short header comment block: project name, target board, what each
   peripheral does, generated-by-Boardsmith line.
2. #include lines for any libraries the peripherals need (Wire.h for
   I2C sensors, DHT.h for the DHT22, etc.). Skip any include the
   sketch doesn't actually reference.
3. #define / const int blocks for every peripheral pin, taken from the
   net summary. Comment each one with the part it drives.
4. Any global state (sensor objects, debounce timers, last-read times).
5. setup() — Serial.begin, pinMode for every output/input, sensor
   .begin() calls, an "Boot OK" Serial.println.
6. loop() — exercise each peripheral:
   - LEDs: blink at 1 Hz (or pulse with PWM if the user said "fade")
   - Buttons: read with 30 ms debounce; on press, toggle a status LED
     and Serial.println the event
   - I2C / one-wire sensors (DHT22, BMP280, MPU6050): read every 30
     seconds, Serial.println every value with a label
   - HC-SR04: trigger and measure echo; print distance in cm
   - Pin Header / JST-XH (off-board breakouts): drive the control
     line LOW/HIGH on a 5 s schedule and add a comment
     "// Wire your <whatever> driver to header J<n>"
7. Keep loop() non-blocking — use millis() schedulers, not delay() in
   the main path (a small delay(20) inside the debounce path is OK).

Hard rules:
- Output the raw .ino text only. Do NOT wrap in markdown / code fences.
- No prose before or after the code.
- Use the actual pins from the net summary. If a peripheral isn't
  on a named MCU pin, fall back to a sensible default and comment why.
- Do not invent peripherals that aren't in the design.
- Keep the sketch under ~150 lines. Concise > comprehensive.

The user message contains:
- a peripheral summary (one bullet per net touching the MCU)
- the full CircuitDesign JSON for reference (use it to disambiguate
  peripheral types when the summary is terse).

This is a {mcu_type} project — generate code that compiles for that
exact board.
"""


def _strip_fences(raw: str) -> str:
    """Defensive cleanup if Gemini ignores 'no markdown' and emits ```cpp ... ```."""
    text = raw.strip()
    fence = re.match(r"^```(?:[a-zA-Z+]+)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip() + "\n"
    return text + ("\n" if not text.endswith("\n") else "")


def _fallback_sketch(
    design: CircuitDesign,
    mcu: ComponentInstance,
    board: dict[str, str],
    reason: str,
) -> str:
    """Deterministic minimal sketch — used when Gemini is unavailable.

    Always lists the design's components by ref so the user can
    immediately see what the board carries even without an LLM call.
    """
    component_lines = "\n".join(
        f" *   {c.ref:6s} {c.type}" + (f"  [{c.value}]" if c.value else "")
        for c in design.components
    )
    return (
        f"/*\n"
        f" * {design.project_name} — Boardsmith starter firmware (fallback)\n"
        f" * Target: {board['board_name']} ({board['framework']})\n"
        f" * Reason for fallback: {reason}\n"
        f" *\n"
        f" * Components on this board:\n"
        f"{component_lines}\n"
        f" *\n"
        f" * This is a minimal blink-only sketch. Re-run generation with\n"
        f" * GEMINI_API_KEY set for a peripheral-aware version.\n"
        f" */\n"
        f"\n"
        f"#ifndef LED_BUILTIN\n"
        f"#define LED_BUILTIN 2  // ESP32 default; STM32 BluePill = PC13\n"
        f"#endif\n"
        f"\n"
        f"void setup() {{\n"
        f"  Serial.begin(115200);\n"
        f"  pinMode(LED_BUILTIN, OUTPUT);\n"
        f"  Serial.println(\"{design.project_name} boot OK\");\n"
        f"}}\n"
        f"\n"
        f"void loop() {{\n"
        f"  digitalWrite(LED_BUILTIN, HIGH);\n"
        f"  delay(500);\n"
        f"  digitalWrite(LED_BUILTIN, LOW);\n"
        f"  delay(500);\n"
        f"}}\n"
    )


def _summary_line(design: CircuitDesign, mcu: ComponentInstance) -> str:
    """One-line description for the firmware tab header."""
    peripheral_count = sum(
        1 for c in design.components if c.ref != mcu.ref
    )
    return (
        f"Starter sketch for {mcu.type} ({mcu.ref}) — "
        f"{peripheral_count} peripheral{'s' if peripheral_count != 1 else ''} wired up."
    )


def generate_starter_firmware(design: CircuitDesign) -> dict[str, Any] | None:
    """Generate an Arduino .ino starter sketch for ``design``.

    Returns ``None`` when the design has no MCU. Otherwise always returns
    a dict with the .ino code — falling back to a deterministic blink
    sketch if Gemini is unavailable or errors out.
    """
    mcu = _locate_mcu(design)
    if mcu is None:
        return None

    mcu_type = normalize_component_type(mcu.type) or mcu.type
    board = _BOARD_HINTS[mcu_type]
    summary = _summary_line(design, mcu)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        code = _fallback_sketch(design, mcu, board, "GEMINI_API_KEY not set")
        return {
            "code": code,
            "filename": "main.ino",
            "target_board": board["board_name"],
            "framework": board["framework"],
            "summary": summary + " (fallback — set GEMINI_API_KEY for AI version)",
        }

    try:
        from google import genai
        from google.genai import types
    except Exception as exc:  # noqa: BLE001
        code = _fallback_sketch(design, mcu, board, f"google-genai unavailable: {exc}")
        return {
            "code": code,
            "filename": "main.ino",
            "target_board": board["board_name"],
            "framework": board["framework"],
            "summary": summary + " (fallback)",
        }

    user_message = (
        f"PERIPHERAL SUMMARY (nets touching {mcu.ref}):\n"
        f"{_peripheral_summary(design, mcu)}\n\n"
        f"FULL CIRCUIT DESIGN (JSON):\n"
        f"{design.model_dump_json(indent=2)}\n\n"
        f"USER GOAL: {design.description or '(no goal — write a generic demo)'}\n"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=_system_prompt(mcu_type, board),
                # Free-form text, not JSON.
                max_output_tokens=8192,
            ),
        )
        raw = response.text or ""
        print(
            f"[boardsmith.firmware] raw response: {len(raw)} chars "
            f"(MCU={mcu_type}, ref={mcu.ref})",
            flush=True,
        )

        try:
            _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            idx = len(list(_DEBUG_DIR.glob("firmware_*.ino")))
            (_DEBUG_DIR / f"firmware_{idx:03d}.ino").write_text(raw, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

        code = _strip_fences(raw)
        if not code.strip() or "void loop" not in code:
            print(
                "[boardsmith.firmware] response missing void loop() — using fallback",
                flush=True,
            )
            code = _fallback_sketch(design, mcu, board, "Gemini response was incomplete")
            summary_suffix = " (fallback)"
        else:
            summary_suffix = ""

        return {
            "code": code,
            "filename": "main.ino",
            "target_board": board["board_name"],
            "framework": board["framework"],
            "summary": summary + summary_suffix,
        }
    except Exception as exc:  # noqa: BLE001
        print(
            f"[boardsmith.firmware] Gemini call FAILED — using fallback. Reason: {exc}",
            flush=True,
        )
        traceback.print_exc()
        code = _fallback_sketch(design, mcu, board, f"Gemini error: {exc}")
        return {
            "code": code,
            "filename": "main.ino",
            "target_board": board["board_name"],
            "framework": board["framework"],
            "summary": summary + " (fallback)",
        }
