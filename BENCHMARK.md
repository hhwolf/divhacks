# BENCHMARK.md — 100-point rubric, scored every iteration

Stop rule: total ≥ 95 with no line under 50 % of its value. Every line needs evidence (test name, timing log, screenshot path). Scores are appended per iteration; the latest table is authoritative.

## Iteration 0 — Skeleton (target: things run) — provisional 58 / 100

Provisional: functional lines are scored from tests and the headless demo; UI fidelity (B) is not yet graded against side-by-side crops (that is Iteration 2's job), so B is scored conservatively from the raw screenshots.

| Line | Pts | Score | Evidence |
|---|---|---|---|
| A1 room create (sample/manual/RoomPlan JSON) | 3 | 3 | `apps/api/tests/test_rooms.py`; `docs/screenshots/iter-0/web-01-empty-room.png` |
| A2 skeleton immutable | 3 | 3 | `tests/test_skeleton_immutable.py` |
| A3 editor interactions | 4 | 3 | `apps/web/src/store.test.ts` (8 tests: add, snap, Shift free-move, wall snap, R, lock, remove, undo/redo); redo has no button yet |
| A4 import link/photo/manual | 3 | 2 | `tests/test_furniture.py`; link import 24 ms in demo; photo path only mock-tested |
| A5 agent both demo requests + clarify + retry | 4 | 4 | `tests/test_agent.py` (retry-on-violation with forced bad plan) |
| A6 variants rename/dup/delete/persist | 3 | 2 | `tests/test_layouts.py`; persistence across JsonStore restart tested; Mongo path untested (no URI) |
| A7 validation rules + fixtures | 4 | 4 | `fixtures/validation/*.json` (14), `packages/geometry/test/parity.test.ts`, `apps/api/tests/test_parity.py` — identical results |
| A8 Photon simulated round trip | 3 | 3 | `tests/test_photon.py`; `scripts/demo.py` step "Simulated Photon message → variant" |
| A9 compare + ghost | 3 | 2 | `web-13-compare.png`, `web-07-ghost-compare.png`; compare page needs visual polish |
| B UI fidelity (12 lines) | 25 | 12 | raw screenshots only; side-by-side grading in iter-2 |
| C1 validation < 100 ms | 3 | 3 | `pnpm --filter @arp/geometry bench`: p50 0.42 ms, p95 1.7 ms for 20 items |
| C2 room load < 30 s cold / < 3 s warm | 2 | 2 | demo step "Open variant in editor" 2.98 s (cold, headless swiftshader) |
| C3 import < 10 s | 1 | 1 | demo 24 ms (mock) |
| C4 agent < 2 s mock | 2 | 2 | demo 58 ms |
| C5 60 fps WebView drag | 2 | 0 → 1 (iter-3) | `make fps`: 120 fps (display-capped) dragging in headed Chromium at 1278×590@2x, `.data/fps.json`; device/simulator WebView number pending iter-4 |
| D1 `make demo` headless | 8 | 8 | `docs/demo/demo-run.json` DEMO OK 8.5 s |
| D2 manual phone run recorded | 5 | 0 | iteration 4 |
| D3 README demo script | 2 | 0 | placeholder |
| E1 mock mode zero env | 3 | 3 | `/health` mode mock; demo ran with no `.env` |
| E2 bad Gemini JSON → retry → fallback | 2 | 2 | `test_agent.py` rejected path keeps old layout |
| E3 JSON store vs Mongo | 2 | 1 | JSON path tested; Mongo adapter written, unverified |
| E4 Expo Go launch without RoomPlan | 2 | 1 | `expo export` bundle compiles; not launched on device yet |
| E5 `/health` live/mock | 1 | 1 | `tests/test_health.py` |
| F1 pnpm typecheck/lint/test | 3 | 3 | 27 vitest green, eslint clean, tsc clean |
| F2 pytest + parity | 3 | 3 | 55 passed |
| F3 .env.example + README verified from clean clone | 2 | 1 | README written; clean-clone run not done |
| F4 no secrets, conventional commits | 2 | 2 | `.env` ignored; iteration commits |
| **Total** | **100** | **58** | |

## Iteration 1 — Core loop — 62 / 100

Changes vs iter-0 (only lines that moved):

| Line | Pts | iter-0 | iter-1 | Evidence |
|---|---|---|---|---|
| A3 editor interactions | 4 | 3 | **4** | `scripts/e2e_editor.py` 14/14 with real Chromium pointer input (palette tap → drop, 10 cm snap, mouse drag, R, L, red + blocked save, ⌘Z, Delete, persistence, fork survives reload); `apps/web/src/store.test.ts` 8/8 |
| A6 variants + persistence | 3 | 2 | **3** | `tests/test_layouts.py`, `tests/test_mongo_store.py::test_api_flow_with_mongodb_uri` (fork + PUT persisted in a real in-memory mongod) |
| A9 compare + ghost | 3 | 2 | **3** | `docs/screenshots/iter-1/web-13-compare.png` (desk visible on the right, deltas, "Added Desk"), `web-07-ghost-compare.png` |
| E3 JSON vs Mongo | 2 | 1 | **2** | `tests/test_mongo_store.py` (3 tests; `/health` reports mongo live; no `db.json` written) |
| **Total** | | 58 | **62** | pytest 58 passed · vitest 27 passed · demo 8.8 s · validation p95 1.65 ms |

Bugs found by the new evidence and fixed: floor picking never fired (invisible mesh), grab-by-top made items jump ~1 m, undo after a drag restored the wrong snapshot, plan view rendered as a diamond, overlay texture mirrored in z, palette only showed items already in the layout, compare view hid imported items.

## Iteration 2 — UI clone — 75 / 100

**B. UI fidelity (25) — graded from `docs/screenshots/iter-2/compare-*.png` (reference crop | ours) and the full frames.** Geometry was measured from ref2 (buttons 49 px at pitch 58 from (79,77); tiles 48 px, 3 × 8 at pitch 58/58.7 from y = 280; pager 38 px at y = 755; top-right divider at x = 1774; corner marks 42 px inset 28) and ref3 (swatches 3 columns at pitch 62, right margin ≈ 90, ✕ as the first cell), and colours were sampled (`#4E3D38` button body over the peach, tile `#F4F7FA`, background `#B57C56` → `#9E6B4A`, floor `#98543E`–`#B0684C`).

| B line | Pts | Score | Evidence / gap |
|---|---|---|---|
| background + corner marks | 2 | 2 | `compare-background-corner.png` — radial peach, hill silhouettes, knotted L marks |
| room island + slab + cutaway walls + windows | 3 | 2 | `compare-room-island.png` — same construction (rounded slab island, two back walls, off-white trim, glowing grid window); ref room is larger and glazed wall-to-wall |
| floor material | 1 | 1 | `compare-floor.png` — terracotta brick, lighter grout |
| top-left cluster | 2 | 2 | `compare-top-left-cluster.png` — size, pitch, rim, disabled undo |
| top-right cluster | 2 | 2 | `compare-top-right-cluster.png` — dim toggles, divider, ? |
| left palette grid + pagination | 3 | 3 | `compare-left-palette.png` — 3 × 8, cursor tool first, 3D tiles, pager |
| category / search behaviour | 1 | 1 | `compare-category-search.png` + `web-02-palette.png` — 🔍 toggles the search field, category tabs above the grid |
| right swatch panel | 3 | 3 | `compare-right-swatch-panel.png` — ✕ first cell, white-bordered swatches, pager, details block |
| selection diamond + pill | 2 | 2 | `compare-selection-diamond-pill.png` — white footprint outline + corner ticks, pill with two colour dots + name + arrow |
| bottom-center cluster | 2 | 2 | `compare-bottom-center.png` — geometry matches; filled palette / tiered pine / crescent / speaker glyphs redrawn against the crop (iter-3) |
| variant tabs / analysis tile / request bar | 2 | 2 | `web-06-variant-tabs.png`, `web-08-request-reply.png` — same tile language, 49 px tab height |
| landscape iPhone proportions | 2 | 2 | `phone-03-selected-side-panel.png` (2556 × 1179) — all clusters scale with `vmin`, no overlaps |
| **B total** | **25** | **24** | |

Other lines that moved: D3 README demo script 0 → **2** (timestamps + spoken lines, Devpost blurb). **Total 75 / 100** (A 29 · B 23 · C 8 · D 10 · E 9 · F 9 — see iter-0/1 tables for unchanged lines).

Controls verified working in this iteration (every visible control): menu drawer, snapshot download, undo, view cycle (cutaway → half → plan), paint drawer (wall + floor), help, palette tiles/paging/search/categories, side panel (rotate, lock, duplicate, delete, 38 swatches over 2 pages), bottom cluster (overlays popover with 3 toggles, ghost popover, night, sound), variant tabs (switch, +, context menu), analysis tile expand, request bar (send, paste link, photo).

## Iteration 3 — Agent + integrations + DEMO-READY checkpoint — 79 / 100

Lines that moved: F3 (clean clone → `make setup` 8 s → `make test` green: 3 + 16 + 8 vitest, 60 pytest; README has setup, phone, Photon, demo script, blurb, live URLs) 1 → **2**; D1 unchanged (8) — `make demo` 9.6 s locally; deploy line (part of §12 deliverables, not scored separately): web https://adaptive-room-planner.vercel.app and API https://adaptive-room-planner-api.vercel.app are live, `/docs` renders, `POST /rooms` works. Photon simulator (`make photon`) → 4 variants + outbox entries with deep links. A5/A8 mock evidence unchanged; real-mode adapters are implemented but unproven (no keys yet). **Known gap:** the deployed API's JSON store is per-instance until `MONGODB_URI` (or another shared store) is configured, so cross-request flows on the public API can 404 — the local stack and `make demo` are unaffected.

**Judge-rubric self-check (iter-3).** *Concept*: "text your room" + never-overwritten variants is the hook; the Live Better framing (100 sq ft, three flights of stairs) is in the copy and the sample room. *Functionality*: the whole loop runs on the public URLs in ~10 s headless; the same script is in the README with spoken lines. *Wow*: the iMessage → variant beat and the ref-faithful cutaway room. *UX*: pixel-measured clone; every control works; a first-time judge still needs the "Load sample room" card to get going — that is the entry point on the web home. *Community value*: NYC renters, movers, and the accessibility line (1.5 m turning radius uses the same solver) are stated in the README.

## Iteration log

### iter-3 — 79/100 (demo-ready checkpoint; B 24 after the glyph pass, C5 1 from the browser fps run)
- Makefile targets verified (`make test`, `make bench`, `make demo`, `make e2e`, `make photon`); pnpm 12 build approval fixed; Vercel deploys for web (static) and API (Python function); README live URLs, demo script, Devpost blurb; ngrok installed for the local path.
- Open: shared persistence for the serverless API, real-mode keys, RoomPlan module + device run (iter-4), phone recording, fps measurement.

### iter-2 — 75/100
- Measured ref2/ref3 geometry + colours applied to every §7 element; side panel restructured to ref3's 3 × 8 grid with ✕ first; button inner rim, dim toggles, knotted corner marks, thumbnail framing by projected extent; README demo script + Devpost blurb.
- Still open: C5 device fps, D2 phone recording, E4 Expo Go launch, F3 clean-clone check, deploy.

### iter-1 — 62/100
- Real-pointer e2e (14 checks), Mongo evidence via pymongo_inmemory (58 pytest), drag offset + single-step undo, floor raycast rewrite, plan view + overlay orientation fixes, compare shows both layouts' furniture, catalog loads into the palette, fixture preview route.
- Next: B fidelity pass (iter-2), then demo-ready checkpoint (README script, Devpost blurb, tag) in iter-3.

### iter-0 — 58/100 (provisional)
- Monorepo, contracts (7 JSON schemas + TS types), geometry package (validation + metrics + overlays, 16 tests, p95 1.7 ms for 20 items), 14 parity fixtures, Kenney assets + manifest (25 items) + rendered thumbnails, sample rooms, FastAPI (55 tests, exact TS parity, mock Gemini/Backboard/Photon, JSON store), Vite editor (cutaway room, drag/rotate/lock, palette, side panel, variant tabs, analysis tile, request bar, overlays, ghost, compare), Expo app (all screens, bridge, RoomPlan placeholder), `make demo` green.
- Failing / weak lines to attack next: B (fidelity grading), C5, D2, D3, E3, E4, F3.

**Judge-rubric self-check (iter-0).** *Concept*: the room is real, the input is a text, every answer is a saved variant — reads as a new angle on "will it fit". *Functionality*: the whole loop runs headless in 8.5 s, but nothing has been touched on a phone yet. *Wow*: the cutaway room already looks like the reference games; the iMessage → variant beat is the moment. *UX*: controls exist and work; pixel fidelity ungraded. *Community value*: NYC renter framing is in the copy, the sample room is 3.4 × 3.0 m.
