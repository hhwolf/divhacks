# Adaptive Room Planner — "Where did my space go?"

DivHacks 2026 · **Live Better** track. Scan your NYC room once, text furniture ideas over iMessage, and rearrange your real room like a cozy top-down game before you buy or haul anything up three flights.

> Renter in a 100–150 sq ft room, buying secondhand, wants one more thing to fit. Bed can't move. Will the Marketplace desk fit beside the window?

## One-command setup

```bash
git clone https://github.com/hhwolf/divhacks && cd divhacks
make setup          # python venv (.venv) + pnpm install
make api            # FastAPI on :8000  (docs at http://localhost:8000/docs)
make web            # Vite editor on :5173
```

Everything runs in **mock mode with zero env vars and no network**: the JSON store lives in `.data/`, Gemini/Backboard/Photon return deterministic fixtures. Copy `.env.example` to `.env` and add keys to switch each service to its real implementation independently (`GET /health` shows live vs mock per service).

```bash
make test           # pnpm typecheck + lint + vitest, then pytest (incl. TS/Python parity on fixtures/validation)
make bench          # validation p95, room-load, import and agent timings → .data/bench.json
make demo           # headless 3-minute demo via Playwright + API (must never fail)
make thumbs         # re-render palette thumbnails from the GLBs
make screenshots    # docs/screenshots/iter-N (needs api + web running)
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

## Running on the phone

1. `cp .env.example .env`, set `EXPO_PUBLIC_API_URL=http://<mac-lan-ip>:8000` and `EXPO_PUBLIC_WEB_URL=http://<mac-lan-ip>:5173`.
2. `cd apps/mobile && npm install`.
3. **Expo Go** (everything except live scan): `npx expo start`, scan the QR.
4. **Dev client with RoomPlan** (iPhone Pro, LiDAR): `npx expo run:ios --device`, then `make mobile`.

The editor screen locks to landscape and embeds the web editor through a typed `postMessage` bridge (`packages/contracts/schemas/bridge.schema.json`).

## Photon (iMessage) in real mode

```bash
ngrok http 8000           # public URL for the webhook
# in the Photon dashboard: webhook → https://<ngrok>/webhooks/photon ; put the signing secret in PHOTON_WEBHOOK_SECRET
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
| 2:05 | Second text: "make space for yoga, keep my dresser" → **Yoga corner** variant with the blue zone | "Every answer is a named variant. The Current Room is never overwritten." |
| 2:25 | 🌲 ghost compare, then the compare view: open floor 62 → 55 %, "Added Desk" | "Two layouts side by side, what moved, how much floor I keep. I can buy with confidence." |
| 2:45 | Menu → health chip shows live/mock per service | "Real room, casual input, game-like editing, saved variants. Same solver later checks a 1.5 m wheelchair turning radius or stages an apartment listing." |

## Devpost blurb

**Adaptive Room Planner — Where did my space go?** (Live Better)

Renters in 100–150 sq ft NYC rooms buy secondhand and guess. We scan the room once with RoomPlan, rebuild the furniture you already own in a cozy isometric editor, and then let you *text* the room: send a Facebook Marketplace link over iMessage and ask "will this fit beside my window without moving my bed?". Gemini turns the listing and the question into structured constraints, Backboard remembers your non-negotiables ("never move the bed"), a Python placement solver finds a spot on a 10 cm grid, and a shared TypeScript/Python fit validator checks bounds, overlaps, door swing clearance, access edges and walkable paths before anything is saved. Every answer becomes a named layout variant next to your untouched Current Room, with open-floor %, conflicts and walkability side by side in a compare view. MongoDB Atlas stores rooms, furniture and variants; everything degrades to an offline mock mode so the demo never depends on Wi-Fi.

Sponsors used: **Photon** (iMessage in/out), **Gemini API** (structured output + listing/photo extraction), **Backboard** (preference memory), **MongoDB Atlas** (storage).

Try it: web editor (Vercel URL in the submission) · source: this repo · `make demo` replays the 3-minute script headlessly.

## Future applications

Real-estate staging ("would my king bed fit?"), movers planning the new place with furniture they already own, architects and designers sending clients three named variants, and accessibility checks (1.5 m wheelchair turning radius and clear paths) with the same solver.

## License

Code MIT. Furniture models: Kenney Furniture Kit 2.0, CC0.
