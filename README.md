# Boardsmith

> Plain English in. Manufacturable PCB out.

Describe a circuit in natural language — or **drop a hand-drawn sketch / breadboard photo** — and Boardsmith parses it with Gemini, lays out the board, routes copper, renders a 3D view, prices an all-in JLCPCB build, and gives you back a single zip that JLCPCB can manufacture.

Live demo: <https://boardsmith.up.railway.app>

```
Plain English  ─┐
                ├─►  Gemini 2.5 Pro / Vision  ──►  CircuitDesign JSON
Sketch / photo ─┘
                                                        │
   ┌────────────────────────────────────────────────────┼────────────────────────────────────────────────┐
   ▼                                ▼                   ▼                ▼                ▼              ▼
Schematic SVG +              Force-directed         Lee-algorithm     3D Three.js     BOM + CPL +     Gerber RS-274X +
KiCad .kicad_sch +            placement              autorouter        FR4 board       JLCPCB cost     Excellon drill
Falstad simulate URL                                                                    breakdown       (one zip)
```

Every stage emits a Server-Sent Event so the UI fills in as each artifact lands. Jobs are persisted to Postgres so refinements and revisions survive a redeploy.

---

## Highlights

- **Auth + Postgres.** Supabase Google OAuth on the front, asyncpg-backed jobs table on the back. Every query is scoped by `user_id`; modern asymmetric Supabase JWTs (ES256/RS256 via JWKS) work alongside the legacy HS256 secret.
- **Persistent dashboard with a jobs sidebar.** Three-pane IDE layout that's always visible — auto-loads your most recent project on sign-in, lets you click between past designs, and lets you delete projects (cascading their refinement chain) right from the sidebar.
- **One-click Falstad SPICE simulation.** Each schematic export bundles a Falstad `circuitjs1` URL — open it and watch current flow, LEDs light up, capacitors charge. The exporter detects R+LED+button branches, picks a sensible supply voltage (5V default, 3.3V for ESP32/STM32, 3.7V for LiPo), and suppresses the button when there's nothing simulatable so the demo never opens into a short circuit.
- **JLCPCB-ready manufacturing bundle.** A single `*_manufacturing_bundle.zip` containing Gerbers, drill, engineering BOM, JLCPCB-format BOM, and a CPL pick-and-place file — auto-detected by JLCPCB's quote uploader.
- **All-in JLCPCB cost breakdown.** A receipt-style breakdown on the BOM tab that uses JLCPCB's published pricing (parts + 5% scrap buffer, board fab tier, $8 SMT setup, $0.0017/joint placement, stencil, shipping) for 5 / 30 / 100-board tiers. Answers "how much for 5 boards assembled?" with a real number.
- **Public share links.** Hit **Share** in the top bar to publish a read-only link at `/p/<job_id>` — no auth, no downloads, just the live 3D / PCB / schematic / BOM tabs. Great for portfolio links and Discord drops.
- **Multimodal prompts.** The prompt box accepts a paperclip-attached image, a drag-and-dropped file, or a paste from clipboard. Gemini Vision extracts components and connections from the picture; optional accompanying text becomes additional guidance.
- **Intent-level prompts.** Describe the *goal* (`"a PCB to control water dispense times"`, `"a smart doorbell"`) and Gemini designs a sensible minimal system — picks an MCU, breaks unsupported parts (relays, motors, displays) out to a header for an off-board driver, and explains every choice it made.
- **Design notes panel.** Every project shows a dedicated "Design notes" card above the viewer tabs listing each design decision the LLM made (MCU choice, power chain, off-board breakouts). Separate from warnings so rationale never gets mixed with actual problems.
- **Native KiCad 10 schematic export.** A real `.kicad_sch` with category-grouped column layout, IEC symbol shapes, and per-symbol `(instances …)` blocks so KiCad opens it as a project.

---

## Tech stack

