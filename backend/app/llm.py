from __future__ import annotations

import json
import os
import re
import traceback
from pathlib import Path
from typing import Any

from app.component_library import supported_component_names
from app.models import CircuitDesign, ComponentInstance, Net, NetConnection

# Where to dump the raw Gemini response for forensics (one file per call).
_DEBUG_DIR = Path(__file__).resolve().parents[1] / "generated" / "_llm_debug"

MODEL = "gemini-2.5-pro"


def _extract_json(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    payload = fenced.group(1) if fenced else text
    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Gemini response did not contain a JSON object")
    return json.loads(payload[start : end + 1])


def _system_prompt() -> str:
    allowed = ", ".join(supported_component_names())
    return f"""You are Boardsmith, a PCB design assistant.

You handle TWO kinds of prompts:
1. COMPONENT-LEVEL — the user lists specific parts ("ESP32 + DHT22 + LED + USB-C").
   Translate the list to the schema below, preserving every quantity exactly.
2. INTENT-LEVEL / GOAL — the user describes what they want the board to DO
   ("a PCB to control water dispense times", "a smart doorbell", "a desk
   weather clock"). DESIGN a sensible board that achieves that goal using
   only the allowed parts. Pick a reasonable MCU, sensors, controls,
   indicators, and power chain yourself.

Return STRICT JSON only. Do not include markdown.

Allowed component types only:
{allowed}

Schema:
{{
  "project_name": "Short_Project_Name",
  "description": "one sentence",
  "components": [
    {{"ref": "U1", "type": "ESP32", "label": "ESP32", "value": "optional value", "notes": "optional"}}
  ],
  "nets": [
    {{
      "name": "3V3",
      "kind": "power",
      "connections": [
        {{"ref": "U1", "pin": "3V3"}}
      ]
    }}
  ],
  "warnings": ["unsupported request or assumption"]
}}

General rules:
- Use only the allowed component types. If the user asks for an unsupported
  part, choose the nearest supported substitute and add a warning describing
  the swap.
- Always include GND and any needed power nets.
- Use realistic pin names from the selected parts.
- Include current-limiting resistors for LEDs and pull-ups for one-wire
  sensor data when useful.

Rules for COMPONENT-LEVEL prompts:
- PRESERVE EVERY QUANTITY the user specifies. "Eight LEDs" → eight separate
  LED components (D1..D8) with eight resistors and eight nets. Never collapse
  identical parts into a single representative.
- Use distinct reference designators per part (R1, R2, R3, …) and wire each
  one individually in the nets list.
- Do not omit components for brevity. There is no length limit on the output.

Rules for INTENT-LEVEL / GOAL prompts:
- Default to a small, sensible system: ONE MCU, the cheapest sensors that
  satisfy the goal, ONE indicator LED + resistor for status, ONE tactile
  button if user input is implied, USB-C power + AMS1117 + decoupling caps
  for power, and connectors for any actuator the library can't model.
- Pick the MCU based on the goal: ESP32 for anything timed / scheduled /
  Wi-Fi-flavored, Arduino Nano for very simple stand-alone behavior, STM32F103
  for low-level signal-heavy designs.
- If the goal requires a part that isn't in the allowed list (relay,
  solenoid, motor, motor driver, display, RTC, buzzer, SD card, RF module,
  etc.), DO NOT invent it. Emit a 4-pin Pin Header or JST-XH labeled with
  what plugs in (e.g. notes: "to external relay/solenoid driver"), wire the
  MCU's control signal + power + ground to it, and add a warning explaining
  what the user needs to attach off-board.
- Always add a warning at the top of the warnings list summarizing the
  design decisions you made (selected MCU, sensors, off-board parts) so the
  user can see what was inferred.
- Keep the inferred design minimal — prefer 8–15 components over 30. The
  user can refine to add more.
"""


def _refine_system_prompt() -> str:
    """System prompt for iterative edits — emphasizes preservation."""
    allowed = ", ".join(supported_component_names())
    return f"""You are Boardsmith, a PCB design refiner.
You are MODIFYING an existing circuit. Return STRICT JSON only — the FULL
updated design (not a diff, not a patch). No markdown.

Allowed component types only:
{allowed}

Schema (same as the original parser):
{{
  "project_name": "Short_Project_Name",
  "description": "one sentence",
  "components": [
    {{"ref": "U1", "type": "ESP32", "label": "ESP32", "value": "optional value", "notes": "optional"}}
  ],
  "nets": [
    {{
      "name": "3V3",
      "kind": "power",
      "connections": [
        {{"ref": "U1", "pin": "3V3"}}
      ]
    }}
  ],
  "warnings": ["unsupported request or assumption"]
}}

Rules:
- Preserve EVERY component from the previous design unless the user instruction
  explicitly removes or replaces it. Do not delete components for brevity.
- Keep reference designators STABLE. R1 stays R1. Only assign new refs
  (continuing the existing sequence: R5, R6, R7…) for newly added parts.
- Preserve EVERY net connection unless the instruction explicitly changes it.
- If the instruction only adds parts, the output must contain every original
  component plus the new ones.
- If the instruction is ambiguous, pick the most conservative interpretation
  and add a string to "warnings" describing the assumption.
- Use only allowed component types. Substitute the nearest allowed part if the
  user requests an unsupported one and add a warning.
- PRESERVE EVERY QUANTITY — same rules as initial parsing. "add eight LEDs"
  means eight separate LED components with eight resistors and eight nets.
- There is no length limit on the output.
"""


def refine_with_gemini(prev: CircuitDesign, instruction: str) -> CircuitDesign:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"google-genai is unavailable: {exc}") from exc

    user_message = (
        "PREVIOUS DESIGN (JSON):\n"
        f"{prev.model_dump_json(indent=2)}\n\n"
        "USER INSTRUCTION:\n"
        f"{instruction}"
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_refine_system_prompt(),
            response_mime_type="application/json",
            max_output_tokens=32768,
        ),
    )
    raw = response.text or ""
    print(f"[boardsmith.llm.refine] raw response: {len(raw)} chars", flush=True)

    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        idx = len(list(_DEBUG_DIR.glob("refine_*.json")))
        (_DEBUG_DIR / f"refine_{idx:03d}.json").write_text(raw, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    data = _extract_json(raw)
    print(
        f"[boardsmith.llm.refine] extracted JSON: "
        f"{len(data.get('components', []))} components, "
        f"{len(data.get('nets', []))} nets",
        flush=True,
    )
    design = CircuitDesign.model_validate(data)
    print(
        f"[boardsmith.llm.refine] parsed: {len(design.components)} components, "
        f"{len(design.nets)} nets, {len(design.warnings)} warnings",
        flush=True,
    )
    return design


def refine_circuit_design(prev: CircuitDesign, instruction: str) -> CircuitDesign:
    """Apply ``instruction`` to ``prev``. On any failure return ``prev`` plus a warning."""
    try:
        design = refine_with_gemini(prev, instruction)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[boardsmith.llm.refine] refine FAILED — keeping previous design. Reason: {exc}",
            flush=True,
        )
        warnings = [*prev.warnings, f"refinement failed — kept previous design ({exc})"]
        return prev.model_copy(update={"warnings": warnings})
    if not design.components or not design.nets:
        print(
            "[boardsmith.llm.refine] empty refinement — keeping previous design",
            flush=True,
        )
        warnings = [*prev.warnings, "refinement returned empty design — kept previous"]
        return prev.model_copy(update={"warnings": warnings})
    return design


