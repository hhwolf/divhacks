"""System prompt for Gemini: the interior-designer skill (verbatim), how this app runs its workflow, then the room as the 3D editor shows it.

The model reasons at zone level only; the Python solver owns coordinates and the skill's validate_layout.py re-checks every option.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from app.agent import scene, skill
from app.models import FurnitureItem, Layout, RoomSkeleton
from app.solver.validate import validate_layout

ZONE_VOCABULARY = (
    "window wall", "door wall", "north wall", "south wall", "east wall", "west wall", "beside window", "near window",
    "near door", "opposite the door", "near outlet", "corner", "centered",
)
SCENE_OPEN, SCENE_CLOSE = '<scene format="references/room-data.md">', "</scene>"

# Written for this app, kept outside the copied skill: it maps the skill's five steps onto what the server does.
RUNTIME = """<app-runtime>
You are the interior-designer skill above, running inside the Adaptive Room Planner through Gemini. The person is talking with you in the app's chat or over iMessage. Follow SKILL.md's voice and workflow; this section only says who does which step here, because you can't run scripts.

Conversation
- Earlier turns of this conversation come before the newest message. Use them: if the person answers your question or says "that one", "the sofa", "yes, do it", "undo that", continue from there. Never ask a question you already asked or that the conversation already answers.
- Be a flexible designer, not a form. Make a sensible assumption, say it in one line of reply, and act (SKILL.md step 2). Use clarify only when you truly can't act, and then ask one specific question.
- For questions, advice and small talk ("what do you think of my room?", "how do I make it feel bigger?", "what should I buy?"), use intent answer: reply in 1 to 4 plain sentences built on the real room numbers, suggest a concrete next step you can do, and leave actions empty. Nothing in the room changes.

Changing the room
- Step 1, read the room: <scene> is the room and the Current Room in the references/room-data.md format, built from the same numbers the 3D editor draws; <scene-facts> says the same in words; <catalog> lists every piece you can add. Put your one-sentence say-back in roomSummary.
- Step 2, pick the intent:
  fit_item: add, move, rotate or remove one or more pieces. An option may hold several actions ("add sofa + add coffee_table", "remove desk_6", or one remove per unlocked piece for "clear everything out").
  make_space: moves or removals plus a clear_zone constraint (w_m, d_m) for an activity.
  keep_clear, compare (rank existing layouts).
  redesign: a whole new design plan for the room ("recommend a layout for my study/bedroom", "make it japandi", "furnish it for guests", "suggest a new design"). Put the design in a few words in theme; the server picks and places catalog pieces around the locked ones and saves it as a new layout. Leave actions empty.
  answer, or clarify as above.
- Step 3, design: never write coordinates. Actions are zone-level and the server's solver places them. Zone phrases (combine with commas, give fallbacks with " or "): {vocabulary}; an empty zone lets the solver pick the best spot. Refer to pieces already in the room by their key in scene.furniture (for example bed_double_1); add pieces by their <catalog> id (the person may say "couch" for sofa, "pot" or "greenery" for plant, "lamp" for floor_lamp: map it). Never move or remove LOCKED pieces. Give 1 to 3 options that are really different ideas. Each option has variantName (1 to 3 plain words), actions, optional extra constraints, explanation (1 to 2 sentences, why it's good for this person) and tradeoff (1 honest sentence). Put your favorite first and name it in recommended, and copy its variantName, actions and constraints to the top level.
- Step 4, check: the server runs scripts/validate_layout.py and the app's own fit check on every option, drops any that fail and adds the measured warnings to the tradeoff. If none pass it tells the person how far off it is, so don't promise a fit you can't see in the numbers. When a piece doesn't fit where it was asked for (the fit check or an earlier turn says so), don't repeat that placement: offer a way to make room (move or remove unlocked pieces) or a smaller piece from <catalog>, and say which in reply.
- Step 5: output only JSON matching the response schema. reply is what the person reads in the chat or iMessage: answer first, conversational, no link (the server adds links).
- Sizes in reply, roomSummary, explanation and tradeoff are in feet and inches ("about 11 by 10 ft", "2 ft 6 in to pull out the chair"); if the person used metric, add the metric too. Meters stay in the JSON fields only.
- Add a lock constraint for every LOCKED item and every remembered "never move" preference. preferencesLearned lists durable facts the person told you (for example "never move the bed").
</app-runtime>"""

FURNISH_RUNTIME = """<app-runtime>
You are the interior-designer skill above, furnishing an empty room from a theme inside the Adaptive Room Planner. The <scene> and <scene-facts> are the room as the 3D editor shows it. Follow SKILL.md's voice and its space-planning and style references, but answer with the furnishing plan the instructions below describe; the server places every piece, checks it with the app's fit rules and skips anything that doesn't fit. Don't write coordinates.
</app-runtime>"""


def room_purpose(room: Mapping[str, object]) -> str | None:
    """'bedroom, study; wants: desk, yoga zone' from the room's post-scan profile, or None when it has none."""
    types = [str(t) for t in room.get("spaceTypes") or []]  # type: ignore[union-attr]
    wants = [str(e.get("label", e.get("id", ""))) if isinstance(e, dict) else str(e) for e in room.get("elements") or []]  # type: ignore[union-attr]
    if not types and not wants:
        return None
    return ", ".join(types) + (f"; wants: {', '.join(wants)}" if wants else "")


