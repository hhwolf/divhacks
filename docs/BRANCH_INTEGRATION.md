# Branch integration decisions

This records how the active branches were combined while keeping the deployed application's authentication, room model and payment safeguards. It is an integration record, not a deployment receipt. The dated session log and backlog describe their original branch at the time they were written.

## Source revisions

These are the remote revisions reviewed for this integration; branch names can move afterward.

| Branch | Reviewed revision | Role |
|---|---|---|
| `origin/main` | `89aaf1455a962653a9aa31a420af460153496ecd` | Existing room lifecycle, authentication, housing comparisons and guarded payments |
| `origin/build-adaptive-room-planner` | `14d3feae64f73c7617ac8851e7c144c2ffc7e673` | Continuing designer, mobile and furniture work |
| `origin/feature/siddhi.m/checking-for-workflow` | `02f6de4f73f6e6902aafa93e24aca0763eea3c98` | Visual design, onboarding, furnishings and sample room |
| `origin/backend` | `d2b41250157de3447a4c95964c94e6ee3e2c7ab3` | Selectively adapted placement and local USDZ conversion tooling |

## Preserved application behavior

- Supabase sessions and scoped API repositories retain ownership checks for rooms, layouts, housing evidence and financial data. Anonymous demo sessions remain separate from signed-in workspaces.
- The room skeleton remains immutable. A replacement scan creates a new room; agent and furnishing results create variants instead of replacing Current Room. Structured `RoomElement` setup and `RoomDraft` remain the mobile capture-to-setup contract.
- Housing comparisons still use confirmed physical floor area and documented comparables. Rearranging or furnishing a room does not change that area or introduce a condition discount.
- Quotes, cumulative fee/deposit checks, authenticated Stripe test checkout and the Postgres ledger retain their existing lifecycle. Live payments remain disabled. Deleting a room removes its condition evidence and layouts while retaining financial records.
- Photon uses the signed webhook and verified account linkage. Imported dimensions still require confirmation before a fit recommendation. Preference memory and Backboard assistant identifiers persist across requests.
- The existing Vercel projects, environment conventions, server-only credentials and zero-credential demo remain supported. Supabase, private Vercel Blob snapshots and local JSON retain their configured document-storage roles; none replaces the financial ledger.
- Mobile remains on Expo SDK 54 and React Native 0.81, with its RoomPlan module, capture-event crash fixes, EAS configuration and Xcode 16 Podfile plugin. The native WebView retains its trusted-origin session injection. The feature branch's SDK upgrade, account-unlinking `app.config.js` and unauthenticated iframe editor were not adopted.

See [housing setup and production gates](HOUSING_PAYMENTS.md) for authentication, payment migrations, data provenance and credential requirements.

## Accepted visual and furnishing features

The integration keeps the neutral web materials and lighting, botanical mobile palette, welcome screens, redesigned mobile Home, room rename/delete controls and L-shaped sample. Native onboarding completion is persisted independently of the in-memory room draft. `expo-linear-gradient` uses the SDK 54-compatible `~15.0.8` package.

To try furnishing, create a clean room through scan/manual setup and open it in the editor. Use **What should this room be?** to enter a description such as “Cozy Japandi bedroom” or attach up to four inspiration photos. The result opens as a new variant; the response lists pieces placed and skipped. **Restyle** supplies a new theme for a variant.

The API exposes `POST /rooms/{room_id}/furnish` for text and `POST /rooms/{room_id}/furnish/photos` for multipart images. Both use the existing session and verify the room/base layout. Plans select catalog furniture; the server controls placement, validates the result, preserves existing items and protected clear areas, and skips additions that cannot fit. These paths do not generate arbitrary 3D meshes or authorize purchases.

With no Gemini credentials, text uses deterministic furniture kits and inspiration photos influence a local color/style heuristic. A configured Gemini integration can interpret inspiration photos; malformed or unavailable model output falls back to the deterministic path. Inspiration photos are a separate, explicitly selected furnishing input. Housing-condition evidence is never sent to the model. Image type, size and decoded-pixel limits are enforced and metadata is stripped before model input.

## Selective placement integration

The existing placement solver remains primary. The advanced solver is adapted as a fallback for supported single-item add/move requests when the primary solver fails. Unsupported actions or constraints keep the existing behavior rather than being silently dropped. Internal `PlacementPlan` models do not replace the public `AgentPlan` or financial contracts.