def _followup_if_needed(client: Any, design: CircuitDesign, description: str) -> CircuitDesign:
    """Deliberately disabled.

    The previous behavior fired a second LLM call to "resolve warnings", but
    Gemini's "corrected" response routinely returned a stripped-down design
    that dropped components — collapsing maximalist prompts (30+ parts) down
    to under 10. Trust the first-pass design instead; warnings are surfaced
    in the UI as informational and the pin-name normalizer in
    ``app.pin_aliases`` already cleans up the most common alias issues.
    """
    return design


def _vision_prompt_addendum() -> str:
    """Extra rules layered on top of ``_system_prompt`` when an image is supplied."""
    return """

The user has attached an image. Treat it as one of:
A) A schematic, breadboard photo, or wiring sketch — EXTRACT mode.
B) A whiteboard sketch / mood board / inspiration photo of a finished
   product — INTENT mode (design from goal, same rules as the goal section
   above).

EXTRACT mode (A) — when the image clearly shows a circuit:
- Identify components by their drawn or photographed appearance: resistors
  (zigzags or color bands), LEDs (triangle+line or visible LED package),
  capacitors (parallel lines), buttons, MCUs (chip with labeled pins),
  sensors, headers, etc. Match each one to the closest allowed component
  type.
- Read any visible value/label text near a part (e.g. "330R", "10uF",
  "ESP32") and copy it into the value field.
- Trace wires/jumpers between components to build the nets list. Power
  rails on the breadboard sides become the GND and power nets.
- Infer voltages from visible components (USB-C → 5V, LiPo → 3.7V, etc.).
- If the image is ambiguous or low-resolution for a part, pick the most
  likely supported type and add a warning naming what was uncertain.

INTENT mode (B) — when the image is a goal/product picture (a coffee
machine, a smart light, a doorbell, etc.):
- Design a board that controls or interacts with the depicted thing using
  the goal-prompt rules above. The image is inspiration, not a circuit.

If accompanying text was provided, use it as additional guidance —
e.g. "ignore the buzzer", "this is a 3.3V design", "I want this to schedule
when the dispenser opens". Text always wins over the image when they
conflict.
"""