CATALOG_OPEN, CATALOG_CLOSE = "<catalog format=\"one JSON object per line\">", "</catalog>"


def catalog_block(furniture: Mapping[str, FurnitureItem]) -> str:
    """Every piece the designer can add: presets plus imports whose size the person confirmed. One JSON object per line."""
    rows = [{"id": f.id, "name": f.name, "kind": f.kind, "w": f.dims.w, "d": f.dims.d, "h": f.dims.h, **({"price": f.price} if f.price else {})}
            for f in furniture.values() if f.source == "preset" or f.dimensionsConfirmed]
    return CATALOG_OPEN + "\n" + "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n" + CATALOG_CLOSE


def parse_catalog(prompt: str) -> list[dict[str, object]]:
    start = prompt.index(CATALOG_OPEN) + len(CATALOG_OPEN)
    return [json.loads(line) for line in prompt[start:prompt.index(CATALOG_CLOSE, start)].strip().splitlines() if line.strip()]


def scene_block(skeleton: RoomSkeleton, base: Layout, furniture: Mapping[str, FurnitureItem], purpose: str | None) -> str:
    """<scene> JSON + <scene-facts> + the current fit check: everything the designer knows about the 3D view."""
    data = scene.scene(skeleton, base.items, furniture, base.style)
    check = validate_layout(skeleton, furniture, base.items, base.zones)
    lfr = check.metrics.largestFreeRect
    status = [f"Open floor {check.metrics.openFloor}%, walking room {check.metrics.walkability.lower()}"
              + (f", biggest open rectangle {lfr.w} x {lfr.d} m" if lfr else "") + "."]
    status += [f"{v.severity}: {v.message}." for v in check.violations]
    zones = [f"Kept-clear area '{z.label}': {z.w} x {z.d} m from x {z.x}, z {z.z}." for z in base.zones]
    return (
        f"{SCENE_OPEN}\n{json.dumps(data, separators=(',', ':'))}\n{SCENE_CLOSE}\n"
        "<scene-facts>\n" + "\n".join(f"- {line}" for line in scene.facts(skeleton, base.items, furniture, purpose) + zones) + "\n</scene-facts>\n"
        f"<current-check layout=\"{base.name}\">\n" + "\n".join(f"- {s}" for s in status) + "\n</current-check>"
    )


def parse_scene(prompt: str) -> dict[str, object]:
    """The <scene> JSON back out of a system prompt (used by the checks to prove the prompt carries the whole 3D view)."""
    start = prompt.index(SCENE_OPEN) + len(SCENE_OPEN)
    return json.loads(prompt[start:prompt.index(SCENE_CLOSE, start)])


def build_system_prompt(
    skeleton: RoomSkeleton, base: Layout, furniture: Mapping[str, FurnitureItem], memories: list[str], imported: FurnitureItem | None,
    purpose: str | None = None, request_text: str = "",
) -> str:
    imported_line = (f"The person is asking about this item (refer to it as '{imported.id}'): {imported.name}, {imported.dims.w} x {imported.dims.d} x "
                     f"{imported.dims.h} m, kind {imported.kind}{', size estimated from a photo' if imported.estimated else ''}.") if imported else ""
    return "\n\n".join(p for p in (
        skill.instructions(request_text, *memories, purpose),
        RUNTIME.replace("{vocabulary}", ", ".join(ZONE_VOCABULARY)),
        scene_block(skeleton, base, furniture, purpose),
        catalog_block(furniture),
        f"The person uses this space as: {purpose}." if purpose else "",
        "Remembered preferences (Backboard): " + ("; ".join(memories) if memories else "none") + ".",
        imported_line,
    ) if p)


def build_furnish_prompt(skeleton: RoomSkeleton, base: Layout, furniture: Mapping[str, FurnitureItem], purpose: str | None, theme: str) -> str:
    """The skill (with its style reference, since a theme is a style request), then the empty room, then the furnishing task."""
    return "\n\n".join((
        skill.instructions(theme, "style", purpose),
        FURNISH_RUNTIME,
        scene_block(skeleton, base, furniture, purpose),
    ))
