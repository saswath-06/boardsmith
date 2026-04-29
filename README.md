# Boardsmith

> From plain English to a manufacturable PCB in seconds.

Describe a circuit in natural language. Boardsmith parses it with Gemini, lays it out, routes the copper, renders a 3D board, and gives you back a complete fab package — Gerbers, an Excellon drill file, **and a native KiCad 10 schematic** — all streaming live from the backend over Server-Sent Events.

```
Natural language description
            ↓
Gemini 2.5 Pro → structured circuit JSON (components + nets)
            ↓
Schematic SVG  +  KiCad 10 .kicad_sch  (real symbol shapes, 3-column layout)
            ↓
Force-directed component placement on a dynamically-sized board
            ↓
Lee-algorithm autorouter (net-aware, falls back to ratsnest gracefully)
            ↓
Three.js 3D board (FR4 substrate, copper traces, gold pads, sprite labels)
            ↓
Gerber RS-274X ZIP (F.Cu · B.Cu · F.Mask · B.Mask · F.SilkS · Edge.Cuts · .drl)
```

Every stage emits an SSE event with stage / status / data / message, so the UI fills in the moment each artifact is ready.

---

## Quick start

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
cp .env.example .env        # then add your GEMINI_API_KEY
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Without a `GEMINI_API_KEY`, Boardsmith falls back to a deterministic ESP32 + USB-C + AMS1117 + LED demo design — every other pipeline stage still runs end-to-end.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

---

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | liveness probe |
| `POST` | `/api/jobs` | create a job; body: `{ "description": "..." }` |
| `GET` | `/api/jobs/{job_id}` | snapshot of a running job |
| `GET` | `/api/jobs/{job_id}/events` | SSE stream of `{stage, status, data, message}` |
| `GET` | `/api/jobs/{job_id}/artifact/{name}` | download generated file |

Artifacts produced per job:

- `circuit_json` — parsed `CircuitDesign`
- `schematic_svg` — readable schematic for the in-app viewer
- **`kicad_schematic` — native KiCad 10 `.kicad_sch`** with category-grouped column layout, IEC symbol shapes (resistor, capacitor, LED triangle, regulator block, …), and per-symbol `(instances …)` blocks so KiCad opens it as a project
- `layout_json` — `BoardLayout` with components, traces, ratsnest
- `pcb_layout_svg` — top-down PCB render
- `gerber_zip` — full fab package

---

## Component library

A focused, hand-curated set so the LLM can't request a part the pipeline can't render:

| Class | Parts |
| --- | --- |
| Microcontrollers | ESP32, Arduino Nano, STM32F103 |
| Sensors | DHT22, MPU6050, HC-SR04, BMP280 |
| Power | USB-C input, AMS1117 LDO |
| Discrete | LED, push button, generic diode |
| Passives | Resistor, capacitor, inductor |
| Connectors | 2.54 mm pin header, JST-XH |

Each entry has its own KiCad symbol shape (in [`backend/app/kicad_symbols.py`](backend/app/kicad_symbols.py)) and footprint reference, plus pin-name aliases (`ANODE`→`A`, `+5V`→`VBUS`, …) in [`backend/app/pin_aliases.py`](backend/app/pin_aliases.py) so Gemini can be sloppy without breaking the pipeline.

---

## Demo prompts

Simple:
```text
An ESP32 connected to a DHT22 temperature sensor, an LED with a current
limiting resistor, and a USB-C power input with an AMS1117 3.3V regulator.
```

Maximalist (every column gets work):
```text
An STM32F103 reading two BMP280 pressure sensors over I2C, driving eight
status LEDs through individual current-limiting resistors, with a tactile
reset button, USB-C power, AMS1117 LDO, four decoupling capacitors, and a
JST-XH connector for an external sensor.
```

---

## Project layout

```
backend/
  app/
    main.py             FastAPI + SSE
    pipeline.py         orchestrates the 7-stage pipeline
    llm.py              Gemini parsing + JSON validation + fallback design
    component_library.py
    pin_aliases.py
    schematic.py        SVG schematic renderer
    kicad_writer.py     native KiCad 10 .kicad_sch generator
    kicad_symbols.py    IEC/IEEE symbol shape registry
    pcb_layout.py       force-directed placement + ratsnest
    router.py           grid-based Lee-algorithm autorouter
    gerber.py           Gerber RS-274X + Excellon drill writer
    storage.py          in-memory job store with async event fan-out

frontend/
  src/
    App.tsx             idle/active mode router + SSE hook
    api.ts              REST + EventSource client
    types.ts            mirrors backend Pydantic models
    components/
      Board3DViewer.tsx Three.js board with OrbitControls
      Viewers.tsx       tabbed 3D / PCB / Schematic + KiCad + Gerber download
      PipelineProgress.tsx
      PromptHistory.tsx
      AmbientPcb.tsx
      Logo.tsx
    styles.css          Tailwind v4 + Boardsmith design tokens
```

---

## Notes

- The autorouter is intentionally simple. If a route can't fit, it falls back to a ratsnest line and the pipeline keeps going. Run real DRC in KiCad before sending to fab.
- The KiCad export is **schematic only** (no `.kicad_pcb`). Open `.kicad_sch` directly with `File → Open` — KiCad will offer to create a `.kicad_pro` for you.
- Gerber output is demo-quality. For production, run KiCad's CAM job against the schematic + a manually laid PCB.
