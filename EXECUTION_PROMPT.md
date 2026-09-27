# Build "FitCheck" — DivHacks 2026, Live Better track

You are building a hackathon project end to end, autonomously, in iterations, until a 100-point benchmark scores ≥95 (target 100). Do not stop to ask questions; when something is ambiguous, pick the option that best serves the 3-minute demo, write the assumption into `DECISIONS.md`, and continue. Commit at the end of every iteration.

## 0. Read these first

1. `docs/specs/PRD.pdf` — product requirements (13 pages).
2. `docs/specs/MVP-spec.pdf` — build spec (10 pages). **Where the two disagree, the MVP spec wins**, except: compare view is P0; keep the PRD's `GET /layouts/{a}/compare/{b}`; keep the PRD's derived analysis numbers (open floor %, largest free rectangle, walkability, reachable storage %, conflict count).
3. `docs/specs/DivHacks-2026-references.pdf` — six pages containing **seven reference images**. They are **already extracted to `docs/reference/`** (ref1…ref7, full resolution). Only if that folder is missing or empty, re-extract with:

   ```bash
   python3 -m pip install --user pypdf
   python3 - <<'EOF'
   import struct, zlib
   from pypdf import PdfReader
   pdf = 'docs/specs/DivHacks-2026-references.pdf'
   def png(w,h,n,d):
       ct={3:2,1:0,4:6}[n]; raw=b''.join(b'\x00'+d[y*w*n:(y+1)*w*n] for y in range(h))
       ch=lambda t,b: struct.pack('>I',len(b))+t+b+struct.pack('>I',zlib.crc32(t+b)&0xffffffff)
       return b'\x89PNG\r\n\x1a\n'+ch(b'IHDR',struct.pack('>IIBBBBB',w,h,8,ct,0,0,0))+ch(b'IDAT',zlib.compress(raw))+ch(b'IEND',b'')
   import os; os.makedirs('docs/reference', exist_ok=True)
   names = {'X5':'ref1-mood-decorate-panel','X9':'ref2-game-ui-peach','X10':'ref3-game-ui-teal-swatches','X13':'ref4-attic-style','X14':'ref5-unpacking-style','X17':'ref6-sims-eyelevel','X20':'ref7-sims-dollhouse'}
   for p in PdfReader(pdf).pages:
       for name, ref in p.get('/Resources',{}).get('/XObject',{}).items():
           x = ref.get_object()
           if x.get('/Subtype') != '/Image': continue
           cs = x['/ColorSpace']; n = cs[1].get_object()['/N'] if isinstance(cs, list) else 3
           out = f"docs/reference/{names.get(name[1:], name[1:])}.png"
           open(out,'wb').write(png(x['/Width'], x['/Height'], n, x.get_data())); print(out)
   EOF
   ```
   (If that fails, `brew install poppler && pdfimages -png "<pdf>" docs/reference/ref` and rename by size: 1920×1080 = ref2, 1200×675 = ref3, 1024×559 = ref1, 686×386 = ref4, 1080×675 = ref5, 1024×576 = ref6, 735×919 = ref7.) **Open every image with the Read tool and study it before building UI.**

## 1. Hackathon context (optimize for this)

- DivHacks 2026, Columbia. Submissions due **Sep 27 2026, 10:30 AM ET**. Deliver a working demo-ready checkpoint **by the end of iteration 3** no matter what; keep improving after.
- Track **Live Better**: "strictly personal utility — the grind of daily NYC life, optimized: groceries, meal planning, apartment hacks." Frame everything as: *renter in a 100–150 sq ft NYC room, buying secondhand, wants one more thing to fit without hauling it up three flights.*
- Judging rubric: **Concept 30%** (overlooked problem / new angle), **Functionality 30%** ("does it work as intended? how well does the demo run?"), **Wow Factor 20%**, **UX & Design 10%**, **Value to Community 10%**. Submission needs a source link + a way to test (deployed web URL).
- Sponsor challenges we target: **Photon** (iMessage in/out), **Backboard** (memory), **Gemini API** (structured reasoning + vision), **Supabase** (storage). Each must be visibly used in the demo *and* degrade gracefully to mock mode.

## 2. Decisions already made (do not revisit)

