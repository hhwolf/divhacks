# Adaptive Room Planner — "Where did my space go?"

DivHacks 2026 · **Live Better** track. Scan your NYC room once, text furniture ideas over iMessage, and rearrange your real room like a cozy top-down game before you buy or haul anything up three flights.

> Renter in a 100–150 sq ft room, buying secondhand, wants one more thing to fit. Bed can't move. Will the Marketplace desk fit beside the window?

## Live demo (judges' test links)

| | URL |
|---|---|
| Web editor | https://adaptive-room-planner.vercel.app — "Load sample room", then drag, ask, compare |
| API + OpenAPI docs | https://adaptive-room-planner-api.vercel.app/docs · `GET /health` shows live vs mock per service |
| Photon webhook (real mode) | `POST https://adaptive-room-planner-api.vercel.app/webhooks/photon` |

Redeploy: `scripts/deploy_api.sh` then `scripts/deploy_web.sh https://adaptive-room-planner-api.vercel.app` (Vercel CLI, logged in, team `ast18`). The deployed API persists to Supabase when `SUPABASE_URL` and a server-only key are configured, otherwise it can fall back to Vercel Blob or local JSON. `scripts/sync_env_to_vercel.sh` pushes real-mode keys from `.env` and redeploys.

## One-command setup

```bash
git clone https://github.com/hhwolf/divhacks && cd divhacks
make setup          # python venv (.venv) + pnpm install
make api            # FastAPI on :8000  (docs at http://localhost:8000/docs)
make web            # Vite editor on :5173
```

Everything runs in **mock mode with zero env vars and no network**: the JSON store lives in `.data/`, Gemini/Backboard/Photon return deterministic fixtures. Copy `.env.example` to `.env` and add keys to switch each service to its real implementation independently (`GET /health` shows live vs mock per service).

Channel split: **Photon/iMessage brings new furniture into the room** from listing links or photos, checks it against the saved scan, and creates a layout variant. The **in-app AI assistant arranges the room**: reading corners, yoga space, window placement, locked-item rules, and other spatial changes inside the existing 3D room.

```bash
make test           # pnpm typecheck + lint + vitest, then pytest (incl. TS/Python parity on fixtures/validation)
make bench          # validation p95, room-load, import and agent timings → .data/bench.json
make demo           # headless 3-minute demo via Playwright + API (must never fail)
make e2e            # 14 real-pointer editor checks in Chromium (needs api + web running)
make photon         # post fixtures/photon/*.json to the local webhook and print the replies
make fps            # drag frame rate in a headed Chromium at iPhone-landscape proportions → .data/fps.json
make record         # re-record docs/demo/run.mp4 (browser recording of the demo at phone proportions)
make thumbs         # re-render palette thumbnails from the GLBs
make screenshots    # docs/screenshots/iter-N (needs api + web running)
```

Storage picks itself: `SUPABASE_URL` + `SUPABASE_SECRET_KEY` → Supabase REST/Postgres; else `BLOB_READ_WRITE_TOKEN` → Vercel Blob snapshots (what the deployed API can use so every serverless instance sees the same rooms); else a JSON file in `.data/`. `GET /health` reports which one is active.

Supabase setup: create this table once in the SQL editor, then add `SUPABASE_URL` and the server-only secret key to `.env` / Vercel env.

```sql
create table if not exists public.arp_documents (
  collection text not null,
  id text not null,
  room_id text,
  user_id text,
  phone text,
  doc jsonb not null,
  seq bigint not null,
  primary key (collection, id)
);
create index if not exists arp_documents_collection_seq_idx on public.arp_documents (collection, seq);
create index if not exists arp_documents_room_idx on public.arp_documents (collection, room_id);
create index if not exists arp_documents_phone_idx on public.arp_documents (collection, phone);
grant select, insert, update, delete on public.arp_documents to service_role;
```

## Repository layout

