# Interior-designer skill in Gemini

Gemini plans every room request with the `interior-designer` skill. The API carries an unedited copy of that skill; nothing in it is rewritten for the app.

## Where the skill lives

`apps/api/app/agent/interior-designer/` is a byte-for-byte copy of the skill folder: `SKILL.md`, `references/`, `scripts/` and `assets/`. `apps/api/app/agent/interior-designer.lock.json` records each file's sha256. The tests and `make designer-check` fail if the copy changes.

To take a new version of the skill, re-copy it rather than editing the files:

```sh
.venv/bin/python apps/api/scripts/check_designer.py --sync ~/.claude/skills/<...>/interior-designer
```

## What Gemini receives

`app/agent/prompts.py` builds the system prompt in this order:

1. **`SKILL.md`, verbatim**, followed by the references the skill tells the designer to read:
   - Always: `room-data.md`, `space-planning.md` and `options-output.md`.
   - `accessible-design.md` when the request, a remembered preference or the room's purpose mentions a wheelchair, cane, walker, low vision, and similar.
   - `style-and-color.md` when style or color is asked about. Furnishing a room from a theme always includes it.
2. **`<app-runtime>`**, a short section written for this app. It sits outside the skill and says who does each of the skill's five steps. Gemini can't run the skill's scripts, so:
   - Gemini reads the room, works out the intent, and proposes 1 to 3 options at zone level ("window wall, beside window"). It never outputs coordinates.
   - The server's solver places each option.
   - The server runs the skill's `validate_layout.py` and the app's validator on every option.
   - Gemini ranks the options and writes the explanation, tradeoff and reply.
3. **`<scene>`**: the room and the Current Room in the skill's `room-data.md` format. It is built from the same numbers the 3D editor draws:
   - Walls are drawn at their `height`.
   - Doors and windows are placed at `offset` along their wall, with sill and height.
   - Items use x/z at the footprint center, and `rotation` works like three.js `rotation.y`, with the front facing +z at 0.
   - The editor stretches each model to w/d/h.
4. **`<scene-facts>`**: the same scene in plain sentences, so Gemini doesn't have to do geometry to picture the room. Each piece gets its walls, the direction its front faces, the open floor in front of it before the next piece or wall, whether it blocks a window, and its neighbours.
5. **`<current-check>`**: open floor, walking room and existing warnings from the app's validator. Then the remembered preferences and any imported item.

The plan schema adds three optional fields: `roomSummary`, `options` (at most 3) and `recommended`. The top-level `variantName`, `actions` and `constraints` repeat the favorite option, so older clients still work.

## What the server does with the options

In `app/agent/pipeline.py`, the favorite is solved first. Locks, keep-clears and clear zones apply to every option; the favorite's adjacency constraint applies only to the favorite. For each option:

1. The solver places it (with the existing advanced-solver fallback).
2. The skill's `validate_layout.py` checks it, unchanged, through `app/agent/review.py`.
3. The option is dropped if either validator reports an error, or if it is an exact duplicate of an earlier option.

Each surviving option is saved as a named variant and returned in `options`:

```json
{"variantName", "layoutId", "recommended", "moved", "explanation", "tradeoff",
 "validation": {"ok", "warnings", "openFloorPct"},
 "skillValidation": {"ok", "warnings", "open_floor_pct"}}
```

`layout` stays the recommended variant, and the editor opens it. The tradeoff always includes any new measured warning, in feet and inches. If nothing passes, the reply says how far off it is. It suggests another wall only when the solver actually found a spot there.

The furnishing path ("What should this room be?") also receives the skill, its style reference and the scene, ahead of its own instructions.

## Conversation

The designer is a chat, in the editor's **Your designer** panel and over iMessage.