| Area | Decision |
|---|---|
| Mobile | **Expo** app (latest SDK, expo-router, TypeScript), run as a **dev client** with `npx expo run:ios` on this Mac. Must also launch in **Expo Go** with every feature except live RoomPlan scan. |
| Scan | **Custom local Expo Module in Swift wrapping RoomPlan** (`RoomCaptureView` + `RoomCaptureSession`), exporting `CapturedRoom` to our skeleton JSON. Device: iPhone Pro (LiDAR). |
| Editor | **Web app** (Vite + React + TypeScript + react-three-fiber + zustand) embedded in the Expo app via `react-native-webview` with a typed `postMessage` bridge. The same build deploys standalone to Vercel as the judges' test URL. Editor screen **locks to landscape**. |
| Backend | **FastAPI** (Python 3.12, pydantic v2, httpx). **Supabase REST/Postgres** when `SUPABASE_URL` and a server-only secret/service key are set; otherwise a JSON-file repository at `.data/` with the identical interface. |
| Geometry | Fit validation implemented in **TypeScript** (`packages/geometry`, runs in the browser on every change) **and** in **Python** (`apps/api/app/solver`). A shared fixture suite `fixtures/validation/*.json` is the single source of truth; a test in each language loads the same fixtures and must produce identical violation lists and metrics. |
| Integrations | Gemini, Backboard, Photon, Supabase are behind adapters. `MOCK_MODE=true` (default) uses deterministic fixtures so the whole demo runs offline. Real mode is enabled per service by its env var being present. |
| Units | Meters internally everywhere. UI shows **feet & inches by default** with a settings toggle to metric. Format like `4' 0"` and `18 in`. |
| Assets | **Kenney Furniture Kit (CC0)** GLBs. Download from https://kenney.nl/assets/furniture-kit (or poly.pizza bundle), keep ~20 items in `assets/furniture/`, and write `assets/furniture/manifest.json` with real-world `dims {w,d,h}` in meters and a per-model scale so each GLB matches its dims exactly. If the download fails, generate procedural low-poly meshes from Three.js primitives with the same manifest and note it in DECISIONS.md. |
| Look | **Isometric cutaway like the references**: two full-height back walls with windows, the two walls nearest the camera hidden; orbit in 90° steps re-picks hidden walls. The room floats as a rounded island with a thick dark-brown slab edge on a warm flat background with faint corner frame marks. Flat shading, soft warm key light, baked-looking soft AO blob under each item. |
| UI | **Clone the game UI in ref2 and ref3 exactly** (positions, sizes, shapes, colors, iconography, spacing). Our extra panels use the same language. Every visible control must actually work. |
| Photon reply | One sentence + deep link `roomplanner://layout/{id}` and an https link to the web editor `/layout/{id}`. PNG snapshot in the reply is P1. |
| Gemini | Latest Flash via `GEMINI_MODEL` (default `gemini-2.5-flash`), **structured output** with `response_schema` = the plan schema. One retry with the violation list when the solver rejects. |
| Users | One shared demo user keyed by phone number (`DEMO_PHONE`). No sign-in. |
| Onboarding | Home screen with three cards: **Scan room**, **Load sample room**, **Enter dimensions**. No separate wizard. |

## 3. Repository layout (create exactly this)

```
divhacks/
  apps/mobile/            Expo app (expo-router). Screens: Home, Scan, Editor (WebView), Ask (request box + agent log), Variants, Settings
  apps/mobile/modules/roomplan/   local Expo Module (Swift): RoomPlanView + startCapture/stopCapture/exportSkeleton
  apps/web/               Vite + React + R3F editor. Routes: /, /layout/:id, /compare/:a/:b, /snapshot/:id (headless render)
  apps/api/               FastAPI. app/{main,routers,models,repo,solver,agent,integrations}.py …
  packages/geometry/      TS: types, validation rules, metrics, zone→coordinate helpers (used by web + bridge)
  packages/contracts/     JSON Schemas: skeleton, layout, furniture, plan (Gemini output), bridge messages, photon fixtures
  assets/furniture/       Kenney GLBs + manifest.json + thumbnails (rendered PNGs for the palette tiles)
  fixtures/rooms/         sample-nyc-bedroom.json (3.4×3.0 m, one door, one window), sample-studio.json, one real RoomPlan export once scanned
  fixtures/validation/    the shared TS/Python parity suite
  fixtures/listings/      desk.html (a static Marketplace-style listing with dims + price), desk.jpg
  fixtures/photon/        inbound webhook payloads (text, link, image) captured from Photon docs/OpenAPI
  docs/reference/         extracted reference images
  docs/screenshots/       per-iteration screenshots (see §8)
  BENCHMARK.md            scored rubric per iteration
  DECISIONS.md            assumptions log
  README.md               setup, run, demo script, Devpost blurb
  .env.example            all env vars
```

