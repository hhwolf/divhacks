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

## Iteration 1 — core loop

- **Floor picking bypasses R3F object picking.** An invisible mesh is skipped by the raycaster, and a transparent plane behind items is occluded by them, so the floor is handled on the canvas' own pointer events with a ray → `y = 0` plane intersection. R3F still handles item hover/select. The floor handler defers one tick so item hits are known first.
- **Drag offset.** Grabbing an item by its top face projects to a floor point ~1 m behind it in the iso view; the drag keeps the item-centre-to-floor-point offset from the first move so items never jump on grab.
- **One undo step per drag.** The history entry pushed on drop is the snapshot taken when the drag started, not the last intermediate position.
- **Rotating may wall-snap.** `R` re-runs the snap/clamp pass, so an item within 15 cm of a wall after rotating hugs it. Accepted as consistent with "snap to walls".
- **Redo has no button** (the reference's top-left cluster has exactly three buttons). ⌘⇧Z redoes; the help overlay documents it.
- **Real-pointer evidence for A3** lives in `scripts/e2e_editor.py` (Playwright + Chromium against the running API/web): palette tap → floor drop, 10 cm snap, mouse drag, R, L, collision red + blocked save, ⌘Z, Delete, persistence, variant fork surviving reload. Unit-level evidence is `apps/web/src/store.test.ts`.
- **Mongo evidence without a local mongod** uses `pymongo_inmemory`, which downloads a mongod binary on first run (~440 MB, cached inside `.venv`). `apps/api/tests/test_mongo_store.py` skips with the reason if that download is impossible.
- **Fixture preview route** `/preview/:sample` renders a sample room with no API (read-only) for design work and offline screenshots.

## Iteration 2 — UI clone

- **Measured, not eyeballed.** Element boxes were segmented from ref2/ref3 by colour (`scipy.ndimage.label`) and sizes expressed at 1920 wide, scaled with `--u = 100vmin / 1080`. Colours are pixel averages over button bodies / tile faces, not the prompt's estimates.
- **Side panel = ref3's grid.** The ✕ sits where ref3 puts it (first cell), then rotate/lock/duplicate/delete, then 19 swatches per page (38 total, 2 pages) so the panel is exactly 8 rows like the palette.
- **Pill keeps the item name.** ref3's pill shows only two colour dots; the prompt asks for dots + name, so the name stays (dots sized like the reference).
- **Top-right view/paint toggles render "dim"** when inactive because ref2 draws them lighter than the help button.
- **Sound defaults on in a browser, off in the WebView** (autoplay policy: the first thunk plays after the first drop gesture).
- **Thumbnails are framed by projected iso extent** (`h·cos35° + (w+d)/2·sin35°` vs `(w+d)·cos45°`) so a moving box and a bed fill the tile equally.

## Iteration 3 — demo-ready checkpoint

- **API deploys to Vercel too**, not Render/Railway (no CLI or account for those on this Mac; Vercel is logged in). `api/index.py` exposes the FastAPI ASGI app; root `vercel.json` rewrites every path to it; root `requirements.txt` is the slim runtime set. This also gives Photon a stable public webhook URL without ngrok. `ngrok` is installed anyway (`brew install ngrok/ngrok/ngrok`) for the local-API path in the README.
- **Serverless persistence caveat.** Without `MONGODB_URI` the JSON store falls back to `/tmp` on a read-only filesystem, so data on the deployed API is per-instance and ephemeral. Set `MONGODB_URI` in the Vercel project for real persistence; locally nothing changes.
- **Web deploys as a prebuilt static site** (`scripts/deploy_web.sh <api-url>`): Vite bakes `VITE_API_URL`, the build copies `assets/` + `fixtures/` (dereferencing the dev symlinks) and writes SPA rewrites into `dist/vercel.json`.
- **pnpm 12 build approval** is `allowBuilds: { esbuild: true }` in `pnpm-workspace.yaml` (the older `onlyBuiltDependencies` key is ignored by pnpm 12.3), so `make setup` is non-interactive.
- **Shared persistence on Vercel = Vercel Blob snapshots** (`apps/api/app/repo/blob_store.py`), chosen because the CLI can provision it non-interactively (`vercel blob create-store arp-db --access private --yes`) while Atlas needs the user's account. Each mutation uploads an immutable `db-<ms>-<rand>.json`; every read first asks the (never CDN-cached) list API for the newest snapshot, so a room created on one function instance is visible to the next request on another. The last 4 snapshots are kept. Store selection order: `MONGODB_URI` → `BLOB_READ_WRITE_TOKEN` → local JSON file; `/health.integrations.mongo` reports `live` / `blob` / `json`.
- **Blob API facts** (learned by reading `@vercel/blob@2.8.0`): `PUT https://blob.vercel-storage.com/?pathname=<p>` with `x-api-version: 12`, `x-vercel-blob-access: private`, `x-add-random-suffix: 0`; list `GET /?prefix=`; delete `POST /delete {urls}`; private blobs are read with the same bearer token on their URL. Putting the pathname in the URL path returns "Invalid pathname".

## Iteration 4 — RoomPlan module + simulator

- **Expo SDK 57 needs Xcode 26.** RN 0.86's Podfile gates on Xcode ≥ 16.1 and `expo-modules-jsi` declares `swift-tools-version: 6.2`; this Mac has Xcode 16.0 / Swift 6.0, so no dev client or archive can be built here yet. `pod install` succeeds and `ExpoRoomPlan` links; `SkeletonExporter.swift` typechecks against the iOS 18 SDK. **Resolved by downgrading `apps/mobile` to Expo SDK 54** (RN 0.81, expo-router 6): with a one-line config plugin (`plugins/withXcode16Podfile.js`) that lowers RN's `min_xcode_version_supported` string check from 16.1 to 16.0, the app builds on this Mac for the simulator and for arm64 devices, and `ExpoRoomPlan` compiles and links (`libExpoRoomPlan.a`, zero warnings). The iOS deployment target is raised to 16.0 via `expo-build-properties` — SDK 54's default 15.1 made autolinking silently skip the RoomPlan pod. `expo-sharing` has no config plugin in SDK 54 and was removed from `plugins` (the package stays). Delete the Podfile plugin once Xcode ≥ 16.1 is installed. Cloud builds (EAS) also work with SDK 54.
- **RoomPlan → skeleton convention:** ours.x = RoomPlan.x, ours.z = RoomPlan.z, no mirror (same right-handed Y-up frame as three.js `rotation=[0,r,0]`, so yaw transfers directly). Walls are projected to XZ, chained by nearest endpoint, corners snapped by line intersection, the loop reversed when the shoelace area is negative so it winds clockwise on screen, then re-based to the min corner. `floorPolygon` comes from the snapped wall corners, never from `floors[0]`, so walls and polygon cannot disagree. Bed width = `min(dims.x, dims.z)`. `stopCapture()` resolves only after `captureView(didPresent:)` so `exportSkeleton()` is safe right after. Debug `meta` is stripped before `POST /rooms`.
- **Simulator evidence only.** Screenshots and the 30 s recording (`docs/demo/run-simulator.mp4`) are Expo Go 57.0.9 on an iPhone 16 Pro simulator; the editor segment is rotated inside the portrait frame because the Simulator window could not be rotated without Accessibility permission. Deep links in Expo Go take the form `exp://127.0.0.1:8081/--/<path>`; `roomplanner://` works only in the dev-client build.
- **WebKit fixes found on the phone:** `%` heights on an `<img>` inside a `<button>` resolve to 0 in WebKit, so palette thumbnails were blank on iOS — tiles now position the image absolutely. Editor clusters add `env(safe-area-inset-*)` so the Dynamic Island never covers the palette. The host ignores the editor's self-`editor:navigate` for the layout already shown (it was pushing a new screen each load).
- **Expo CLI rewrites `apps/mobile/tsconfig.json` `include` on every start**; the committed version is kept and the rewrite is discarded.
