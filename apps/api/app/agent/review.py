"""Skill step 4 on the server: run the interior-designer's own scripts/validate_layout.py on a solved option, and turn warnings into plain tradeoffs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.agent import scene, skill
from app.models import FurnitureItem, LayoutItem, RoomSkeleton, ValidationResult, Zone
from app.solver.units import format_length_imperial

_METERS = re.compile(r"(\d+(?:\.\d+)?) m\b")


def skill_input(sk: RoomSkeleton, catalog: Mapping[str, FurnitureItem], items: list[LayoutItem], base_items: list[LayoutItem],
                new_zones: list[Zone] | None = None) -> dict[str, Any]:
    """An option in the shape of the skill's assets/sample_room.json (room, furniture, base_items, items, clear_zones)."""
    now = scene.scene(sk, items, catalog)
    before = scene.scene(sk, base_items, catalog)
    return {"room": now["room"], "furniture": {**before["furniture"], **now["furniture"]}, "base_items": before["base_items"],
            "items": now["base_items"], "clear_zones": [{"label": z.label, "w": z.w, "d": z.d} for z in new_zones or []]}


def skill_validate(sk: RoomSkeleton, catalog: Mapping[str, FurnitureItem], items: list[LayoutItem], base_items: list[LayoutItem],
                   new_zones: list[Zone] | None = None) -> dict[str, Any]:
    """validate_layout.validate() from the copied skill, unmodified. Returns its {ok, violations, warnings, metrics}."""
    data = skill_input(sk, catalog, items, base_items, new_zones)
    return skill.script("validate_layout").validate(
        data["room"], data["furniture"], data["items"], clear_zones=data["clear_zones"], base_items=data["base_items"])


def imperial(text: str) -> str:
    """'less than 0.75 m of room' -> 'less than 2' 6" of room' (the skill talks to US users in feet and inches)."""
    return _METERS.sub(lambda m: format_length_imperial(float(m.group(1))), text)


def measured_warnings(app: ValidationResult, before: ValidationResult, review: dict[str, Any], review_before: dict[str, Any],
                      catalog: Mapping[str, FurnitureItem], items: list[LayoutItem]) -> list[str]:
    """Warnings this option adds over the Current Room, one plain sentence each, app and skill merged by (rule, item)."""
    names = {it.id: (catalog[it.furnitureId].name.lower() if it.furnitureId in catalog else it.id) for it in items}
    old = {(v.rule, tuple(v.items)) for v in before.violations} | {(w["rule"], tuple(w["items"])) for w in review_before.get("warnings", [])}
    out: dict[tuple[str, str], str] = {}
    for v in app.violations:
        if v.severity != "warning" or (v.rule, tuple(v.items)) in old:
            continue
        name = names.get(v.items[0], "piece") if v.items else "piece"
        text = {
            "access_edge": f"There's less than 2' 6\" of room at the {name} to get in, sit or open it.",
            "window_keep_clear": f"The {name} stands in front of the window and blocks some light.",
            "clear_zone": imperial(v.message) + ".",
        }.get(v.rule, imperial(v.message) + ".")
        out[(v.rule, v.items[0] if v.items else "")] = text
    base_ids = {it.id for it in items}
    for w in review.get("warnings", []):
        key = (w["rule"], w["items"][0] if w["items"] else "")
        if key[1] in base_ids and key not in out and (w["rule"], tuple(w["items"])) not in old:
            text = imperial(w["message"])
            for it in items:
                if it.furnitureId in catalog:
                    text = text.replace(f"the {catalog[it.furnitureId].name}", f"the {names[it.id]}")
            out[key] = text
    return list(out.values())


def moved_ids(items: list[LayoutItem], base_items: list[LayoutItem]) -> list[str]:
    before = {b.id: b for b in base_items}
    return [it.id for it in items if (b := before.get(it.id)) is None or (b.x, b.z, b.rotation) != (it.x, it.z, it.rotation)]


def complete_tradeoff(tradeoff: str | None, warnings: list[str], floor_before: float, floor_after: float, items_named: list[str]) -> str:
    """Every option has a downside (SKILL.md step 5). Keep the designer's own sentence; add any measured warning it doesn't cover."""
    text = (tradeoff or "").strip()
    for w in warnings:
        if not any(n and n in text.lower() and n in w.lower() for n in items_named):
            text = f"{text} {w}".strip()
    if not text:
        lost = round(floor_before - floor_after)
        text = f"It uses about {lost}% more of your open floor." if lost > 0 else "Nothing big: the rest of the room stays as it is."
    return text