Tooling: pnpm workspaces for JS, `uv` (or venv) for Python; root `Makefile` with `make api`, `make web`, `make mobile`, `make test`, `make bench`, `make demo`.

## 4. Data model & API (canonical; from the MVP spec)

Collections `rooms`, `furniture`, `layouts`, `users`, `agent_requests` exactly as the MVP spec's table, with `layouts.items[] {furnitureId, x, z, rotation, locked}`, `zones[] {label, x, z, w, d}`, `metrics {openFloor, conflicts, walkability, reachableStorage, largestFreeRect}`. `rooms.skeleton { walls[] {x1,z1,x2,z2,height}, doors[] {wall, offset, width, swing:"in"|"out", hinge:"left"|"right"}, windows[] {wall, offset, width, sillHeight, height}, floorPolygon[] }` plus derived `dimensions {l,w,h}`. **The skeleton is immutable after creation** and **the layout with `isCurrent:true` can only be changed by the user from the editor, never by the agent.**

Endpoints: `POST /rooms` (RoomPlan JSON | manual dims | `{sample:"nyc-bedroom"}` → creates room + Current Room seeded from detected objects), `GET /rooms/{id}`, `GET /layouts/{id}`, `PUT /layouts/{id}`, `POST /layouts/{id}/fork`, `DELETE /layouts/{id}` (refuses on isCurrent), `GET /layouts/{a}/compare/{b}`, `GET /furniture`, `POST /furniture/from-link`, `POST /furniture/from-photo`, `POST /furniture/manual`, `POST /agent/request`, `POST /webhooks/photon`, `GET /health` (reports which integrations are live vs mock). OpenAPI docs at `/docs` must render.

## 5. Fit validation (PRD §8, identical in TS and Python)

10 cm grid. Rules and failure behavior: room bounds (red, blocks save), overlap (both named, red), locked items never moved by agent/solver (plan rejected), door swing arc + 0.9 m clearance (red keep-clear overlay), window keep-clear (warning), access edges 0.75 m for beds/desks (one long edge) and wardrobes/dressers (front) (yellow), requested clear zones as one contiguous free rectangle (report largest found), walkable path flood-fill from door to every bed and desk ("Path blocked to desk"). Derived numbers: open floor %, largest free rectangle (sq ft + "fits a yoga mat / a desk"), walkability Good/Tight/Blocked, reachable storage %, conflict count. **Budget: < 100 ms for 20 items on the 10 cm grid in the browser** (measure it; memoize per layout hash).

## 6. Agent pipeline (MVP spec §Agent pipeline)

Router → furniture import when Photon/iMessage supplies a link/photo or when a caller passes a `furnitureId` → Backboard context → Gemini structured JSON `{intent, variantName, constraints[], actions[], reply, clarifyingQuestion?}` with intents `fit_item | make_space | keep_clear | compare | clarify` → **Python placement solver** turns zones ("window wall, beside window", "east wall, centered", "near outlet", "opposite the door") into coordinates by scanning candidate positions on the grid, scoring by constraint satisfaction, and rejecting anything that fails §5 → retry Gemini once with the violation list → save as a **forked** layout named `variantName` (dedupe with " (2)") → reply text + links → write new preferences back to Backboard. Log every run to `agent_requests`. In mock mode, the Gemini adapter returns canned plans for the two demo requests ("Will this fit beside my window without moving my bed?" with an imported desk; "make space for yoga, keep my dresser") and a `clarify` for anything else.

Furniture import: Photon/iMessage is the user-facing channel for new furniture. `from-link` fetches the page (10 s timeout), extracts OpenGraph/JSON-LD/text, asks Gemini for `{name, category, dims, price, color, estimated}`; Facebook Marketplace requires login so also accept a **screenshot** (`from-photo`) and manual dims; `fixtures/listings/desk.html` is served by the API at `/fixtures/listings/desk` so the demo link works offline.

Backboard: `pip install backboard-sdk`, base `https://app.backboard.io/api`, `X-API-Key`. Use `/memories` (POST add, GET list/search) keyed by the demo user; store must-keep items ("never move my bed"), lifestyle notes ("I do yoga every morning"), budget. Fetch the docs at https://docs.backboard.io/ (and the index at https://backboard-docs.docsalot.dev/llms.txt) before coding the adapter.