def parse_with_gemini(description: str) -> CircuitDesign:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"google-genai is unavailable: {exc}") from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=description,
        config=types.GenerateContentConfig(
            system_instruction=_system_prompt(),
            response_mime_type="application/json",
            # Generous budget so dense prompts (30+ components, 50+ nets)
            # don't get truncated mid-JSON.
            max_output_tokens=32768,
        ),
    )
    raw = response.text or ""
    print(f"[boardsmith.llm] raw response: {len(raw)} chars", flush=True)

    # Persist the raw response so we can re-parse offline if validation fails.
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        idx = len(list(_DEBUG_DIR.glob("response_*.json")))
        (_DEBUG_DIR / f"response_{idx:03d}.json").write_text(raw, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    try:
        data = _extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"[boardsmith.llm] JSON extract FAILED: {exc}", flush=True)
        raise
    print(
        f"[boardsmith.llm] extracted JSON: "
        f"{len(data.get('components', []))} components, "
        f"{len(data.get('nets', []))} nets in payload",
        flush=True,
    )

    try:
        design = CircuitDesign.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        print(f"[boardsmith.llm] Pydantic validation FAILED: {exc}", flush=True)
        traceback.print_exc()
        raise

    print(
        f"[boardsmith.llm] parsed: {len(design.components)} components, "
        f"{len(design.nets)} nets, {len(design.warnings)} warnings",
        flush=True,
    )
    return _followup_if_needed(client, design, description)