| Layer | Stack |
| --- | --- |
| LLM | Gemini 2.5 Pro (text + vision) via `google-genai` |
| Backend | FastAPI · uvicorn · asyncpg · python-jose · python-multipart · lzstring |
| Database / Auth | Supabase Postgres + Supabase Auth (Google OAuth) |
| PCB pipeline | schemdraw · custom force-directed placement · custom Lee router · custom Gerber writer |
| Frontend | React + Vite + TypeScript · Tailwind v4 · Three.js · @supabase/supabase-js · react-router-dom |
| Hosting | Railway (frontend + backend services) |

---

## Quick start (local)

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
cp .env.example .env        # fill in the keys below
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`backend/.env`:

```
GEMINI_API_KEY=...                # https://aistudio.google.com/app/apikey
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=<anon key>
SUPABASE_JWT_SECRET=<jwt secret>  # from Supabase Settings → API
DATABASE_URL=postgresql://...     # session-mode pooler URL recommended
```

Without a `GEMINI_API_KEY`, Boardsmith falls back to a deterministic ESP32 + USB-C + AMS1117 + LED demo so the rest of the pipeline still runs end-to-end.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

`frontend/.env.local`:

```
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key>
```

Open <http://localhost:5173>.

### Supabase setup

1. Create a Supabase project.
2. **Authentication → Providers → Google** — enable, paste your Google OAuth client ID + secret.
3. **Authentication → URL configuration** — add your dev (`http://localhost:5173`) and prod (`https://your-app.up.railway.app`) site URLs.
4. The `jobs` table and `is_public` column are created idempotently on first connection — no manual migration needed.

---

## API

All `/api/jobs/*` endpoints require a Supabase JWT (`Authorization: Bearer …`, or `?token=…` for SSE / `<a download>`).

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | liveness probe |
| `POST` | `/api/jobs` | **multipart/form-data** — `description: string` (optional), `image: file` (optional). At least one required. |
| `GET` | `/api/jobs` | list of the caller's jobs (sidebar feed) |
| `GET` | `/api/jobs/{id}` | full snapshot (events + artifacts index) |
| `GET` | `/api/jobs/{id}/lineage` | refinement chain for the breadcrumb |
| `GET` | `/api/jobs/{id}/events` | SSE stream of `{stage, status, data, message}` |
| `GET` | `/api/jobs/{id}/artifact/{name}` | download a generated file |
| `POST` | `/api/jobs/{id}/refine` | refinement: `{ "instruction": "…" }` |
| `DELETE` | `/api/jobs/{id}` | cascade-delete a job + revisions; returns `{deleted: [ids]}` |
| `POST` | `/api/jobs/{id}/publish` | flip `is_public=true`; returns `{share_url: "/p/<id>"}` |
| `POST` | `/api/jobs/{id}/unpublish` | revoke the public link |
| `GET` | `/api/public/jobs/{id}` | **no auth** — read-only snapshot if `is_public=true`; artifact URLs stripped |

### Artifacts produced per job

- `circuit_json` — parsed `CircuitDesign`
- `schematic_svg` — readable schematic for the in-app viewer
- `kicad_schematic` — native KiCad 10 `.kicad_sch`
- `falstad_txt` — Falstad `circuitjs1` text file (when simulatable)
- `bom_json` / `bom_csv` / `bom_jlcpcb_csv` — three views of the BOM
- `cpl_csv` — JLCPCB-format pick-and-place file
- `layout_json` / `pcb_svg` — top-down PCB render data
- `gerbers` — `*_manufacturing_bundle.zip` (Gerbers + drill + BOMs + CPL)

---

## Pipeline

Each stage emits SSE events with `stage / status / data / message`.

| # | Stage | What it does |
| --- | --- | --- |
| 1 | `parse` | Gemini → strict JSON → Pydantic. Vision branch when an image is attached. |
| 2 | `schematic` | SVG + KiCad `.kicad_sch` + Falstad text + simulate URL |
| 3 | `bom` | Group identical parts, look up LCSC numbers, price each line, compute SMT joint count, generate cost tiers, write engineering CSV + JLCPCB CSV |
| 4 | `pcb_layout` | Force-directed placement on a dynamically-sized board |
| 5 | `routing` | Lee grid router; ratsnest fallback per net. Writes CPL after layout. |
| 6 | `3d` | Three.js board data: substrate, traces, pads, components |
| 7 | `gerber` | Bundles Gerbers + drill + BOMs + CPL into one JLCPCB-ready zip |