Photon: TypeScript-first platform (`spectrum-ts`); we only need the **webhook in** and **REST send out**. Photon is the external furniture input channel: users send Facebook Marketplace, IKEA, Amazon, or other store links/photos over iMessage and ask if the item fits. Spatial-only prompts ("make space for yoga", "reading corner", "don't move my bed") are redirected to the in-app assistant. Read https://photon.codes/docs/webhooks/events, https://photon.codes/docs/webhooks/verifying-signatures (Python verifier exists), and the OpenAPI at https://spectrum.photon.codes/openapi/json, then implement `POST /webhooks/photon` (verify signature when `PHOTON_WEBHOOK_SECRET` is set) and an outbound `send_text(to, text, links)` client. Ship a `scripts/simulate_photon.py` that posts the fixture payloads to the local webhook so the round trip is testable without an account. Public URL for real mode: `ngrok http 8000` (document it).

## 7. UI — exact clone map of ref2 / ref3 (the web editor, rendered in the WebView and standalone)

Measure the references (they are 1920×1080 and 1200×675); express sizes in CSS px at a 1920-wide layout and scale with `vmin` so the landscape iPhone matches proportionally. Match colors by sampling the images.

**Canvas & room** — flat warm background (ref2 peach ≈ `#D9A56E`; ref3 teal ≈ `#8FBDB0` is the second theme) with faint darker silhouettes of hills/trees along the bottom and thin dark corner frame marks in the four corners. Room = rounded floor island with a thick dark-brown slab edge; back-left and back-right walls full height, off-white trim, tall grid windows with warm translucent panes; terracotta brick/herringbone floor. Orthographic camera, ~35° elevation, 45° azimuth, scroll to zoom, right-drag/two-finger to orbit in 90° steps.

**Top-left cluster** (3 buttons, ~48px, radius ~10, dark brown `#4A3327` at ~85% opacity, white glyphs, 8px gap): ☰ menu (opens Rooms / Variants / Settings / Units / Help drawer), 📷 snapshot (downloads a PNG of the canvas and posts it to the bridge), ↺ undo (greyed when history empty; ⌘Z too).

**Top-right cluster**: 👁 view (cycles cutaway → half-height walls → plan view), 🪣 paint (opens wall/floor palette; recolors room surfaces), thin vertical divider, ? help (overlay listing gestures: drag, R rotate, L lock, Del remove, Shift free-move).

**Left palette** (ref2): 3 columns × 8 rows of ~52px white rounded tiles (`#F7F2EA`, radius 10, soft shadow), 6px gaps; first tile is the **select/cursor tool** (dark when active). Remaining tiles are furniture thumbnails from `assets/furniture/thumbs/`. Below: `‹ 1 ›` pagination (dark buttons, page number in dark text). Ref3's variant shows category icons with 🔍 first — implement as **category tabs above the grid** (All, Bed, Desk, Seating, Storage, Table, Decor, Imported) and a search field that appears when 🔍 is pressed. Tap a tile → item appears at the room center in "placing" state following the pointer; tap to drop.

**Right side panel** (ref3): appears when an item is selected. ✕ close at top-left of the panel; 3-column grid of ~40px rounded tiles; `‹ 1 ›` at the bottom. Our content: row 1 = actions (rotate ⟳, lock 🔒, duplicate, delete); then **color swatches** that recolor the selected item's material (ref3 behavior); then a details block: name, `W × D × H` in current units, gap to nearest wall, price/source if imported, "estimated" badge.

**Selection affordance** (ref3): white diamond outline on the floor footprint plus a floating pill above the item with the item's two dominant color dots and the name. Red tint + shake on collision, yellow tint for access-edge violations; small bounce + soft "thunk" (WebAudio, muted by default in the WebView) on drop.

**Bottom-center cluster** (4 buttons, same style as top-left): 🎨 overlays (walkable green / keep-clear red / low-clearance yellow toggles), 🌲 ghost-compare (overlay another variant as translucent ghosts), 🌙 day/night lighting, 🔊 sound.

**Our additions, same visual language**:
- **Variant tabs**: top-center pill bar — `Current Room` (lock glyph, never renamed) `Marketplace Desk` `Yoga corner` `+`. Long-press/right-click → rename, duplicate, delete. Agent-created tabs animate in.
- **Analysis tile**: small card under the top-right cluster: open floor %, conflicts, walkability, largest free rectangle; updates on every drag; tap to expand the conflict list ("Desk overlaps Dresser", "Path blocked to desk").
- **Request bar**: bottom-right chat bubble button; expands to a text field with spatial suggestions ("make space for yoga", "reading corner", "place the desk near the window", "don't move my bed") and shows the agent's one-line reply. It hits `POST /agent/request` for room arrangement only; new furniture links/photos go through Photon/iMessage.
- **Compare view** (`/compare/:a/:b`): two rooms side by side + metric deltas + "what moved" list; the 🌲 button is the in-editor ghost version.