def parse_with_gemini_vision(
    image_bytes: bytes,
    mime_type: str,
    description: str | None = None,
) -> CircuitDesign:
    """Vision-aware parse: image (sketch/photo) + optional text instructions.

    Sends both the image and the text in the same Gemini request so the
    model can cross-reference visible components with any user
    annotations.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"google-genai is unavailable: {exc}") from exc

    client = genai.Client(api_key=api_key)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    user_text = (
        description.strip()
        if description and description.strip()
        else "Extract the circuit shown in the attached image."
    )
    contents = [image_part, user_text]

    system_instruction = _system_prompt() + _vision_prompt_addendum()

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            max_output_tokens=32768,
        ),
    )
    raw = response.text or ""
    print(
        f"[boardsmith.llm.vision] raw response: {len(raw)} chars "
        f"(image={len(image_bytes)} bytes, mime={mime_type})",
        flush=True,
    )

    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        idx = len(list(_DEBUG_DIR.glob("vision_*.json")))
        (_DEBUG_DIR / f"vision_{idx:03d}.json").write_text(raw, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    data = _extract_json(raw)
    print(
        f"[boardsmith.llm.vision] extracted JSON: "
        f"{len(data.get('components', []))} components, "
        f"{len(data.get('nets', []))} nets",
        flush=True,
    )

    design = CircuitDesign.model_validate(data)
    print(
        f"[boardsmith.llm.vision] parsed: {len(design.components)} components, "
        f"{len(design.nets)} nets, {len(design.warnings)} warnings",
        flush=True,
    )
    return design


def fallback_design(description: str, reason: str | None = None) -> CircuitDesign:
    text = description.lower()
    components: list[ComponentInstance] = [
        ComponentInstance(ref="J1", type="USB-C Input", label="USB-C Power"),
        ComponentInstance(ref="U2", type="AMS1117", label="3.3V LDO", value="AMS1117-3.3"),
        ComponentInstance(ref="C1", type="Capacitor", label="Input decoupling", value="10uF"),
        ComponentInstance(ref="C2", type="Capacitor", label="Output decoupling", value="10uF"),
    ]
    warnings: list[str] = []
    if reason:
        warnings.append(f"Gemini fallback used: {reason}")

    if "arduino" in text:
        mcu_ref, mcu_type, data_pin = "U1", "Arduino Nano", "D2"
    elif "stm32" in text:
        mcu_ref, mcu_type, data_pin = "U1", "STM32F103", "PA0"
    else:
        mcu_ref, mcu_type, data_pin = "U1", "ESP32", "GPIO5"
    components.append(ComponentInstance(ref=mcu_ref, type=mcu_type, label=mcu_type))

    sensor_ref = None
    if "mpu" in text:
        sensor_ref = "U3"
        components.append(ComponentInstance(ref=sensor_ref, type="MPU6050", label="MPU6050 IMU"))
    elif "hc-sr04" in text or "ultrasonic" in text:
        sensor_ref = "U3"
        components.append(ComponentInstance(ref=sensor_ref, type="HC-SR04", label="Ultrasonic Sensor"))
    elif "bmp" in text or "pressure" in text:
        sensor_ref = "U3"
        components.append(ComponentInstance(ref=sensor_ref, type="BMP280", label="BMP280 Sensor"))
    elif "dht" in text or "temperature" in text or "humidity" in text:
        sensor_ref = "U3"
        components.append(ComponentInstance(ref=sensor_ref, type="DHT22", label="DHT22 Sensor"))

    include_led = "led" in text or "indicator" in text
    if include_led:
        components.extend(
            [
                ComponentInstance(ref="R1", type="Resistor", label="LED current limit", value="330R"),
                ComponentInstance(ref="D1", type="LED", label="Status LED", value="Red"),
            ]
        )
    if sensor_ref == "U3" and any(k in text for k in ("dht", "temperature", "humidity")):
        components.append(ComponentInstance(ref="R2", type="Resistor", label="DHT22 data pullup", value="10K"))

    nets = [
        Net(
            name="VBUS",
            kind="power",
            connections=[
                NetConnection(ref="J1", pin="VBUS"),
                NetConnection(ref="U2", pin="VIN"),
                NetConnection(ref="C1", pin="1"),
            ],
        ),
        Net(
            name="3V3",
            kind="power",
            connections=[
                NetConnection(ref="U2", pin="VOUT"),
                NetConnection(ref="C2", pin="1"),
                NetConnection(ref=mcu_ref, pin="3V3"),
            ],
        ),
        Net(
            name="GND",
            kind="ground",
            connections=[
                NetConnection(ref="J1", pin="GND"),
                NetConnection(ref="U2", pin="GND"),
                NetConnection(ref="C1", pin="2"),
                NetConnection(ref="C2", pin="2"),
                NetConnection(ref=mcu_ref, pin="GND"),
            ],
        ),
    ]

    if sensor_ref:
        nets[1].connections.append(NetConnection(ref=sensor_ref, pin="VCC"))
        nets[2].connections.append(NetConnection(ref=sensor_ref, pin="GND"))
        sensor_type = next(c.type for c in components if c.ref == sensor_ref)
        if sensor_type in ("MPU6050", "BMP280"):
            nets.extend(
                [
                    Net(name="I2C_SCL", connections=[NetConnection(ref=mcu_ref, pin="GPIO18"), NetConnection(ref=sensor_ref, pin="SCL")]),
                    Net(name="I2C_SDA", connections=[NetConnection(ref=mcu_ref, pin="GPIO19"), NetConnection(ref=sensor_ref, pin="SDA")]),
                ]
            )
        elif sensor_type == "HC-SR04":
            nets.extend(
                [
                    Net(name="TRIG", connections=[NetConnection(ref=mcu_ref, pin="GPIO4"), NetConnection(ref=sensor_ref, pin="TRIG")]),
                    Net(name="ECHO", connections=[NetConnection(ref=mcu_ref, pin="GPIO5"), NetConnection(ref=sensor_ref, pin="ECHO")]),
                ]
            )
        else:
            nets.append(Net(name="DHT_DATA", connections=[NetConnection(ref=mcu_ref, pin=data_pin), NetConnection(ref=sensor_ref, pin="DATA")]))
            nets[1].connections.append(NetConnection(ref="R2", pin="1"))
            nets[-1].connections.append(NetConnection(ref="R2", pin="2"))

    if include_led:
        nets.extend(
            [
                Net(name="LED_DRIVE", connections=[NetConnection(ref=mcu_ref, pin="GPIO4"), NetConnection(ref="R1", pin="1")]),
                Net(name="LED_A", connections=[NetConnection(ref="R1", pin="2"), NetConnection(ref="D1", pin="A")]),
            ]
        )
        nets[2].connections.append(NetConnection(ref="D1", pin="K"))

    return CircuitDesign(
        project_name="Boardsmith_Demo",
        description=description,
        components=components,
        nets=nets,
        warnings=warnings,
    )


def parse_circuit_description(
    description: str,
    *,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
) -> CircuitDesign:
    """Parse a user prompt into a CircuitDesign.

    If ``image_bytes`` is supplied we route through the vision-aware
    parser; ``description`` is passed alongside as optional context. The
    fallback path is text-only because the rule-based fallback can't
    interpret pixels.
    """
    use_vision = image_bytes is not None and mime_type
    try:
        if use_vision:
            design = parse_with_gemini_vision(
                image_bytes,  # type: ignore[arg-type]
                mime_type,    # type: ignore[arg-type]
                description,
            )
        else:
            design = parse_with_gemini(description)
    except Exception as exc:  # noqa: BLE001
        path = "vision" if use_vision else "text"
        print(
            f"[boardsmith.llm] Gemini {path} parse FAILED — using fallback. "
            f"Reason: {exc}",
            flush=True,
        )
        return fallback_design(description, str(exc))
    if not design.components or not design.nets:
        print(
            f"[boardsmith.llm] Gemini returned empty design — using fallback. "
            f"components={len(design.components)} nets={len(design.nets)}",
            flush=True,
        )
        return fallback_design(description, "Gemini returned an incomplete circuit")
    return design
