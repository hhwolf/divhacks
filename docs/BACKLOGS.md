# Backlogs

As of 2026-09-26 · shared copy: https://claude.ai/code/artifact/4d978fea-de33-4176-ab94-92cfeb2236e2

Furnish-an-empty-room works end to end on a local machine but is not live yet: the API and web editor still need a Vercel deploy before anyone, including TestFlight users, can use it.

What exists locally today: describe a room or add up to 4 inspiration photos, and the server picks catalog furniture, places it with the fit solver (0 conflicts across 25 test runs, under 3 s), and opens it as a new variant in one of 5 styles (Japandi, industrial, boho, minimal, cozy) with a drop-in animation. Restyle re-themes the same room.

Top 3 blockers:

1. Deploy the API and web editor to Vercel (needs a login to the `ast18` team).
2. Run the Gemini path once with a real key, for text and for photos; only the offline fallback has been tested.
3. Check the photo picker inside the TestFlight app on a real iPhone.

## Release

Nothing from this round is deployed; the Vercel CLI on the dev laptop is logged out. The TestFlight build needs no rebuild because it loads the deployed API and web editor.

- [ ] Log in to Vercel with an account in the `ast18` team (`npx vercel login`)
- [ ] Link the repo root to the existing `adaptive-room-planner-api` project before deploying; `scripts/deploy_api.sh` would otherwise create a new project named "divhacks"
- [ ] Deploy the API, then check `GET /health` and call `POST /rooms/{id}/furnish` on the live URL
- [ ] Build and deploy the web editor against the live API; `pnpm` is not on PATH, so run `npx pnpm@9 --filter @arp/web build` by hand instead of `scripts/deploy_web.sh`
- [ ] Smoke-test the live site: empty room, furnish from text, furnish from a photo, Restyle
- [ ] Open the TestFlight app, create a room with Enter dimensions, and confirm the empty-room card appears

## Furnish feature follow-ups

The feature is tested only in mock mode (no Gemini key): 89 API tests pass, plus browser runs for text, photos and Restyle.

- [ ] Run the live Gemini path with `GEMINI_API_KEY` set, for a text theme and for 1–4 photos; if Gemini fails it falls back to the built-in furniture sets, so check which one actually ran
- [ ] Add photos to Restyle: the Ask bar's Restyle button only takes text today
- [ ] Without Gemini, photos only set the style and the plant count (from colour); the pieces come from the room type. Decide whether that is good enough for the demo
- [ ] Rooms that already have furniture get the new set added on top, and only a second bed, desk or wardrobe is prevented. Consider a "start from empty" option
- [ ] Desk chair, nightstand and coffee table are placed next to their anchor piece; TV stand and armchair still go to any free wall, so a TV can end up facing away from the sofa
- [ ] Style is detected from keywords; unfamiliar words (e.g. "mid-century", "coastal") fall back to minimal. Add more styles or map them
- [ ] The reply lowercases style names ("japandi bedroom")

## 3D models and Blender

Blender MCP works (Blender 5.0.1); one model is built and exported but not yet in the app. Blender is only needed while building models, never at runtime.

- [ ] Add `desk_l` (L-shaped desk, 1.4 × 1.1 × 0.75 m, `assets/furniture/desk_l.glb`) to `manifest.json`, render its thumbnail with `make thumbs`, and add it to the furniture sets
- [ ] Build more shapes in Blender: sectional sofa, loft/bunk bed, round and oval tables, open shelving, floor mirror
- [ ] Give marketplace imports a shape: have Gemini return the shape family and features (L-side, round, drawers), not just width/depth/height
- [ ] White-model look from the reference video: an all-white matte theme, dark caps on cut walls, low wall stubs in cutaway view, warm low sun, ambient occlusion (one new package), bold floor labels
- [ ] Optional: AI-generated custom pieces (Hyper3D / Tripo through the MCP) as a background job; slow and messy geometry, so not for the base room

## Mobile app

The new features live in the web editor the app shows, so they reach TestFlight on deploy; native changes need a new build.

- [ ] Check on a device: the gap under the Scan room card went from 24 to 40 px (`apps/mobile/app/index.tsx`); needs a new TestFlight build
- [ ] Check that the inspiration-photo button opens the iOS photo picker inside the embedded editor; taking a photo needs a camera permission in the app's Info.plist
- [ ] Optional: a native "describe your room" step in the setup flow, so the theme is asked for before the editor opens (needs a new build)

## Tech debt and known issues

None of these block the demo; they slow down development on the Windows laptop.

- [ ] `test_parse_listing_extracts_dims_and_price` fails on Windows unless Python runs in UTF-8 mode (`PYTHONUTF8=1`); the test reads a file with `×` using the system encoding. Pass `encoding="utf-8"` in the test
- [ ] `pnpm`, `make` and `ruff` are not on PATH on this machine; `make test` doesn't run. Install them or document the `npx pnpm@9` workaround
- [ ] Playwright has no browsers installed; the `e2e`, `demo` and `screenshots` scripts need `playwright install chromium` (or `channel="msedge"`)
- [ ] `fastapi.testclient` warns that using `httpx` is deprecated; switch to `httpx2` when convenient
- [ ] The repo folder is not a git repository, so there is no history of today's changes; initialise it or copy the changes into the GitHub clone before anything else is lost
