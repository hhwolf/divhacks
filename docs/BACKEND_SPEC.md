# Adaptive Room Planner: Backend Spec (v3)

The build spec for the main backend (`apps/api`). v3 = the v2 orchestration prompt plus the team's decisions: Gemini is the
orchestrator, the Interior Designer follows the `interior-designer` skill, the Photon agent is a deliverer, rent and payment checks
are in scope, field names stay as the web/mobile clients use them, and the serverless Vercel API is retired. The reasoning behind
each choice is in [DECISIONS.md](../DECISIONS.md) ("Backend v2" and "Backend v3").

## Role

- One FastAPI service. Three clients: the iOS scanner (Expo + RoomPlan module), the web editor (react-three-fiber), and the Photon
  agent that relays iMessages.
- Four services: Gemini, Backboard, MongoDB Atlas, Vercel Blob. Stripe and Spectrum keys are loaded, never called.

## Pipeline

```
[iPhone scan] -> RoomPlan .parametric USDZ -> POST /rooms (multipart)
  -> Blob (raw file first) -> usd-core conversion -> canonical skeleton + Base Layout + Current Room
  -> editor draws the Current Room
  -> the person either
       (a) drags / rotates / locks / adds / removes             -> PUT /layouts/{id} (versioned)
       (b) asks the Interior Designer (app or iMessage via Photon) -> POST /agent/request -> up to 3 named variants
  -> editor draws the result -> loop
```

Rules that never bend:

- The skeleton (walls, doors, windows, floor polygon) is immutable after ingest.
- The Base Layout ("Original Room") is read-only: the way back to the scanned room.
- The agent never writes the Base Layout or the Current Room. Every placement result is a new named variant.
- Gemini never outputs coordinates. The Python solver places; the browser validator has the final say for what the user sees.
- The server re-checks the hard rules on every save.

## Units and coordinates

