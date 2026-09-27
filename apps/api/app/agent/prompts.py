"""Stage 0 context -> the Stage 1 system prompt. Every Gemini call starts with the Interior Designer instructions (designer.md,
adapted from the interior-designer skill) and the user's Backboard memory; the model picks the intent and its inputs only, and the
Python solver owns coordinates."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from app.models import FurnitureItem, Layout, RoomSkeleton
from app.solver.zones import wall_label

DESIGNER = (Path(__file__).with_name("designer.md")).read_text()
_NEVER_MOVE = re.compile(r"\b(?:never|don'?t ever|do not ever)\s+(?:move|touch|shift)\s+(?:the|my)\s+([a-z][a-z _-]*?)\s*(?:\bagain\b|\bever\b|[.,;!?]|$)", re.IGNORECASE)


def memory_locks(memories: list[str]) -> list[str]:
    """Items the user said must never move ("never move the bed" -> "bed"); the solver treats them as locked."""
    return [m.group(1).strip() for text in memories for m in _NEVER_MOVE.finditer(text)]


def stated_preferences(text: str) -> list[str]:
    """Durable rules stated in a request ("never move my bed") written back to Backboard even if Gemini didn't list them."""
    return [f"never move the {item}" for item in memory_locks([text])]


def build_system_prompt(
    skeleton: RoomSkeleton,
    source: Layout,
    furniture: Mapping[str, FurnitureItem],
    memories: list[str],
    recent_requests: list[str],
    variants: list[Layout],
    imported: FurnitureItem | None,
) -> str:
    memory = "\n".join(f"- {m}" for m in memories) or "- (none yet)"
    recent = "\n".join(f"- {r}" for r in recent_requests) or "- (none)"
    walls = [f"wall {i}: {wall_label(skeleton, i)}, {round(((w.x2 - w.x1) ** 2 + (w.z2 - w.z1) ** 2) ** 0.5, 2)} m" for i, w in enumerate(skeleton.walls)]
    items = []
    for it in source.items:
        f = furniture.get(it.furnitureId)
        dims = f"{f.dims.w}x{f.dims.d}x{f.dims.h} m, kind {f.kind}" if f else "unknown dims"
        items.append(f"- {it.id}: {f.name if f else it.furnitureId} ({dims}){' LOCKED' if it.locked else ''}")
    layouts = [
        f"- {l.id}: '{l.name}' ({l.kind}; open floor {l.metrics.openFloor if l.metrics else '?'}%, conflicts {l.metrics.conflicts if l.metrics else '?'}, "
        f"{'has a desk' if any(furniture.get(i.furnitureId) and furniture[i.furnitureId].kind == 'desk' for i in l.items) else 'no desk'})"
        for l in variants
    ]
    imported_line = (
        f"\nThe user is asking about this item: {imported.name}, {imported.dims.w}x{imported.dims.d}x{imported.dims.h} m, kind {imported.kind}"
        f"{f', ${imported.price:.0f}' if imported.price else ''}. Use it as `item` (type '{imported.kind}')."
        if imported else ""
    )
    return (
        DESIGNER + "\n\n"
        "USER MEMORY (Backboard). Lines starting with 'never' are non-negotiable: add a lock constraint for that item.\n"
        f"{memory}\nRECENT REQUESTS FOR THIS ROOM:\n{recent}\n\n"
        "THE ROOM\n"
        f"Room {skeleton.dimensions.l} x {skeleton.dimensions.w} m, ceiling {skeleton.dimensions.h} m. Walls:\n" + "\n".join(walls) + "\n"
        f"Doors: {json.dumps([{'wall': d.wall, 'width': d.width, 'swing': d.swing} for d in skeleton.doors])}\n"
        f"Windows: {json.dumps([{'wall': w.wall, 'width': w.width, 'sillHeight': w.sillHeight} for w in skeleton.windows])}\n"
        f"Layout being changed, '{source.name}':\n" + ("\n".join(items) or "- (empty)") + imported_line + "\n"
        "Saved layouts in this room:\n" + "\n".join(layouts) + "\n\n"
        "YOUR JOB NOW: read the request and return ONLY the plan JSON: which tool to use (intent) and its inputs. You never output "
        "coordinates or positions: a Python solver places items (up to 3 options) and a validator checks them; you word the result later.\n"
        "Intents:\n"
        "- fit_item: will an item fit (optionally near a feature)? Fill `item` (type, dims in meters if stated, price) and constraints such as "
        "{type: adjacent, item: desk, feature: window} and {type: lock, item: bed}.\n"
        "- make_space: clear floor for an activity. Add {type: clear_zone, w_m, d_m, label} (yoga mat default 1.8 x 1.2) and locks for what must stay.\n"
        "- keep_clear: keep a window or the door swing free, e.g. {type: keep_clear, item: desk, feature: window}.\n"
        "- rank_variants: which saved layout is better for a purpose. Fill `ranking` with the layout ids above, best first, one short reason each.\n"
        "- rent_check: is my rent fair for this room? Fill `rent` (askingRent, zip, issues they mention). The app does the math.\n"
        "- payment_check: can I safely pay a deposit / application fee / rent? Fill `payment` (purpose, amount). The app applies NYC limits.\n"
        "- clarify: anything else, or you truly can't act (e.g. no amount for a payment). Ask exactly one question in `question`.\n"
        "Always add a lock constraint for every LOCKED item and every 'never move' memory. `feature` is one of window, door, wall, outlet. "
        "variantName is a short tab label (<= 30 chars). explanation is one friendly sentence. "
        "preferences lists durable facts the user just stated (e.g. 'never move the bed', 'does yoga every morning'), else []."
    )
