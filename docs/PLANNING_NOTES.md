# Plan: Execution prompt for "FitCheck" (DivHacks 2026, Live Better track)

## Context

Henry's team is building **FitCheck** ("Where Did My Space Go?") at DivHacks 2026 (Columbia, Sep 26–27 2026, submissions due **Sep 27 10:30 AM ET**). Track: **Live Better** — "strictly personal utility: the grind of daily NYC life, optimized… apartment hacks." Judging rubric (from the DivHacks 2026 Devpost): Concept 30%, Functionality 30% ("how well does the demo run?"), Wow Factor 20%, UX/Design 10%, Value to Community 10%. Sponsor challenges relevant to this build: **Photon** (iMessage, $400 + credits), **Backboard** (memory), **Gemini API**, **Supabase**.

The repo `hhwolf/divhacks` is **empty** (no commits locally or on origin). Three attachments exist under `.context/attachments/assets/`: the PRD (13 pp), the MVP spec (10 pp), and "DivHacks 2026.pdf" (6 pp) whose only content is 7 reference images (page 1 also repeats the PRD summary; page 6 is the heading "UI/UX").

This planning phase produces **one execution prompt** the user will run on their Mac (Xcode + LiDAR iPhone Pro available). The prompt must drive a multi-iteration build with a 100-point benchmark and a stop condition of ≥95 (ideally 100).

## Decisions made with the user (Q&A this session)

| Topic | Decision |
|---|---|
| Frontend | **Expo iOS app** (dev client via `npx expo run:ios`) with a **WebView-hosted Three.js editor** (Vite + React + react-three-fiber). The same web build deploys standalone to Vercel as the judges' test link. |
| Scanning | Custom **Expo Module (Swift) wrapping RoomPlan**. Everything except live scan must also work in Expo Go via sample room / manual dimensions. |
| Device | iPhone Pro (LiDAR). Editor screen **locked to landscape**; scan/chat screens portrait. |
| Backend | **FastAPI + Supabase REST/Postgres**, with a local JSON-file store fallback when no `SUPABASE_URL`/secret key is configured. Validation exists in TS (browser) and Python (solver); parity enforced by a shared JSON fixture suite both must pass identically. |
| Credentials | None in hand yet; free accounts can be created. Every external service sits behind an adapter with a **mock mode that is the default**; real mode via env vars. |
| UI | **Clone the low-poly room-decorator game UI exactly** (reference images 2 and 3), adding our variant tabs / request bar / analysis tile in the same visual language. |
| Units | Toggle in settings, **default feet & inches**; meters internally. |
| Assets | **Kenney Furniture Kit (CC0)** GLBs, ~20 chosen items, rescaled to real dimensions via a manifest. |
| Room look | **Isometric cutaway**: two full-height back walls, front walls hidden per camera quadrant, room as a floating island on a warm background. |
| "User-controlled" | Means **genuinely interactive**: every visible control works (press states, panels open/close, pagination, drag). Not customization theming. |
| Time budget | Unanswered → **assume open-ended loop until ≥95**, with a mandatory "demo-ready" checkpoint after iteration 3 given the deadline. |

## Assumptions for the PRD's open questions (stated in the prompt, not asked again)

- Photon reply = one sentence + deep link `roomplanner://layout/{id}` (and https universal link to the web editor). Rendered PNG snapshot is P1.
- Channel split = Photon/iMessage imports new furniture from listing links/photos and creates fit variants; the in-app assistant handles spatial planning and room changes such as reading corners, yoga space, desk placement, and locked-item rules.
- Gemini: latest Flash model via `GEMINI_MODEL` env (default `gemini-2.5-flash`), **structured output** with a JSON schema for the plan.
- One shared demo user keyed by phone number; no sign-in.
- Onboarding = the app's home screen (Scan / Sample room / Manual dims cards), not a separate wizard.

## Spec reconciliation (PRD vs MVP spec) baked into the prompt