- **Memory:** the server sends Gemini this person's last 6 exchanges about the room as real turns. Follow-ups like "ok, remove the plant then" or "yes, do it" build on what was said, and a question isn't asked twice.
- **Starting point:** each message starts from the layout that's open. Every change is saved as a new variant, and the reply's option buttons open it.
- **Intents:**

  | Intent | What happens |
  |---|---|
  | `fit_item` | Add, move, rotate or remove one or more pieces. "Clear everything out" removes each unlocked piece. |
  | `make_space` | Moves or removals plus a clear area for an activity. |
  | `redesign` | A new design plan for the room (`theme`). The furnishing flow places catalog pieces around what's already there. |
  | `answer` | Questions and advice. The room doesn't change. |
  | `clarify` | Only when Gemini truly can't act. |

- **Catalog:** the prompt's `<catalog>` lists every piece that can be added: presets plus confirmed imports.
- **Plans without actions:** Gemini gets one retry. The reply is never an empty string or "null".

## Gemini models and limits

`GEMINI_MODEL` defaults to `gemini-3.8-flash`. `gemini-2.5-flash` is no longer offered to new keys.

When a model is busy (503), out of quota (429), retired (404) or times out after 30 s, the next model in `GEMINI_FALLBACK_MODELS` answers. The default order is:

`gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-flash-latest`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`

Chat calls use low reasoning, which takes about 4 to 10 s per message instead of 10 to 20. The free tier allows **20 requests a day per model**, so a busy day of testing moves the app down the chain. Billing on the Google project removes that limit.

If every model fails, the offline planner answers, and the reply starts by saying so.

## Solver change the skill exposed

Before this change, a clear zone such as a yoga space could overlap the door's swing and 0.9 m clearance. A zone that didn't fit was also saved at a smaller size and reported as a fit. The skill's validator rejects both. Clear zones are now searched only on floor outside the door area. A zone that doesn't fit is reported with the largest space actually available.

## The merge check

```sh
make designer-check                      # or: .venv/bin/python apps/api/scripts/check_designer.py [--json out.json] [--no-live]
```

`tests/test_interior_designer.py` runs checks A to C in the normal suite. SKIP is not a pass.

| Group | Check | What it proves |
|---|---|---|
| A. Skill fidelity | Copy matches the lock, and the installed skill when it can be found | The skill is not re-written for the app |
| | The prompt carries `SKILL.md` and the references verbatim | Gemini gets the real skill, including the read-when-needed references |
| | The skill's own sample runs as documented | Its scripts work as shipped |
| B. 3D understanding | The prompt's `<scene>` round-trips to the editor's data | Every wall, opening, outlet and item arrives unchanged. For each item, the skill's box, the app's footprint and three.js's rotated +z all agree, at 0/90/180/270° |
| | Scene facts cover every opening and item | The room description names every door and window wall, and each item's lock is stated |
| | The skill's validator agrees with the app's | Over sample and 150 random layouts per room: bounds, overlap and locks agree 100%. The app's door rule may be stricter (it adds the swing arc) but never looser |
| | GLB models | `inspect_glb.py` measures every model in the editor. Beds and seating have their tall back at -z, so the rendered front matches the data |
| C. Designer behavior | Requests on every sample room | Each answer has 1 to 3 distinct options, each passing both validators, with locks kept, an explanation and a tradeoff, and none of the skill's banned words. A too-big item gets an honest miss |
| D. Live Gemini | Quiz, run only with `GEMINI_API_KEY` | Gemini answers room size, door and window walls, and each item's walls, facing, lock and window blocking from the production prompt. It needs at least 90% correct against geometry; the score from the bare scene JSON is also reported |
| | Live plan | A real plan has 1 to 3 options, a room description, locks the bed, and uses plain words |

## Known notes

- The rug and yoga-mat models are turned 90° compared with their catalog sizes. The editor stretches them to the catalog footprint, so placement is unaffected, but the render looks stretched. Fix the assets or swap their catalog w/d.
- Check D has not been run here: there is no Gemini key in this environment. Run `make designer-check` with the key before merging.
- Mock plans (`fixtures/plans/*.json`) are room-agnostic. The yoga plan moves a nightstand, so it honestly fails in rooms without one.