## 8. Screenshot discipline (mandatory every iteration)

- Web: Playwright (chromium, 1920×1080 **and** 2556×1179 for iPhone Pro landscape) captures: empty room, palette open, item selected + side panel, collision state, overlays on, variant tabs with 3 variants, ghost compare, compare route, request bar reply. Save to `docs/screenshots/iter-N/`.
- Mobile: `xcrun simctl io booted screenshot` (or device screenshot) of Home, Scan (fallback screen in Simulator), Editor WebView, Ask, Variants.
- For each UI element in §7, produce a **side-by-side crop** (reference crop | ours) in `docs/screenshots/iter-N/compare-<element>.png` and grade it in BENCHMARK.md. Use the Read tool to look at every screenshot yourself; do not grade from code.

## 9. Benchmark — 100 points, score every iteration in `BENCHMARK.md`

Stop only when total ≥ 95 with **no single line below 50% of its value**; target 100. Every line needs evidence: a test name, a timing log, or a screenshot path.

**A. Functional acceptance (30)**
- A1 (3) Sample room and manual dims create a room whose walls/doors/windows render in the right places; RoomPlan JSON fixture also loads.
- A2 (3) Skeleton immutable: editing/deleting layouts never changes it (API test).
- A3 (4) Editor: add, drag on floor plane with 10 cm snap, Shift free-move, R rotate 90°, wall snap, lock badge, remove, undo/redo.
- A4 (3) Import: fixture link → placeable item with correct dims + price in < 10 s; photo → type + estimated dims; manual dims.
- A5 (4) Agent: both demo requests return valid plan JSON (schema-validated), bed stays locked, variant saved beside Current Room, reply text sensible; unknown request → clarifying question. Retry-on-violation path tested with a forced bad plan.
- A6 (3) Variants: rename/duplicate/delete, Current Room never overwritten, both reopen after reload (persistence test in JSON store and, if configured, Supabase).
- A7 (4) Validation: each §5 rule has a fixture that triggers it; violations named per item; red state blocks save.
- A8 (3) Photon: simulated inbound furniture link/photo+question → variant created → outbound reply captured (mock) with deep link; spatial-only texts redirect to the in-app assistant; real round trip if credentials exist.
- A9 (3) Compare: side-by-side + metric deltas + moved list; ghost overlay in editor.

**B. UI fidelity to ref2/ref3 (25)** — each graded 0/1/2 against the side-by-side crop: background + corner marks (2), room island + slab edge + cutaway walls + windows (3), floor material (1), top-left cluster (2), top-right cluster (2), left palette grid + pagination (3), category/search behavior (1), right swatch panel (3), selection diamond + pill (2), bottom-center cluster (2), variant tabs / analysis tile / request bar consistent with the language (2), landscape iPhone proportions (2).

**C. Performance (10)** — validation < 100 ms for 20 items (3, log p95 over 50 runs); room load to rendered editor < 30 s cold / < 3 s warm (2); import fixture < 10 s (1); agent round trip < 20 s real, < 2 s mock (2); WebView editor 60 fps drag on device or ≥ 45 fps in Simulator (2).

**D. Demo run (15)** — `make demo` runs the full 3-minute script headlessly via Playwright + API (load sample → build Current Room from fixture → lock bed → simulated Photon message → Marketplace Desk variant → drag into door swing → red → drag back → compare) without errors (8); the same script performed manually on the phone in landscape, recorded to `docs/demo/run.mp4` (5); README demo script with timestamps and spoken lines (2).

**E. Robustness (10)** — mock mode works with zero env vars and no network (3); bad Gemini JSON → retry → fallback keeps old layout (2); no `SUPABASE_URL` → JSON store; with Supabase env → Supabase (2); Expo Go launch without the RoomPlan module (2); `/health` reports live/mock per service (1).

**F. Engineering quality (10)** — `pnpm typecheck && pnpm lint && pnpm test` green (3); `pytest` green including TS/Python parity on `fixtures/validation` (3); `.env.example`, README setup steps verified from a clean clone (2); no secrets committed, conventional commits per iteration (2).

**Judge-rubric self-check (not scored, written each iteration):** one paragraph each on Concept, Functionality, Wow, UX, Community Value — what a judge sees in 3 minutes and what to improve.

