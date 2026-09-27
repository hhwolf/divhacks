# Adaptive Room Planner — "Where did my space go?"

DivHacks 2026 · **Live Better** track. Scan your NYC room once, text furniture ideas over iMessage, and rearrange your real room like a cozy top-down game before you buy or haul anything up three flights.

> Renter in a 100–150 sq ft room, buying secondhand, wants one more thing to fit. Bed can't move. Will the Marketplace desk fit beside the window?

## Live demo (judges' test links)

| | URL |
|---|---|
| Web editor | https://adaptive-room-planner.vercel.app — "Load sample room", then drag, ask, compare |
| API + OpenAPI docs | DigitalOcean App Platform (`.do/app.yaml`), `/docs` · `GET /health` shows live vs mock per service. The old Vercel API is retired. |

Web: `scripts/deploy_web.sh <api-url>` (Vercel CLI, team `ast18`). API: a Docker image on DigitalOcean App Platform, see [Backend](#backend-api) below (the serverless Vercel API was retired: usd-core does not fit in a function).

## One-command setup

```bash
git clone https://github.com/hhwolf/divhacks && cd divhacks
make setup          # python venv (.venv) + pnpm install
make api            # FastAPI on :8000  (docs at http://localhost:8000/docs)
make web            # Vite editor on :5173
```

Everything runs in **mock mode with zero env vars and no network**: the JSON store lives in `.data/`, files in `.data/blob/`, and Gemini/Backboard return deterministic fixtures. Copy `.env.example` to `.env` and set `MOCK_MODE=false` plus the four required keys to run live (`GET /health` shows live vs mock per service).

```bash
make test           # pnpm typecheck + lint + vitest, then pytest (incl. TS/Python parity on fixtures/validation)
make bench          # validation p95, room-load, import and agent timings → .data/bench.json
make demo           # headless 3-minute demo via Playwright + API (must never fail)
make e2e            # 14 real-pointer editor checks in Chromium (needs api + web running)
make docker-api     # build + run the API image (amd64) with .env
make seed           # upload preset GLBs to Vercel Blob and seed them into Atlas (live keys)
make fps            # drag frame rate in a headed Chromium at iPhone-landscape proportions → .data/fps.json
make record         # re-record docs/demo/run.mp4 (browser recording of the demo at phone proportions)
make thumbs         # re-render palette thumbnails from the GLBs
make screenshots    # docs/screenshots/iter-N (needs api + web running)
```

Storage picks itself: `MONGODB_URI` → MongoDB Atlas (required in live mode); else a JSON file in `.data/`. `BLOB_READ_WRITE_TOKEN` → Vercel Blob for files (raw USDZ scans, photos, preset GLBs); else `.data/blob/`, served at `/blob/`. `GET /health` reports both.

## Repository layout

| Path | What |
|---|---|
| `apps/web` | Vite + React + react-three-fiber editor. Routes `/`, `/layout/:id`, `/compare/:a/:b`, `/snapshot/:id`, `/thumb/:id` |
| `apps/api` | FastAPI: RoomPlan USDZ ingest, rooms, layouts (base / current / variants), furniture import, agent pipeline, placement solver |
| `apps/mobile` | Expo app (expo-router): Home, Scan (RoomPlan module), Editor (WebView bridge), Ask, Variants, Settings |
| `packages/geometry` | TypeScript fit validation + metrics (source of truth; Python port in `apps/api/app/solver`) |
| `packages/contracts` | JSON Schemas + TS types for skeleton, layout, furniture, plan, bridge, Photon |
| `assets/furniture` | 25 Kenney Furniture Kit GLBs (CC0) + `manifest.json` (real-world dims) + thumbnails |
| `fixtures/` | sample rooms, validation parity suite, canned plans, listing page, Photon payloads |
| `docs/` | specs, reference images, per-iteration screenshots, demo recording |

## Rent Reality Check + guarded payments

The editor's analysis tile now has **Fit / Space / Rent** tabs. Rent check combines the scanned floor polygon, current open-floor metrics, fixture-backed ZIP rent baselines, material/condition penalties, and NYC open-data-style building signals into an explainable estimated fair range. It is intentionally labeled as an estimate, not a legal rent or appraisal.

Mock-first endpoints:

```bash
POST /rent/assess
GET  /rooms/{room_id}/rent-assessment
POST /payments/quote
POST /payments/checkout
POST /webhooks/stripe
```

Payment guardrails block security deposits above one month of rent and application fees above $20. Payments are a non-goal: `STRIPE_*` keys are loaded but Stripe is never called, so quotes are always mock. No escrow or stored card data is implemented.

The agent can answer rent/payment prompts such as “I pay $1600 for this room in 10027. Is that fair?”, “Can I safely send a $500 deposit?”, and “This application fee is $75.” Furniture-planning prompts still use the original Gemini/solver pipeline.

## Running on the phone

1. `cp .env.example .env`, set `EXPO_PUBLIC_API_URL=http://<mac-lan-ip>:8000` and `EXPO_PUBLIC_WEB_URL=http://<mac-lan-ip>:5173`.
2. `cd apps/mobile && npm install`.
3. **Expo Go** (everything except live scan): `npx expo start`, scan the QR.
4. **Dev client with RoomPlan** (iPhone Pro, LiDAR): `npx expo run:ios --device`, then `make mobile`.

The editor screen locks to landscape and embeds the web editor through a typed `postMessage` bridge (`packages/contracts/schemas/bridge.schema.json`).

## Backend (API)

One FastAPI service (`apps/api`) for the iOS scanner and the web editor; iMessage (Photon) runs outside it. Spec: [docs/BACKEND_SPEC.md](docs/BACKEND_SPEC.md);
decisions in [DECISIONS.md](DECISIONS.md) ("Backend v2", "Backend v3").

- **Ingest**: `POST /rooms` takes the RoomPlan `.usdz` (`capturedRoom.export(to:exportOptions: .parametric)`) as multipart field `usdz`. The raw file goes to Blob first, then `usd-core` converts it to the canonical skeleton + a read-only **Base Layout** + the **Current Room** (a fork of Base). A failed conversion is a 422 with a `conversionReport`; re-run it later with `{"usdzUrl": ...}`. Also accepts `sample`, manual `dimensions`, or the legacy `skeleton` JSON. Inspect a real export with `.venv/bin/python apps/api/scripts/inspect_usdz.py <file.usdz> --convert` and save one as `fixtures/rooms/real_scan.usdz` (the converter test picks it up).
- **Layouts**: `PUT /layouts/{id}` re-checks the hard rules (422 with violations `byItem`) and uses optimistic `version`s (409 when stale); Base is read-only (403). `PATCH` renames, `POST /layouts/{id}/fork`, `POST /layouts/{id}/promote` (the old Current Room stays as "Previous Room, <date>"), `POST /rooms/{id}/restore {target: base|empty}`, `DELETE /rooms/{id}` cascades.
- **Agent (Interior Designer)**: `POST /agent/request {text, roomId?, layoutId?, furnitureId?, link?, photo?}`. Gemini orchestrates: it picks the tool (fit, make space, keep clear, rank, rent check, payment check, clarify) and words the answer in the voice of the `interior-designer` skill (`apps/api/app/agent/designer.md`). The Python solver places (Gemini never outputs coordinates) and returns up to 3 genuinely different options, each saved as a named variant with an explanation and an honest tradeoff; locks from the layout, the plan and Backboard memory always hold.
- **Photon (iMessage)**: the Photon agent is a deliverer. It forwards the text / listing link / photo URL to `POST /agent/request` with no ids (the texter's latest room is used) and sends back `reply` + `links[1]`.
- **Verify**: `make verify` checks every requirement in [docs/BACKEND_SPEC.md](docs/BACKEND_SPEC.md) against the sample rooms and synthetic RoomPlan scans.
- **Validation constants**: `GET /validation/rules` serves `apps/api/rules.json`; Python loads it and a test fails if `packages/geometry/src/constants.ts` drifts.

Deploy (DigitalOcean App Platform, spec in `.do/app.yaml`):

```bash
doctl apps create --spec .do/app.yaml      # builds apps/api/Dockerfile (python:3.11-slim + usd-core), health check GET /health
# set GEMINI_API_KEY, BACKBOARD_API_KEY, MONGODB_URI, BLOB_READ_WRITE_TOKEN as encrypted env vars in the app settings
# Atlas → Network Access → allow 0.0.0.0/0 (App Platform egress); then point api.<name>.tech at the app (CNAME)
```

The image runs with `MOCK_MODE=false` and refuses to start if a required key is missing. CORS allows only the origins in
`FRONTEND_ORIGINS` (`apps/api/app/config.py`); add `https://<name>.tech` there once the domain exists.

## Demo script (3:00)

Setup before walking up: `make api`, `make web`, phone on the same Wi-Fi with the dev client open. Fallback: everything below also runs in mock mode (the request bar calls `POST /agent/request` directly), and `make demo` replays the whole thing headlessly.

| Time | On screen | Spoken line |
|---|---|---|
| 0:00 | Photo of a desk on a stoop | "I bought a desk on Marketplace that didn't fit beside my window. NYC rooms are 100 square feet; you get one shot at carrying furniture up three flights." |
| 0:20 | Phone: RoomPlan scan (live, or the pre-recorded clip in `docs/demo/`) → room appears in the editor as **Current Room** | "One scan, and the room is a digital twin. Walls, door, window, and the furniture I already own." |
| 0:50 | Editor: drag the dresser, rotate it with R, tap the bed → lock | "It plays like a cozy game. The bed is locked: it never moves, whatever I ask for." |
| 1:05 | Drag the dresser into the door swing → red, analysis tile counts the conflict → drag back | "Fit validation runs on every drag: bounds, overlaps, the 90 cm you need in front of a door, a 75 cm edge to get into bed." |
| 1:20 | Phone: iMessage the Marketplace link + "Will this fit beside my window without moving my bed?" | "I don't open an app to ask. I text the room." |
| 1:40 | Reply arrives with a link; **Marketplace Desk** tab animates in; desk sits beside the window, bed untouched | "Gemini read the listing and turned the question into constraints. Backboard remembered the bed rule. Plain Python placed it and the same validator signed off: 2 inches to spare." |
| 2:05 | Second text: "make space for yoga, keep my dresser" → **Yoga corner** variant with the blue zone | "Every answer is a named variant. The Current Room is never overwritten." |
| 2:25 | 🌲 ghost compare, then the compare view: open floor 62 → 55 %, "Added Desk" | "Two layouts side by side, what moved, how much floor I keep. I can buy with confidence." |
| 2:45 | Menu → health chip shows live/mock per service | "Real room, casual input, game-like editing, saved variants. Same solver later checks a 1.5 m wheelchair turning radius or stages an apartment listing." |

Optional rent beat: open the Rent tab, enter ZIP `10027` and rent `$1600`, then run “Rent check.” Say: “Now the scan becomes a price sanity check: it measures the private room, discounts for rats/leaks or rough floors, and warns before you send a deposit or illegal application fee.”

## Devpost blurb

**Adaptive Room Planner — Where did my space go?** (Live Better)

Renters in 100–150 sq ft NYC rooms buy secondhand and guess. We scan the room once with RoomPlan, rebuild the furniture you already own in a cozy isometric editor, and then let you *text* the room: send a Facebook Marketplace link over iMessage and ask "will this fit beside my window without moving my bed?". Gemini turns the listing and the question into structured constraints, Backboard remembers your non-negotiables ("never move the bed"), a Python placement solver finds a spot on a 10 cm grid, and a shared TypeScript/Python fit validator checks bounds, overlaps, door swing clearance, access edges and walkable paths before anything is saved. Every answer becomes a named layout variant next to your untouched Current Room, with open-floor %, conflicts and walkability side by side in a compare view. MongoDB Atlas stores rooms, furniture and variants; everything degrades to an offline mock mode so the demo never depends on Wi-Fi.

Sponsors used: **Photon** (iMessage in/out), **Gemini API** (structured output + listing/photo extraction), **Backboard** (preference memory), **MongoDB Atlas** (storage).

Try it: https://adaptive-room-planner.vercel.app · API docs: `<api-host>/docs` · source: this repo · `make demo` replays the 3-minute script headlessly.

## Future applications

Real-estate staging ("would my king bed fit?"), movers planning the new place with furniture they already own, architects and designers sending clients three named variants, and accessibility checks (1.5 m wheelchair turning radius and clear paths) with the same solver.

## License

Code MIT. Furniture models: Kenney Furniture Kit 2.0, CC0.