The adapted solver enforces explicit add-versus-move semantics, confirmed imported dimensions, item locks and remembered constraints. It rejects invalid/non-finite dimensions and model-provided coordinates. Required adjacency constraints are not relaxed in alternatives, and existing hard geometry errors cannot be reported as a successful placement. Suggestions about another wall are based on a tested placement there.

## Optional local USDZ inspection

RoomPlan's native JSON export remains the app's scan path. USDZ tooling is a local developer utility and is not added to Vercel's runtime dependencies or exposed as a public upload endpoint.

From the repository root, after normal setup:

```sh
.venv/bin/python -m pip install -r apps/api/requirements-usdz.txt
.venv/bin/python apps/api/scripts/inspect_usdz.py /path/to/room.usdz
.venv/bin/python apps/api/scripts/inspect_usdz.py /path/to/room.usdz --convert
.venv/bin/python -m pytest -q apps/api/tests/test_usdz.py
```

The utility prints stage units, axes, classified geometry and, with `--convert`, a canonical skeleton, detected objects and conversion report. Review the output before using it. Use trusted local exports; the CLI is not a sandbox for arbitrary USD assets. Tests requiring `usd-core` skip when it is absent, and the real-scan case requires an actual export at `fixtures/rooms/real_scan.usdz`. Synthetic conversion tests do not establish compatibility with every real RoomPlan export.

## Interior-designer skill for Gemini

The `backend` branch prompted Gemini with its own designer notes (`app/agent/designer.md`) and a separate narration stage. Neither was adopted. Instead, Gemini now receives an unedited copy of the `interior-designer` skill (`apps/api/app/agent/interior-designer/`, pinned by `interior-designer.lock.json`). It also receives the room as the 3D editor shows it, in the skill's own room format.

Each request can return up to 3 options. Each option is placed by the existing solver and checked by both the app's validator and the skill's `validate_layout.py`. Clear zones now stay out of the door's swing area. See [the interior-designer integration](INTERIOR_DESIGNER.md). `make designer-check` is the merge check; it includes a live Gemini comprehension quiz when `GEMINI_API_KEY` is set.

## Deferred backend changes

| Change not adopted | Reason and work needed before adoption |
|---|---|
| MongoDB repository replacement and DigitalOcean deployment configuration | They replace the existing Supabase/Vercel configuration and repository behavior. Adoption needs an explicit migration of ownership, document storage, financial retention and operational setup; merging them wholesale would regress the current application. |
| Raw scan uploads, public Blob storage and URL-based USDZ re-import | The alternate upload path does not preserve the current private-evidence/access model. A hosted version needs owner-bound object access, safe parsing/resource limits, validated fetches and deletion/retention rules. The local CLI preserves the conversion work without exposing that endpoint. |
| Base-layout promotion, restore lifecycle and compare-and-swap revision contract | The branch introduces a different Base/Current/variant model and new write preconditions. Existing web/mobile clients, geometry protections and saved records must migrate together. Concurrency checks remain useful future work, but accepting one side of this contract would break existing editing and Current Room guarantees. |
| Alternate unauthenticated/single-demo-user routes and replacement financial models | They conflict with the current account boundaries and transactional quote/payment lifecycle. The existing authentication and financial contracts stay authoritative. |

## Verification and remaining checks

Completed during integration: mobile TypeScript checks, iOS JavaScript export, Expo configuration validation and focused onboarding persistence checks; web lint, TypeScript checks, production build and 29 JavaScript tests; 33 focused furnishing tests; the full API suite (186 passed, one skipped real-scan fixture), including local Postgres payment and synthetic USDZ conversion tests. Browser checks passed for all 14 editor interactions, the housing/payment demo, Photon imports, and L-shaped-room furnishing/restyling. Exporting JavaScript does not test a native iPhone build or LiDAR capture.

Full integration-suite results and deployment verification belong in the integration PR/release report. Test counts in the historical records are not acceptance results for this combined branch. A real Gemini furnishing call, native photo picker/LiDAR capture, Supabase email delivery and an actual Stripe test charge still require their respective credentials or hardware.

Historical records: [September 26 session log](SESSION_LOG_2026-09-26.md) and [original branch backlog](BACKLOGS.md).