Meters; floor plane x/z, y up; rotation in degrees about y (0/90/180/270; rotation 0 means the item's front faces +z). Floor polygon
min x and min z are 0. An item's (x, z) is its footprint center.

## Data model (MongoDB Atlas)

Field names are the ones the web editor, the TS validator and the mobile app already use; v2 names were added alongside, not swapped in.

**rooms**: `id, userId, name, source: scan|sample|manual, usdzUrl, thumbnailUrl, baseLayoutId, currentLayoutId, conversion, createdAt, updatedAt`,
`skeleton: {walls:[{id, x1,z1,x2,z2, height, thickness?}], doors:[{id, wall, wallId, offset, center, width, height, swing, hinge, opening?}],
windows:[{id, wall, wallId, offset, center, width, sillHeight, height}], floorPolygon, dimensions:{l,w,h}, ceilingHeight, outlets?}`.
`wall`+`offset` and `wallId`+`center` state the same fact. Openings are doors with `opening: true, swing: "out"` (clearance, no swing arc).

**furniture**: `id, name, category (bed|desk|seating|storage|table|decor|imported|other), kind (validator rule kind), dims{w,d,h}, glbUrl,
thumbUrl, photoUrl?, source (preset|link|photo|manual|scan), price, estimated, userId (null for presets), roomId (scanned items only)`.

**layouts**: `id, roomId, name, kind: base|current|variant, isCurrent (= kind == current), parentLayoutId, items:[{id, furnitureId, x, z,
rotation, locked, color?}], zones:[{type: clear|keep_clear, label, x, z, w, d}], metrics:{openFloor, openFloorPct, conflicts, walkability,
reachableStorage, largestFreeRect, warnings[]}, createdBy, requestText, version, createdAt, updatedAt`. Exactly one base and one current per room.

**users**: `id, displayName, memories (local mirror), backboardAssistantId, createdAt`. One shared demo user.

**agent_requests**: `id, userId, roomId, sourceLayoutId, resultLayoutId, resultLayoutIds, requestText, attachments, channel (app|imessage),
intent, geminiPlan (raw, per attempt), plan, solverAttempts, validation, status: ok|rejected|clarify, reply, latencyMs, createdAt`.

**rent_assessments**, **payment_quotes**: see "Rent and payment checks".

## Ingest (USDZ -> canonical JSON)

`POST /rooms` (multipart field `usdz`) takes the file from `capturedRoom.export(to:exportOptions: .parametric)`. Also accepted: `usdzUrl`
(re-convert a stored scan), `sample`, manual `dimensions` (+ `doors`/`windows`), or the legacy `skeleton` + `objects` JSON.

1. Upload the raw USDZ to Blob first (`scans/<roomId>.usdz`); a failed conversion never loses the scan.
2. `Usd.Stage.Open`; units from `metersPerUnit` (unauthored = meters, not USD's 0.01 fallback); Z-up maps to Y-up.
3. Classify prims by name prefix (`Wall*`, `Door*`, `Window*`, `Opening*`, `Floor*`, the 16 RoomPlan object categories), never by parent
   path; skip `*_grp` containers, prims without geometry, and nested duplicates.
4. Each element's box = its leaf geometry's local extents mapped into the element frame (not a world AABB).
5. Walls, doors/windows/openings (nearest wall), floor polygon (Floor prim, else wall endpoints), objects (category, dims, yaw to 90°).
6. Normalize: longest wall on +x at min z (ties: window wall, then no door), floor polygon min corner at the origin.
7. Sanity: >= 3 walls, floor 3–100 m², ceiling 2–4 m; else 422 `{message, conversionReport}` with `usdzUrl`.
8. Base Layout: furniture -> nearest preset scaled to the scanned size (`source: scan`); fixtures -> `category: other`, locked. Boxes
   poking <= 10 cm through a wall are nudged in; chairs tucked under a table are pulled out; remaining hard problems are listed in
   `conversion.warnings`. Current Room = fork of Base.

`apps/api/scripts/inspect_usdz.py <file> --convert` prints the prim tree and the conversion. Save one real export as
`fixtures/rooms/real_scan.usdz`; the converter test uses it when present.

## Editor path

- `GET /rooms/{id}`, `GET /layouts/{id}` (layout + catalog entries + validation).
- `PUT /layouts/{id}` `{items, zones, version, source}`: 403 on the Base Layout; the Current Room needs `source: "editor"`; 409 on a stale
  `version` (compare-and-set); hard-rule failures are 422 with `violations` and `byItem`; soft rules land in `metrics.warnings`.
- The web editor sends `version`, and on 409 reloads the latest version and keeps the local edit one redo away. It treats the Base Layout
  as read-only.

## Interior Designer agent (`POST /agent/request`)

Body: `{text, roomId?, layoutId?, furnitureId?, link?, photo?, channel}`. Without ids the user's most recently used room and its Current
Room are used (the Photon path). Gemini is the orchestrator; the designer's voice and planning rules come from `apps/api/app/agent/designer.md`,
adapted from the `interior-designer` skill.

- **Stage 0, context**: skeleton, source layout with locks, catalog, Backboard memory and the room's recent requests (prefixed to every
  Gemini call). A `link` or photo is imported first.
- **Stage 1, Gemini picks the tool** (Pydantic `GeminiPlan`, no coordinate fields): `fit_item`, `make_space`, `keep_clear`, `rank_variants`,
  `rent_check` (with `rent`), `payment_check` (with `payment`), or `clarify` (one question).
- **Stage 2, the tool runs**:
  - Placement solver: 10 cm occupancy grid; locked = layout locks ∪ plan locks ∪ Backboard "never move ..." rules; candidates flush to
    walls and on open floor, all rotations; front-use pieces (desk chair side, drawers) need their 0.75 m band free; filters
    `adjacent`/`keep_clear`; ranking: no new conflict > constraints > fewer new warnings > closeness + designer tie-breakers (keep one open
    rectangle, no desk chair with its back to the door). Up to 3 genuinely different options (>= 1 m apart, or the recommended spot
    turned 90°); a good wall spot that ignores `adjacent` may fill a slot, labelled as such. `make_space` slides the zone over the grid
    and clears it with the fewest moves (<= 2). If nothing passes, the violations go back to Gemini once and the tools re-run; still
    nothing is `rejected` with the nearest miss ("12 cm too wide for the window wall; try the wall by the door?").
  - Ranker: Gemini's ranking of saved layouts, or a validator-based score; no new variant.
  - Rent check / payment guardrails: see below.
- **Stage 3**: each option becomes a named variant (recommended first); stated preferences go back to Backboard.
- **Stage 4, Gemini words it** as the Interior Designer from the solver's facts (`Narration`: room summary, per-option name, explanation,
  tradeoff, recommended, one-sentence reply). A deterministic draft in the same voice is used in mock mode or if Gemini fails.

Response: `{status, reply, roomSummary, options:[{variantName, layoutId, explanation, tradeoff, moved, placement, moves, zones, relaxed,
validation:{ok, warnings, open_floor_pct}}], recommended, layoutId, layout, plan (with the recommended placement), links, ranking,
assessment?, quote?, violations, requestId}`.

### Photon (iMessage) deliverer contract

The Photon agent runs outside this service. It receives the iMessage (text, a listing link, a photo) and calls
`POST /agent/request {text, link?, photo?: <https url>, channel: "imessage"}`, then texts back `reply` + `links[1]` (the web editor link
to the recommended variant). A `clarify` status means `reply` is a question to send as is.

