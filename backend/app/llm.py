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
    return f"""You are Boardsmith, a PCB design parser.
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

Rules:
- Use only the allowed component types. If the user asks for an unsupported part, choose the nearest supported part and add a warning.
- Always include GND and any needed power nets.
- Use realistic pin names from the selected parts.
- Include current-limiting resistors for LEDs and pullups for one-wire sensor data when useful.
- PRESERVE EVERY QUANTITY the user specifies. If they say "eight LEDs", emit
  eight separate LED components (D1..D8 or LED1..LED8) — never collapse them
  into a single representative part. Same for resistors, capacitors, buttons,
  sensors, and connectors. Match the user's requested counts exactly.
- Use distinct reference designators per part (R1, R2, R3, …) and wire each
  one individually in the nets list. A "row of 8 LEDs" means 8 LEDs, 8
  resistors, and 8 separate signal nets.
- Do not omit components for brevity. There is no length limit on the output.
"""


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


def parse_circuit_description(description: str) -> CircuitDesign:
    try:
        design = parse_with_gemini(description)
    except Exception as exc:  # noqa: BLE001
        print(f"[boardsmith.llm] Gemini parse FAILED — using fallback. Reason: {exc}", flush=True)
        return fallback_design(description, str(exc))
    if not design.components or not design.nets:
        print(
            f"[boardsmith.llm] Gemini returned empty design — using fallback. "
            f"components={len(design.components)} nets={len(design.nets)}",
            flush=True,
        )
        return fallback_design(description, "Gemini returned an incomplete circuit")
    return design