## 10. Iteration protocol

Each iteration: build → run `make test` and `make bench` → capture screenshots (§8) → score every line in BENCHMARK.md with evidence → list the failing lines → fix the highest-value failures first → commit `iter-N: <summary> (score X/100)`. Never claim a line passes without evidence.

- **Iteration 0 — Skeleton (target: things run).** Monorepo, contracts (JSON schemas + TS types + pydantic models generated from them), FastAPI with JSON store, sample rooms, Kenney assets + manifest + thumbnails, Vite editor rendering the sample room in the cutaway style, Expo app with Home + Editor WebView loading the dev server over LAN, bridge handshake, `.env.example`, Makefile.
- **Iteration 1 — Core loop.** Editor interactions (A3), validation TS + Python + parity fixtures (A7, F), layouts CRUD + fork + persistence (A2, A6), analysis tile, variant tabs, settings units toggle.
- **Iteration 2 — UI clone.** Every §7 element pixel-matched against ref2/ref3 with side-by-side crops; landscape iPhone proportions; all controls functional; sound + day/night + overlays; first full B-section grading.
- **Iteration 3 — Agent + integrations + DEMO-READY CHECKPOINT.** Import endpoints, Gemini adapter (mock + real), solver, Backboard adapter, Photon webhook + simulator + outbound client, compare view + ghost, `make demo`, README demo script, Devpost blurb. Tag `demo-ready`.
- **Iteration 4 — RoomPlan module + device.** Swift Expo Module, skeleton export (walls→segments, doors/windows→wall offsets, objects→seeded items by category), Scan screen, real device run, one real scan saved to `fixtures/rooms/`, landscape lock, deep links, Expo Go fallback verified.
- **Iteration 5+ — Benchmark loop.** Re-score; fix lowest lines; polish (animations, empty states, error toasts, loading skeletons); deploy web to Vercel and API to Render/Railway (or document ngrok); record the demo video. Repeat until ≥ 95 (aim 100). After each pass, append the score table to BENCHMARK.md so progress is visible.

If the deadline approaches with lines still failing, protect in this order: D (demo runs) > A5/A8 (agent + Photon) > B (fidelity) > everything else. Never leave the repo in a state where `make demo` fails.

## 11. RoomPlan module details

`apps/mobile/modules/roomplan` created with `npx create-expo-module --local roomplan`. Swift: an Expo View wrapping `RoomCaptureView`, session delegate collecting `CapturedRoom` on stop; a function `exportSkeleton()` returning JSON with walls (segment endpoints in meters projected to the floor plane, origin re-based to the min corner), doors/windows (parent wall index, offset along the wall, width, height, sill), and `objects` (RoomPlan category, dimensions, center, yaw). Map categories → manifest keys (bed→bed_double/bed_single by width, table→desk if near a chair else table, storage→dresser/wardrobe by height, sofa, chair, television→tv_stand, stove/refrigerator skipped for bedroom). Guard with `RoomCaptureSession.isSupported`; unsupported devices and Expo Go get the fallback screen (sample room / manual dims / paste RoomPlan JSON).

## 12. Deliverables checklist (all must exist at the end)

- Running: `make api` (FastAPI :8000), `make web` (Vite :5173), `make mobile` (Expo dev client), `make demo` (headless 3-minute run), `make bench` (perf + parity + scoring helpers).
- `README.md`: one-command setup, env vars, how to run on device, the 3-minute demo script with lines, fallback plan (pre-recorded scan, mock mode), Devpost blurb (Live Better framing, sponsors used), future applications (real estate, movers, accessibility 1.5 m turning radius).
- `BENCHMARK.md` with the final score ≥ 95 and evidence links; `DECISIONS.md`; `docs/screenshots/iter-N/*`; `docs/demo/run.mp4`.
- Deployed web editor URL (Vercel) and API URL or documented ngrok command; `.env.example` complete.
- Git: every iteration committed; `demo-ready` tag.

## 13. Working rules

- Autonomous: never wait on the user; log assumptions in DECISIONS.md.
- Mock-first: every integration works offline before any real key is used; when a key exists, prove the real path once and record the timing.
- Look at your own screenshots with the Read tool before grading UI lines. Fidelity means matching the references, not "inspired by."
- Meters internally; formatting only at the UI edge.
- Current Room is sacred: the agent forks, never edits it.
- Keep the demo path fast: preload the sample room, cache GLBs, no network calls on the editor's hot path.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
