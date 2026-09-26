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

_See the "Demo script" section below (filled in at the demo-ready checkpoint)._

## Devpost blurb

_Filled in at the demo-ready checkpoint._

## Future applications

Real-estate staging ("would my king bed fit?"), movers planning the new place with furniture they already own, architects and designers sending clients three named variants, and accessibility checks (1.5 m wheelchair turning radius and clear paths) with the same solver.

## License

Code MIT. Furniture models: Kenney Furniture Kit 2.0, CC0.