1. **API surface**: use the MVP spec's endpoints (`PUT /layouts/{id}`, `POST /layouts/{id}/fork`, `/furniture/from-link`, `/furniture/from-photo`, `POST /agent/request`, `POST /webhooks/photon`) plus the PRD's `GET /layouts/{a}/compare/{b}`. Drop the PRD's `PATCH /layouts` and `/rooms/{id}/agent`.
2. **Coordinates**: `x, z` in meters, rotation in degrees about vertical, origin at room's min corner (MVP spec). PRD's `x, y` is dropped.
3. **Gemini never emits coordinates**: zone-level `actions` + `constraints` (MVP spec); the PRD's `placement {x,y}` field is dropped. Solver converts zones → coordinates; browser validation has the final say.
4. **Compare view is P0** (it's in both demo scripts), not P1 as the PRD table says.
5. **Skeleton shape**: MVP spec's `skeleton { walls[], doors[], windows[], floorPolygon }`; add PRD's `dimensions {l,w,h}` as a derived convenience field.
6. **Demo length**: 3-minute script from the MVP spec, with the PRD's 2-minute cut as the "short version."
7. **Validation ownership**: rules live in TS (`packages/geometry`, runs in browser) and Python (`apps/api/solver`); a `fixtures/validation/*.json` suite is the single source of truth and CI fails on any divergence.

## Reference images (extracted this session to /tmp; the prompt re-extracts them on the Mac)

| # | PDF page / XObject | Size | What it is | Role |
|---|---|---|---|---|
| 1 | p1 X5 | 1024×559 | Cozy AI render of a cutaway living room with a "DECORATE" card bottom-right (Furniture/Paint/Rugs/Plants, gold counter, progress bar) | Mood only |
| 2 | p2 X9 | 1920×1080 | **Low-poly decorator game, warm peach bg.** Top-left ☰ 📷 ↺; top-right 👁 🪣 | ?; left 3×8 item-tile palette with cursor tool first and `< 1 >` pagination; bottom-center 🎨 🌲 🌙 🔊; two full-height back walls with grid windows, terracotta brick floor, thick brown slab edge; faint corner frame marks and hill silhouettes on the background | **Primary UI clone** |
| 3 | p2 X10 | 1200×675 | **Same game, teal bg.** Left palette is category icons with 🔍 first; right-side color-swatch panel (✕ top, 3-col swatches, `< 1 >`); selected sofa shows a white diamond floor outline and a floating pill with two color dots; green walls, herringbone floor | **Primary UI clone** (selection + side panel) |
| 4 | p3 X13 | 686×386 | Isometric attic cutaway render, olive bg | Style |
| 5 | p3 X14 | 1080×675 | "Unpacking"-style attic with moving boxes and hover cursor | Style/interaction |
| 6 | p4 X17 | 1024×576 | Sims 4 eye-level living room | Style |
| 7 | p5 X20 | 735×919 | Sims 4 dollhouse-view kitchen cutaway, cream bg | Style (cutaway) |

Extraction snippet that works with only `pypdf` (no Pillow) is included in the prompt.

## Files this plan produces

- This plan file (contains the prompt below).
- Nothing else in this phase. The execution phase creates the monorepo described in the prompt.

## Verification of this plan

Before handing off, confirm the prompt below: (a) names all three PDFs and the extraction step, (b) lists every decision above, (c) contains the 100-point rubric with automated evidence per line, (d) defines the iteration loop and ≥95 stop rule, (e) has the exact UI element map for references 2 and 3, (f) includes the Live Better / judging optimization section, (g) says "do not ask questions; state assumptions" so the run is autonomous.

---

## Notes for Henry (outside the prompt)

- **Deadline math**: the prompt front-loads a demo-ready checkpoint at iteration 3 because submissions close tomorrow morning. Iterations 4+ are the benchmark loop you asked for.
- **Accounts to create when the prompt starts running** (all free): Google AI Studio key (Gemini), Backboard API key, Photon account + iMessage line (needs a public webhook URL; `ngrok http 8000`), Supabase project. Everything works in mock mode until keys exist.
- **Two spec conflicts to tell the team**: coordinates are `x,z` (not `x,y`), and Gemini returns zone-level actions (never coordinates) — teammates writing prompts or the Swift exporter should follow the MVP spec's shapes.
- **Team split still holds**: a teammate can own the Swift RoomPlan exporter against `packages/contracts/skeleton.schema.json` while the prompt builds everything else; the prompt's iteration 4 will produce a working module if nobody else does.
