# Boardsmith
> From plain English to a manufacturable PCB in seconds.

PCB design has a massive accessibility problem. The tools are arcane, the learning curve is brutal, and most people who need a simple board can't get one made without hiring someone or spending 10 hours in KiCad. Boardsmith removes that barrier entirely.

---

## The Problem

Designing a PCB today means learning KiCad or Altium, understanding component footprints, manually placing parts, routing traces, running design rule checks, and exporting Gerber files — all before you've ordered a single board. For a simple circuit, this is a 10-hour process for an experienced engineer. For a student or hobbyist, it's a wall they never get past.

The knowledge required to describe what you want and the knowledge required to produce a manufacturable board are completely different skills. Boardsmith separates them.

---

## What Boardsmith Does

Describe your circuit in plain English. Boardsmith handles everything else.

**The pipeline:**

```
Natural language description
            ↓
Gemini parses intent → extracts component list and connections
            ↓
Schematic generated and rendered (Schemdraw)
            ↓
Components placed on PCB canvas with ratsnest connections
            ↓
Traces auto-routed between components
            ↓
3D board visualization rendered (Three.js)
            ↓
Gerber files exported → ready to upload to JLCPCB
```

Every stage streams to the frontend in real time. You watch the board build itself.

---

## The Demo

**Input:**
> "An ESP32 microcontroller connected to a DHT22 temperature sensor, an LED indicator with a current limiting resistor, and a USB-C power input with a decoupling capacitor."

**Output in under 10 seconds:**
- Clean schematic with labeled components and connections
- PCB layout with components placed and traces routed
- 3D board visualization rotating on a green substrate
- Gerber file package ready for fabrication

You could upload that Gerber file to JLCPCB right now and have boards in your hands in a week for $5.

---

## Why It's Different

Boardsmith doesn't just generate code or suggest a design. It produces a complete manufacturable artifact at every stage of the pipeline — schematic, layout, 3D render, fabrication files. Each stage is a real output, not a preview.

The target user isn't a hardware expert. It's the firmware engineer who needs a breakout board, the student who wants to prototype an idea, the maker who has never touched EDA software. Boardsmith doesn't require you to know what a ratsnest is to use it.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Natural language parsing | Gemini (Google Cloud) |
| Schematic generation | Schemdraw (Python) |
| Netlist representation | SKiDL (Python) |
| PCB layout engine | Custom placement + routing (Python) |
| 3D board visualization | Three.js |
| Gerber export | Custom Gerber writer (Python) |
| Backend | FastAPI + SSE |
| Frontend | Next.js + Tailwind |

---

## Supported Components

Boardsmith ships with a library of the most common PCB components:

- Microcontrollers: ESP32, Arduino Nano, STM32
- Sensors: DHT22, MPU6050, HC-SR04, BMP280
- Passives: Resistors, capacitors, inductors
- Discrete: LEDs, buttons, switches, diodes
- Power: USB-C input, LDO regulators, decoupling caps
- Connectors: Pin headers, JST, USB

Adding a new component is a single entry in the component library.

---

## Pipeline Detail

**Stage 1 — Intent Parsing**
Gemini receives the natural language description and returns a structured JSON object containing the component list, net connections, and power rails. Ambiguous descriptions are clarified with a follow-up prompt before proceeding.

**Stage 2 — Schematic Generation**
Schemdraw renders a clean schematic from the netlist. Components are arranged by functional block (power, logic, IO) and wires are routed to avoid crossings where possible.

**Stage 3 — PCB Layout**
Components are placed using a force-directed algorithm that clusters connected components and respects standard PCB design practices (decoupling caps close to power pins, sensors away from noise sources). Ratsnest lines show unrouted connections.

**Stage 4 — Auto-routing**
A grid-based Lee algorithm routes traces between component pads on separate copper layers. Design rule checks run automatically — minimum trace width, clearance, via sizing.

**Stage 5 — 3D Visualization**
Three.js renders the board with a green FR4 substrate, copper-colored traces, and component outlines. The board rotates on screen. Users can zoom and pan.

**Stage 6 — Gerber Export**
The layout is serialized to industry-standard Gerber RS-274X format — the same format every PCB manufacturer accepts. The export package includes copper layers, silkscreen, soldermask, drill files, and board outline.

---

## Getting Started

```bash
# Clone the repo
git clone https://github.com/your-username/boardsmith
cd boardsmith

# Backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

**Required environment variables:**
```
GEMINI_API_KEY=
```

---

## What's Next

- **Simulation** — run a SPICE simulation on the generated schematic before committing to layout, catching errors at the electrical level
- **BOM generation** — produce a bill of materials with Mouser/Digikey links and real-time pricing
- **Design rule profiles** — support manufacturer-specific DRC rules (JLCPCB, OSHPark, PCBWay) so exported Gerbers are guaranteed to pass their checks
- **Multi-board projects** — describe a system with multiple interconnected boards and generate them as a matched set
- **Image input** — upload a hand-drawn schematic sketch and have Boardsmith recognize components and connections

---

## Built With

- [Gemini](https://deepmind.google/technologies/gemini/) — natural language to circuit intent
- [Schemdraw](https://schemdraw.readthedocs.io/) — schematic rendering
- [SKiDL](https://devbisme.github.io/skidl/) — netlist representation
- [Three.js](https://threejs.org/) — 3D board visualization
- [FastAPI](https://fastapi.tiangolo.com/) — backend and SSE streaming
- [Next.js](https://nextjs.org/) — frontend dashboard

---

## License

MIT
