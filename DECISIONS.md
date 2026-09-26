# DECISIONS.md — assumptions log

Every ambiguity resolved while building, newest at the bottom. Decisions from EXECUTION_PROMPT.md §2 are not repeated here.

## Iteration 0

- **Python 3.13, not 3.12.** The Mac has 3.13.7 via miniconda; FastAPI/pydantic/motor all support it. `uv` is not installed, so the Makefile uses a plain `python3 -m venv .venv`.
- **Expo app is not in the pnpm workspace.** `apps/mobile` installs with `npm install` on its own; pnpm's strict linking breaks Metro/Expo autolinking. Root `pnpm` covers `apps/web` and `packages/*`.
- **Coordinates & rotation.** Origin = min corner of the floor polygon; `x` along wall 0, `z` toward the viewer. Rotation is degrees about vertical; the item's *front* faces `+z` at 0°, `+x` at 90°, `-z` at 180°, `-x` at 270°. Footprint swaps `w`/`d` at 90°/270°.
- **Wall numbering & compass words.** Walls are listed as floor segments in order; doors/windows use `{wall, offset}` from `(x1,z1)` along the wall. For the solver, `north` = wall with min z, `south` = max z, `west` = min x, `east` = max x (by midpoint).
- **GLB scale.** Kenney models are roughly half real size, so each model is scaled *per axis* at load so its bounding box equals the manifest `dims` exactly (the manifest also stores the precomputed `glb.scale` for reference). 25 items shipped (spec said ~20); the extras (yoga mat, mini fridge, moving box) exist for the NYC framing.
- **Kenney has no dresser/wardrobe/nightstand meshes.** `bookcaseClosedWide` → dresser, `bookcaseClosedDoors` → wardrobe, `cabinetBedDrawer` → nightstand, scaled to real dims.
- **Floor items.** Rugs and the yoga mat have `kind: "floor"`: they are excluded from overlap, door clearance, and walkability (you walk on them). They still obey room bounds.
- **`blocked` (cannot save) = any `bounds` or `overlap` violation.** Door clearance and blocked paths are red and count as conflicts, but the layout can still be saved so the user can keep working; the PRD only names bounds as save-blocking.
- **Access-edge rule tolerance.** An edge counts as free when ≥ 70 % of its 0.75 m band is clear, so a nightstand beside a bed's head does not trigger the yellow warning.
- **Window keep-clear is always evaluated** as a warning (items taller than the sill inside a 0.6 m band), rather than only "when the user asked" — it never blocks anything and is cheap to show.
- **Walkability.** `Blocked` if any bed/desk is unreachable from the door via 4-neighbour flood fill on free cells; `Tight` if reachable only through corridors narrower than 0.5 m (erosion radius 2 cells); otherwise `Good`.
- **Largest free rectangle "fits" labels**: queen bed 1.5×2.0, desk and chair 1.2×1.4, yoga mat 0.61×1.83, desk 1.2×0.6, armchair 0.9×0.9, nightstand 0.45×0.4, else "not much".
- **Reachable storage %** = share of storage/dresser/wardrobe items whose 0.75 m front band is ≥ 70 % free.
- **Sample bedroom seed has no desk** (bed locked, nightstand, dresser, low bookshelf, plant) so the Marketplace desk is the first desk that arrives. The PRD's "Current Room with bed locked, desk, dresser" line is read as the state *after* the demo request. The yoga request forks from whichever layout is active (the Marketplace Desk variant during the demo).
- **Reference background colour.** Sampled ref2 is `#B87E58` mid / `#9F6D4C` at the edges (a vignette), darker than the `#D9A56E` guess in the prompt; the CSS uses the sampled values. Ref3 teal samples `#84AA9D` / `#77978C`.
- **Validation fixtures are generated from TypeScript** (`packages/geometry/bench/gen_expectations.ts`) and committed; Python must reproduce them. TS is the source of truth by construction.
- **Compare view renders two read-only scenes** sharing one store (room + furniture) with an `itemsOverride` per side, rather than two stores.

## Iteration 0 — backend (FastAPI + solver)

- **Rounding parity.** JS `Math.round` rounds half toward +∞, Python's `round` is banker's. Every rounding in the Python solver goes through `js_round` (`floor(v + 0.5)`) so grid sizing, metrics and imperial formatting match TS bit-for-bit.
- **Photon real-mode sending needs a relay.** The Spectrum OpenAPI (`spectrum.photon.codes`) is a management plane only (webhooks, lines, tokens); runtime sending goes through the `spectrum-ts` SDK. Live `send_text` POSTs `{to, from, text}` with a Bearer key to `{PHOTON_BASE_URL}/messages`, the shape a thin spectrum-ts relay would expose. Mock mode (outbox at `.data/photon_outbox.jsonl`) is what the demo uses.
- **Photon inbound shape & signatures.** Body `{event:"messages", space{…}, message{id, direction, sender{id}, content{type:"text",text}|{type:"attachment",…}}}`; `message.id` is the idempotency key. Signature = `X-Spectrum-Signature: v0=hex(HMAC-SHA256(secret, "v0:{ts}:{body}"))` with `X-Spectrum-Timestamp` (5-minute skew) — Standard-Webhooks headers are accepted too. Our fixture shape and any `from/text`-like body are also normalised.
- **Backboard.** Base `https://app.backboard.io/api`, header `X-API-Key`; memories live under an *assistant*: `POST/GET /assistants/{id}/memories`, `POST …/memories/search`. Live mode lazily creates one assistant per demo user and stores its id on the user doc.
- **"Live" per service** = `MOCK_MODE=false` **and** that service's key present. Mongo is live whenever `MONGODB_URI` is set. `/health.mode` is `live` / `mock` / `mixed` across Gemini + Backboard + Photon.
- **Solver candidates are wall-flush only** (10 cm edge grid, back to the wall). A *named* wall restricts candidates to that wall so "won't fit on the window wall" rejections are honest; an unnamed wall scans all four. Zone phrases may list alternatives with " or ". "Beside window" = closest to the window span with a penalty for standing in front of it; the reply's gap is the smaller along-wall clearance to the nearest obstacle.
- **Clear zones** are placed at the corner of the validator's largest free rectangle, oriented to fit; if the requested size can't fit, the largest rectangle is used and the reply says so.
- **`add` actions** resolve to the request's imported `furnitureId` unless the plan names a *different* exact catalog id; new instance ids are `<furnitureId>_<n>`. A link-only message is treated as "Will this fit in my room?".
- **Webhook room resolution.** The demo user is keyed by phone; if that user has no room, the newest room overall is used so the first iMessage after "Load sample room" hits the right room.
- **HTTP semantics.** `PUT` on a Current Room requires `source:"editor"` (403 otherwise), renaming it is 409, blocked layouts are 422 with the violation list, deleting a Current Room is 409.
- **Mock listing extraction** returns the fixed desk (1.2 × 0.6 × 0.75 m, $80) regardless of page content; the OpenGraph/JSON-LD/regex parser feeds Gemini in live mode and is tested on its own. Local `fixtures/listings/*` URLs are read from disk so the demo works offline.
- **`python-multipart`** added for the photo upload route.