---

## JLCPCB cost model

Implemented in [`backend/app/cost.py`](backend/app/cost.py). Targets a default 100×100 mm 2-layer green-soldermask board with one-side SMT.

| Component | Source / value |
| --- | --- |
| Parts | `total_unit_cost_usd × qty × 1.05` (5% scrap buffer) |
| PCB fab | Tiered lookup: 5 boards = $2.00, 30 = $8.00, 100 = $25.00 |
| SMT setup | $8.00 flat, one-time per order |
| SMT placement | `joints × qty × $0.0017` (JLCPCB published rate) |
| Stencil | $8.00 (skipped when `joints == 0`) |
| Shipping | $5.00 flat (DHL economy estimate) |

The BOM viewer surfaces this as a tier pill (`5 boards · 30 boards · 100 boards`) plus a receipt:

```
Parts (5× × 1.05 buffer)         $12.34
PCB fabrication (5 boards)        $2.00
SMT setup + stencil               $16.00
Component placement (84 joints)    $0.71
Shipping (DHL economy)             $5.00
─────────────────────────────────────────
All-in build           $36.05  ($7.21/board)
```

---

## Public share links

- Click **Share** in the top bar of any complete project. Boardsmith calls `POST /api/jobs/{id}/publish`, copies `${origin}/p/<id>` to your clipboard, and flashes "Link copied".
- Visiting `/p/<id>` skips the auth gate, hits `GET /api/public/jobs/<id>`, and renders the same `ViewerTabs` with `readOnly` set — every download bar (KiCad / BOM / CPL / Manufacturing bundle / Simulate) is hidden.
- Backend gates on the `is_public` boolean column; no flag, no snapshot. Artifact URLs are stripped from the response.

---

## Multimodal input

Drop a sketch, paste a phone photo of a breadboard, or click the paperclip in the prompt composer. Accepted: PNG, JPEG, WebP, GIF. Max 10 MB.

The vision branch in [`backend/app/llm.py`](backend/app/llm.py) sends the image as a `types.Part.from_bytes(...)` plus the existing strict-JSON system prompt augmented with a vision rule set ("identify resistors by zigzag color bands, LEDs by triangle+line, MCUs by labeled pins; trace wires/jumpers between components; copy any visible value labels into the value field").

You can mix and match:

- Text only → existing behavior.
- Image only → "Extract the circuit shown in the attached image."
- Image + text → image is the primary source, text is guidance ("ignore the buzzer", "this is a 3.3V design").

---

## Component library

A focused, hand-curated set in [`backend/app/component_library.py`](backend/app/component_library.py) — the system prompt restricts Gemini to these so the pipeline can always render what it gets back.

| Class | Parts |
| --- | --- |
| Microcontrollers | ESP32, Arduino Nano, STM32F103 |
| Sensors | DHT22, MPU6050, HC-SR04, BMP280 |
| Power | USB-C input, AMS1117 LDO |
| Discrete | LED, push button, generic diode |
| Passives | Resistor, capacitor, inductor |
| Connectors | 2.54 mm pin header, JST-XH |

Each entry has a KiCad symbol shape ([`kicad_symbols.py`](backend/app/kicad_symbols.py)), a footprint, an LCSC part number ([`lcsc.py`](backend/app/lcsc.py)) with a unit price, an SMT-joint flag for the cost model, and pin-name aliases ([`pin_aliases.py`](backend/app/pin_aliases.py)) so Gemini can be sloppy without breaking the pipeline.

---

## Demo prompts

Simple:
```text
An ESP32 connected to a DHT22 temperature sensor, an LED with a current
limiting resistor, and a USB-C power input with an AMS1117 3.3V regulator.
```

Maximalist:
```text
An STM32F103 reading two BMP280 pressure sensors over I2C, driving eight
status LEDs through individual current-limiting resistors, with a tactile
reset button, USB-C power, AMS1117 LDO, four decoupling capacitors, and a
JST-XH connector for an external sensor.
```