| Path | What |
|---|---|
| `apps/web` | Vite + React + react-three-fiber editor. Routes `/`, `/layout/:id`, `/compare/:a/:b`, `/snapshot/:id`, `/thumb/:id` |
| `apps/api` | FastAPI: rooms, layouts, furniture import, agent pipeline, placement solver, Photon webhook |
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
POST /payments/supabase-sync
```

Payment guardrails block security deposits above one month of rent and application fees above $20. Supabase stores the guarded quote/payment record when configured, but no card processor, escrow, wire, crypto, or cash-transfer flow is implemented.

The agent can answer rent/payment prompts such as “I pay $1600 for this room in 10027. Is that fair?”, “Can I safely send a $500 deposit?”, and “This application fee is $75.” Furniture-planning prompts still use the original Gemini/solver pipeline.

## Running on the phone

1. `cp .env.example .env`, set `EXPO_PUBLIC_API_URL=http://<mac-lan-ip>:8000` and `EXPO_PUBLIC_WEB_URL=http://<mac-lan-ip>:5173`.
2. `cd apps/mobile && npm install`.
3. **Expo Go** (everything except live scan): `npx expo start`, scan the QR.
4. **Dev client with RoomPlan** (iPhone Pro, LiDAR): `npx expo run:ios --device`, then `make mobile`.
5. **TestFlight** (Xcode-free, cloud build): `npx eas-cli build --platform ios --profile production` then `npx eas-cli submit --platform ios --profile production --latest`. The first build needs an interactive Apple login (2FA); App Store Connect app id 6816528380, team 59MGA3685P are in `eas.json`.

The editor screen locks to landscape and embeds the web editor through a typed `postMessage` bridge (`packages/contracts/schemas/bridge.schema.json`).

### Scanning a real room (LiDAR iPhone Pro / iPad Pro, iOS 16+)

The Scan screen hosts Apple's `RoomCaptureView` through the local Expo module in `apps/mobile/modules/roomplan` (Swift). Flow on device:

1. **Start** — the app asks for camera access (first time), then runs a `RoomCaptureSession` with coaching on. Walk the room slowly; the chip shows Apple's instructions ("Move closer to the wall", "Slow down") and live wall / door / window / object counts.
2. **Stop** — RoomPlan post-processes the capture; the promise resolves only when the final `CapturedRoom` arrives (30 s timeout), then it is exported to our skeleton JSON: walls projected to the floor plane and chained into a closed polygon, doors/windows as offsets along their parent wall, detected furniture mapped to the catalog (bed → `bed_double`/`bed_single` by width, table near a chair → `desk`, storage → `wardrobe`/`dresser` by height, sofa, chair, television → `tv_stand`).
3. **Use this scan** → room setup (space types → elements) → the clean scanned room opens in the editor. Detected furniture stays on the room as `detectedObjects`.

If the camera is denied the screen shows an "Open Settings" button. Without LiDAR (or in Expo Go / the Simulator) the screen falls back to sample room, typed dimensions, or pasted RoomPlan JSON — `fixtures/rooms/roomplan-export-sample.json` is a hand-authored export in exactly the shape the module produces.

## Photon (iMessage) in real mode

Photon is the external furniture input channel. Text the line a Facebook Marketplace, IKEA, Amazon, or other store link/photo plus a fit question; the webhook imports the item, checks it against the saved room, and replies with a new layout variant link. Spatial planning requests without new furniture belong in the in-app assistant.

```bash
ngrok http 8000           # public URL for the webhook
# set SPECTRUM_PROJECT_ID + SPECTRUM_PROJECT_SECRET (or PHOTON_API_KEY) plus PHOTON_WEBHOOK_SECRET
# in the Photon dashboard: webhook → https://<ngrok>/webhooks/photon
.venv/bin/python scripts/simulate_photon.py     # posts fixtures/photon/*.json to the local webhook (works in mock mode too)
```

## Demo script (3:00)

Setup before walking up: `make api`, `make web`, phone on the same Wi-Fi with the dev client open, `ngrok http 8000` if Photon is live. Fallback: everything below also runs in mock mode with `scripts/simulate_photon.py` instead of a real iMessage, and `make demo` replays the whole thing headlessly.