## Rent and payment checks

- `POST /rent/assess` (HousingProfile + `layoutId`) and `GET /rooms/{id}/rent-assessment`: a deterministic fair-rent range from the
  scanned floor area, open floor, ZIP baselines, condition issues and building signals (`fixtures/housing`). Always labelled an estimate.
- `POST /payments/quote`, `POST /payments/checkout`: NYC guardrails. Deposits above one month of rent and application fees above $20 are
  blocked (409 on checkout). Quotes are always `mock`: Stripe is never called, no card data is stored, no escrow.
- `POST /webhooks/stripe`: acknowledged only.
- Through the agent, Gemini routes "is my rent fair", "can I send this deposit", "this application fee" to these checks.

## Fit validation

`packages/contracts/rules.json` is the one source: the TS validator imports it, the API loads it and serves it at `GET /validation/rules`.

| Rule | Severity | On failure |
|---|---|---|
| Room bounds | hard (blocks save) | item red |
| Overlap (rugs/mats excluded) | hard (blocks save) | both named |
| Locked items | hard (agent/solver) | plan rejected |
| Door swing + 0.9 m | conflict | counted, red keep-clear overlay |
| Access edges (0.75 m) | warning | yellow overlay |
| Window keep-clear | warning | yellow |
| Requested clear zone | warning | largest zone reported |
| Walkable path door -> beds/desks | warning | "Path blocked to desk" |

## Furniture catalog

`GET /furniture?category=`, `POST /furniture` (manual dims), `POST /furniture/from-link` (< 10 s; blocked/login walls -> 422 "upload a
screenshot or enter the dimensions"), `POST /furniture/from-photo` (photo to Blob, Gemini vision, `estimated: true`). `seed_presets.py`
uploads preset GLBs to Blob and seeds them into Atlas.

## Endpoints

| Method and path | Purpose |
|---|---|
| `POST /rooms` | USDZ (converted server-side), `usdzUrl`, sample, manual dims, or legacy skeleton JSON |
| `GET /rooms?userId=` / `GET /rooms/{id}` / `PATCH /rooms/{id}` / `DELETE /rooms/{id}` | list, read, rename, cascade delete |
| `POST /rooms/{id}/restore {target: base\|empty, name}` | back to the original, as a new variant |
| `GET /layouts/{id}` / `PUT` / `PATCH` / `DELETE` | read, versioned save, rename, delete a variant (403 base, 409 current) |
| `POST /layouts/{id}/fork` / `POST /layouts/{id}/promote` | duplicate; make a variant the Current Room (old one becomes "Previous Room, <date>") |
| `GET /layouts/{a}/compare/{b}` | metric deltas + moved / added / removed |
| `GET /furniture` / `POST /furniture` / `from-link` / `from-photo` | catalog + import |
| `POST /agent/request` | Interior Designer (app and Photon) |
| `POST /rent/assess` / `GET /rooms/{id}/rent-assessment` / `POST /payments/quote` / `POST /payments/checkout` / `POST /webhooks/stripe` | rent and payment checks |
| `GET /validation/rules` / `GET /health` | shared constants; health check |

## Environment

Only these secrets (pydantic-settings, `SecretStr`, never logged or returned): `GEMINI_API_KEY`, `BACKBOARD_API_KEY`, `MONGODB_URI`,
`BLOB_READ_WRITE_TOKEN` (required when `MOCK_MODE=false`), `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `SPECTRUM_PROJECT_ID`,
`SPECTRUM_PROJECT_SECRET` (loaded, not called). `MOCK_MODE` (default true) runs everything offline. Non-secret config is in
`apps/api/app/config.py` (CORS origins, Gemini model, db name) and `packages/contracts/rules.json`.

## Deploy

DigitalOcean App Platform from `.do/app.yaml`: `apps/api/Dockerfile` (python:3.11-slim + usd-core, amd64 only), health check
`GET /health`, `MOCK_MODE=false`. CORS allows only `FRONTEND_ORIGINS`; add `https://<name>.tech` when the domain is chosen, and point
`api.<name>.tech` at the app. Atlas network access: allow App Platform egress. The serverless Vercel API is retired; the web editor still
deploys to Vercel as a static site.

## Fallbacks

No LiDAR: sample room or manual dims. Conversion fails: 422 + report, raw USDZ kept, re-run with `usdzUrl`. Gemini forgets a lock:
irrelevant, the solver enforces locks. Gemini down: the planner attempt counts as failed; wording falls back to the draft. Listing
blocks scraping: photo or manual dims. Backboard down: run without memory, log it.