Vision (drop a photo):
```text
Build the circuit shown in this breadboard photo. It's 5V, ignore the buzzer.
```

---

## Project layout

```
backend/
  app/
    main.py             FastAPI + SSE + multipart job creation + share endpoints
    auth.py             Supabase JWT verification (HS256 + JWKS asymmetric)
    db.py               asyncpg pool + idempotent schema/migration
    storage.py          jobs hot cache + Postgres durable record + delete cascade + publish
    pipeline.py         orchestrates the 7-stage pipeline (text or vision branch)
    llm.py              Gemini parsing — parse_with_gemini + parse_with_gemini_vision
    component_library.py
    pin_aliases.py
    schematic.py        SVG schematic renderer
    kicad_writer.py     native KiCad 10 .kicad_sch generator
    kicad_symbols.py    IEC/IEEE symbol shape registry
    pcb_layout.py       force-directed placement + ratsnest
    router.py           grid-based Lee-algorithm autorouter
    bom.py              BOM build + LCSC + pricing + JLCPCB CSV
    cost.py             JLCPCB all-in cost estimator
    cpl.py              JLCPCB pick-and-place CSV writer
    falstad.py          CircuitDesign → circuitjs1 URL
    gerber.py           Gerber RS-274X + Excellon drill writer + bundle assembly
    lcsc.py             LCSC part-number + unit-price lookup table

frontend/
  src/
    main.tsx            BrowserRouter wrapper
    App.tsx             Routes (/ vs /p/:id), persistent dashboard, SSE pipeline hook
    api.ts              REST + EventSource + auth-aware fetch wrappers
    types.ts            mirrors backend Pydantic models (incl. CostEstimate)
    lib/
      auth.tsx          Supabase auth context + access-token accessor
      supabase.ts       singleton client
    components/
      AuthGate.tsx      sign-in screen (Google OAuth)
      Board3DViewer.tsx Three.js board with OrbitControls
      Viewers.tsx       3D / PCB / Schematic / BOM tabs (+ readOnly mode)
      PromptComposer.tsx paperclip + drag-drop + paste + thumbnail
      PromptHistory.tsx jobs sidebar with delete
      LineageBreadcrumb.tsx
      PipelineProgress.tsx
      RefinePanel.tsx
      PublicViewer.tsx  /p/:id read-only viewer
      Logo.tsx
    styles.css          Tailwind v4 + Boardsmith design tokens
```

---

## Deploying to Railway

Two services side-by-side: one for the FastAPI backend, one for the Vite frontend.

**Backend service**
- Root: `backend/`
- Build: `pip install -r requirements.txt`
- Start: `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Vars: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`, `DATABASE_URL`, `FRONTEND_URL=https://your-frontend.up.railway.app`

**Frontend service**
- Root: `frontend/`
- Build: `npm ci && npm run build`
- Start: `npm run start` (binds Vite preview to `$PORT` with SPA fallback for `/p/:id`)
- Vars (set at build time): `VITE_API_URL=https://your-backend.up.railway.app`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`

Make sure your Supabase **Authentication → URL configuration** lists the Railway frontend domain.

---

## Notes & non-goals

- The autorouter is intentionally simple. If a route can't fit, it falls back to a ratsnest line and the pipeline keeps going. Run real DRC in KiCad before sending to fab.
- The KiCad export is **schematic only** (no `.kicad_pcb`). Open `.kicad_sch` directly with `File → Open` — KiCad will offer to create a `.kicad_pro` for you.
- Cost estimates assume a 100×100 mm 2-layer board and one-side SMT. Real JLCPCB pricing scales with size, layer count, and finish — treat the number as a "good enough for go/no-go" figure, not a final quote.
- Public viewers can only see; they can't download artifacts. There's no "unshare from the UI" yet — call `POST /api/jobs/{id}/unpublish` directly if you need to revoke a link.
- Refinements are text-only. Image-driven refinement is a TODO.