| Time | On screen | Spoken line |
|---|---|---|
| 0:00 | Photo of a desk on a stoop | "I bought a desk on Marketplace that didn't fit beside my window. NYC rooms are 100 square feet; you get one shot at carrying furniture up three flights." |
| 0:20 | Phone: RoomPlan scan (live, or the pre-recorded clip in `docs/demo/`) → room appears in the editor as **Current Room** | "One scan, and the room is a digital twin. Walls, door, window, and the furniture I already own." |
| 0:50 | Editor: drag the dresser, rotate it with R, tap the bed → lock | "It plays like a cozy game. The bed is locked: it never moves, whatever I ask for." |
| 1:05 | Drag the dresser into the door swing → red, analysis tile counts the conflict → drag back | "Fit validation runs on every drag: bounds, overlaps, the 90 cm you need in front of a door, a 75 cm edge to get into bed." |
| 1:20 | Phone: iMessage the Marketplace link + "Will this fit beside my window without moving my bed?" | "I don't open an app to ask. I text the room." |
| 1:40 | Reply arrives with a link; **Marketplace Desk** tab animates in; desk sits beside the window, bed untouched | "Gemini read the listing and turned the question into constraints. Backboard remembered the bed rule. Plain Python placed it and the same validator signed off: 2 inches to spare." |
| 2:05 | In-app assistant: "make space for yoga, keep my dresser" → **Yoga corner** variant with the blue zone | "Furniture comes in over text. Room changes happen right inside the app, and every answer is a named variant. The Current Room is never overwritten." |
| 2:25 | 🌲 ghost compare, then the compare view: open floor 62 → 55 %, "Added Desk" | "Two layouts side by side, what moved, how much floor I keep. I can buy with confidence." |
| 2:45 | Menu → health chip shows live/mock per service | "Real room, casual input, game-like editing, saved variants. Same solver later checks a 1.5 m wheelchair turning radius or stages an apartment listing." |

Optional rent beat: open the Rent tab, enter ZIP `10027` and rent `$1600`, then run “Rent check.” Say: “Now the scan becomes a price sanity check: it measures the private room, discounts for rats/leaks or rough floors, and warns before you send a deposit or illegal application fee.”

## Devpost blurb

**Adaptive Room Planner — Where did my space go?** (Live Better)

Renters in 100–150 sq ft NYC rooms buy secondhand and guess. We scan the room once with RoomPlan, rebuild the furniture you already own in a cozy isometric editor, and split the AI workflow into two natural channels: text a Facebook Marketplace/IKEA/Amazon listing or photo over iMessage to bring new furniture into the room, then use the in-app assistant for layout changes like "make space for yoga" or "place the desk near the window." Gemini turns listings and spatial requests into structured constraints, Backboard remembers your non-negotiables ("never move the bed"), a Python placement solver finds a spot on a 10 cm grid, and a shared TypeScript/Python fit validator checks bounds, overlaps, door swing clearance, access edges and walkable paths before anything is saved. Every answer becomes a named layout variant next to your untouched Current Room, with open-floor %, conflicts and walkability side by side in a compare view. Supabase stores rooms, furniture, rent assessments and variants when configured; everything degrades to an offline mock mode so the demo never depends on Wi-Fi.

Sponsors used: **Photon** (iMessage in/out), **Gemini API** (structured output + listing/photo extraction), **Backboard** (preference memory), **Supabase** (storage).

Try it: https://adaptive-room-planner.vercel.app · API docs: https://adaptive-room-planner-api.vercel.app/docs · source: this repo · `make demo` replays the 3-minute script headlessly.

## Future applications

Real-estate staging ("would my king bed fit?"), movers planning the new place with furniture they already own, architects and designers sending clients three named variants, and accessibility checks (1.5 m wheelchair turning radius and clear paths) with the same solver.

## License

Code MIT. Furniture models: Kenney Furniture Kit 2.0, CC0.
