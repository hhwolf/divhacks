"""System prompt for the Gemini planner. The model reasons at zone level only; the Python solver owns coordinates."""

from __future__ import annotations

import json
from collections.abc import Mapping

from app.models import FurnitureItem, Layout, RoomSkeleton
from app.solver.zones import wall_label

ZONE_VOCABULARY = (
    "window wall", "door wall", "north wall", "south wall", "east wall", "west wall", "beside window", "near window",
    "near door", "opposite the door", "near outlet", "corner", "centered",
)


def build_system_prompt(skeleton: RoomSkeleton, base: Layout, furniture: Mapping[str, FurnitureItem], memories: list[str], imported: FurnitureItem | None) -> str:
    walls = [f"wall {i}: {wall_label(skeleton, i)} ({w.x1},{w.z1})->({w.x2},{w.z2})" for i, w in enumerate(w for w in skeleton.walls)]
    items = []
    for it in base.items:
        f = furniture.get(it.furnitureId)
        dims = f"{f.dims.w}x{f.dims.d}x{f.dims.h} m, kind {f.kind}" if f else "unknown dims"
        items.append(f"- {it.id} ({f.name if f else it.furnitureId}; {dims}) at x={it.x} z={it.z} rot={it.rotation}{' LOCKED' if it.locked else ''}")
    imported_line = f"\nThe user is asking about this item (refer to it as '{imported.id}'): {imported.name} {imported.dims.w}x{imported.dims.d}x{imported.dims.h} m, kind {imported.kind}." if imported else ""
    return (
        "You are the planner for Adaptive Room Planner, helping a NYC renter fit secondhand furniture into a small room.\n"
        f"Room {skeleton.dimensions.l} x {skeleton.dimensions.w} m, height {skeleton.dimensions.h} m. Walls:\n" + "\n".join(walls) + "\n"
        f"Doors: {json.dumps([d.model_dump() for d in skeleton.doors])}\nWindows: {json.dumps([w.model_dump() for w in skeleton.windows])}\n"
        f"Outlets: {json.dumps([o.model_dump() for o in skeleton.outlets])}\n"
        f"Current layout '{base.name}':\n" + "\n".join(items) + imported_line + "\n"
        "User memory: " + ("; ".join(memories) if memories else "none") + "\n\n"
        "Rules: never move LOCKED items (add a lock constraint for them). Output ONLY the plan JSON matching the schema. "
        "Actions are zone-level: use phrases from this vocabulary, combined with commas: " + ", ".join(ZONE_VOCABULARY) + ". "
        "Never output coordinates. Intents: fit_item (add/move one item), make_space (moves + a clear_zone constraint with w_m/d_m), "
        "keep_clear, compare, clarify (when the request is ambiguous; fill clarifyingQuestion). "
        "variantName is a short label (<= 30 chars). reply is one friendly sentence stating where the item goes and what stayed put. "
        "preferencesLearned lists durable facts about the user (e.g. 'never move the bed')."
    )
