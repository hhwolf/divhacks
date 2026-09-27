"""Stage 4: turn solver results into the Interior Designer's words (interior-designer skill voice).

`facts_for` extracts what actually happened (where each option put things, gaps, warnings, moves) so the wording can never claim
something the solver didn't do. `draft` writes it deterministically (mock mode, and the fallback); in live mode Gemini rewrites
the draft from the same facts (`Narration` schema) and `merge` keeps only well-formed parts of its answer.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from app.models import FurnitureItem, GeminiPlan, LayoutItem, Narration, OptionText, RoomSkeleton
from app.solver.constants import ACCESS_EDGE, M2_TO_SQFT, WINDOW_BAND
from app.solver.grid import front_dir, item_rect, rects_overlap
from app.solver.placement import SolveResult
from app.solver.skeleton import Rect, opening_span, room_bounds, window_band
from app.solver.units import format_length_imperial
from app.solver.zones import wall_label

FT_PER_M = 3.28084
WARNING_WORDS = {
    "access_edge": "there's less than 2 ft 6 in of room beside or in front of it",
    "window_keep_clear": "it stands in front of the window",
    "walkable_path": "it blocks the way from the door to the bed or desk",
    "clear_zone": "something sits in the open spot you asked for",
}


def feet(m: float) -> str:
    return f"{round(m * FT_PER_M * 2) / 2:g} ft"


def room_side(sk: RoomSkeleton, wall: int) -> str:
    """Plain position of a wall as seen in the editor's plan view (z toward the viewer)."""
    b, w = room_bounds(sk), sk.walls[wall]
    mx, mz = (w.x1 + w.x2) / 2, (w.z1 + w.z2) / 2
    sides = {"back": abs(mz - b.z0), "front": abs(mz - b.z1), "left": abs(mx - b.x0), "right": abs(mx - b.x1)}
    return min(sides, key=sides.get)  # type: ignore[arg-type]


def wall_name(sk: RoomSkeleton, wall: int) -> str:
    label = wall_label(sk, wall)
    return label if label in ("window wall", "door wall") else f"{room_side(sk, wall)} wall"


def room_summary(sk: RoomSkeleton) -> str:
    d = sk.dimensions
    parts = [f"A {feet(d.l).removesuffix(' ft')} by {feet(d.w)} room ({d.l:g} x {d.w:g} m)"]
    if sk.windows:
        parts.append(f"the window on the {room_side(sk, sk.windows[0].wall)} wall")
    if sk.doors:
        parts.append(f"the door on the {room_side(sk, sk.doors[0].wall)} wall")
    return (parts[0] + (", with " + " and ".join(parts[1:]) if len(parts) > 1 else "")) + "."


def _span_rect(sk: RoomSkeleton, opening: Any) -> Rect:
    a, b = opening_span(sk, opening)
    return Rect(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def _dist(a: Rect, b: Rect) -> float:
    return math.hypot(max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1)), max(0.0, max(a.z0, b.z0) - min(a.z1, b.z1)))


def _where_item(sk: RoomSkeleton, fur: FurnitureItem, it: LayoutItem, wall: int | None) -> tuple[str, str, bool, bool]:
    """(phrase, short name, beside_window, back_to_door) for where an item ended up."""
    r = item_rect(it.x, it.z, it.rotation, fur.dims)
    by_window = bool(sk.windows) and _dist(r, _span_rect(sk, sk.windows[0])) <= 0.3
    under_window = bool(sk.windows) and rects_overlap(r, window_band(sk, sk.windows[0], WINDOW_BAND))
    back_to_door = False
    if fur.kind == "desk" and sk.doors:
        a, b = opening_span(sk, sk.doors[0])
        fx, fz = front_dir(it.rotation)
        back_to_door = ((a[0] + b[0]) / 2 - it.x) * fx + ((a[1] + b[1]) / 2 - it.z) * fz > 0
    if wall is None:
        return "out on the open floor", "Open Floor", by_window, back_to_door
    w = sk.walls[wall]
    along_x = abs(w.x2 - w.x1) > abs(w.z2 - w.z1)
    flush = (r.x1 - r.x0 >= r.z1 - r.z0) == along_x
    name = wall_name(sk, wall)
    if under_window and fur.dims.h <= (sk.windows[0].sillHeight if sk.windows else 0):
        return f"under the window on the {name}", "Under Window", True, back_to_door
    if by_window:
        return (f"against the {name}, right beside the window" if flush else f"side-on to the {name}, right beside the window"), "by Window", True, back_to_door
    return (f"against the {name}" if flush else f"side-on to the {name}"), f"on {name.title().removesuffix(' Wall')} Wall", False, back_to_door


def _zone_where(sk: RoomSkeleton, z: Any) -> tuple[str, str]:
    b = room_bounds(sk)
    near_x = "left" if z.x - b.x0 < 0.05 else "right" if b.x1 - (z.x + z.w) < 0.05 else None
    near_z = "back" if z.z - b.z0 < 0.05 else "front" if b.z1 - (z.z + z.d) < 0.05 else None
    if near_x and near_z:
        return f"in the {near_z} {near_x} corner", f"{near_z.title()} {near_x.title()}"
    if near_x or near_z:
        side = near_x or near_z
        return f"along the {side} wall", f"{side.title()} Wall"
    return "in the middle of the room", "Middle"


def facts_for(sk: RoomSkeleton, catalog: Mapping[str, FurnitureItem], source: list[LayoutItem], plan: GeminiPlan, options: list[SolveResult], locked_names: list[str]) -> dict[str, Any]:
    area = sk.dimensions.l * sk.dimensions.w
    out: list[dict[str, Any]] = []
    for res in options:
        assert res.validation is not None
        f: dict[str, Any] = {
            "open_floor_pct": res.validation.metrics.openFloor,
            "warnings": [WARNING_WORDS.get(v.rule, v.message) for v in res.validation.violations if v.severity == "warning"],
            "relaxed": res.relaxed,
            "gap": format_length_imperial(res.gap_m) if res.gap_m is not None else None,
            "moves": [],
        }
        if res.placement is not None:
            fur = catalog[res.placement.furnitureId]
            placed = next(i for i in res.items if i.id == res.placement.item)
            phrase, short, by_window, back_to_door = _where_item(sk, fur, placed, res.wall)
            f.update(item=fur.name, item_kind=fur.kind, where=phrase, short=short, by_window=by_window, back_to_door=back_to_door, estimated=fur.estimated,
                     floor_used_sqft=round(fur.dims.w * fur.dims.d * M2_TO_SQFT))
        for m in res.moves:
            fur = catalog[m.furnitureId]
            moved = next(i for i in res.items if i.id == m.item)
            wall = min((i for i, _ in enumerate(sk.walls)), key=lambda i: _wall_distance(sk, i, moved, fur))
            f["moves"].append({"item": fur.name, "to": _where_item(sk, fur, moved, wall)[0]})
        if res.zones:
            z = res.zones[0]
            f.update(zone=f"{z.w:g} x {z.d:g} m", zone_where=_zone_where(sk, z)[0], zone_short=_zone_where(sk, z)[1], zone_label=z.label)
        out.append(f)
    keep = [c.feature for c in plan.constraints if c.type == "keep_clear" and c.feature] or (["window"] if plan.intent == "keep_clear" else [])
    return {"room_summary": room_summary(sk), "intent": plan.intent, "locked": locked_names, "keep_clear": keep, "options": out, "room_area_m2": round(area, 1)}


def _wall_distance(sk: RoomSkeleton, wall: int, it: LayoutItem, fur: FurnitureItem) -> float:
    w = sk.walls[wall]
    r = item_rect(it.x, it.z, it.rotation, fur.dims)
    return _dist(r, Rect(min(w.x1, w.x2), min(w.z1, w.z2), max(w.x1, w.x2), max(w.z1, w.z2)))


def _join(names: list[str]) -> str:
    names = [n.lower() for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def draft(plan: GeminiPlan, facts: dict[str, Any]) -> Narration:
    """Deterministic designer-voice wording from the facts (mock mode and the live fallback)."""
    opts = facts["options"]
    locked = facts["locked"]
    texts: list[OptionText] = []
    for i, f in enumerate(opts):
        if "item" in f:
            name = (plan.variantName if i == 0 and plan.variantName else f"{f['item'].split()[-1].title()} {f['short']}")
            why = []
            under = f["where"].startswith("under the window")
            if under:
                why.append("you get lots of daylight right in front of you")
            elif f["by_window"]:
                why.append("you get daylight from the side while you work" if f["item_kind"] == "desk" else "it gets the window light")
            if f["item_kind"] == "desk":
                why.append(f"there's at least {format_length_imperial(ACCESS_EDGE)} to pull out your chair")
            explanation = f"The {f['item'].lower()} goes {f['where']}" + (f"; {' and '.join(why)}." if why else ".")
            if locked:
                explanation += f" Your {_join(locked)} stay{'s' if len(locked) == 1 else ''} put."
            if f["relaxed"]:
                tradeoff = f"It isn't {' or '.join(f['relaxed'])}, which is what you asked for, but it's the next best wall."
            elif f["warnings"]:
                tradeoff = f"Heads up: {f['warnings'][0]}."
            elif under and f["item_kind"] == "desk":
                tradeoff = "Facing the window means glare on your screen on sunny days" + (", and your back is to the door." if f["back_to_door"] else ".")
            elif f["back_to_door"]:
                tradeoff = "You'd sit with your back to the door."
            elif f["gap"] and f["gap"] != "0 in":
                tradeoff = f"It's snug: only {f['gap']} to spare next to it."
            else:
                tradeoff = f"It takes about {f['floor_used_sqft']} sq ft of open floor."
            if f.get("estimated"):
                tradeoff += " The size is an estimate from a photo, so measure before you buy."
        elif "zone" in f:
            name = (plan.variantName if i == 0 and plan.variantName else f"{(f['zone_label'] or 'Open').split()[0].title()} {f['zone_short']}")
            moves = f["moves"]
            explanation = f"A clear {f['zone']} spot {f['zone_where']}" + (
                f": move the {_join([m['item'] for m in moves])} {moves[0]['to']} and you have it." if moves else ", and nothing has to move.")
            tradeoff = (f"You'll have to move the {_join([m['item'] for m in moves])} first." if moves
                        else "It's all the open floor in that spot, so keep it free of bags and laundry.")
        else:  # keep_clear
            moves = f["moves"]
            name = plan.variantName or "Clear View"
            what = " or ".join(f"the {f}" for f in facts["keep_clear"]) or "it"
            explanation = "Moved the " + "; the ".join(f"{m['item'].lower()} {m['to']}" for m in moves) + f", so nothing stands in front of {what}."
            tradeoff = "Things are in a new spot, so it may take a day to get used to."
        texts.append(OptionText(index=i, variantName=" ".join(name.split()[:4]), explanation=explanation, tradeoff=tradeoff))
    return Narration(room_summary=facts["room_summary"], options=texts, recommended_index=0, reply=_reply(plan, facts, texts))


def _reply(plan: GeminiPlan, facts: dict[str, Any], texts: list[OptionText]) -> str:
    f = facts["options"][0]
    more = f" I saved {len(texts)} layouts; {texts[0].variantName} is my pick." if len(texts) > 1 else f" It's saved as {texts[0].variantName}."
    locked = f", and your {_join(facts['locked'])} {'doesn' if len(facts['locked']) == 1 else 'don'}'t move" if facts["locked"] else ""
    if "item" in f:
        spare = f" with {f['gap']} to spare" if f["gap"] and f["gap"] != "0 in" else ""
        return f"Yes, it fits {f['where']}{spare}{locked}.{more}"
    if "zone" in f:
        moves = f"; just move the {_join([m['item'] for m in f['moves']])}" if f["moves"] else ""
        return f"Yes, there's a clear {f['zone']} spot {f['zone_where']}{moves}.{more}"
    what = " or ".join(f"the {k}" for k in facts["keep_clear"]) or "it"
    return f"Done: I moved the {_join([m['item'] for m in f['moves']])} so nothing blocks {what}.{more}"


def merge(base: Narration, live: dict[str, Any] | None, n_options: int) -> Narration:
    """Take Gemini's wording where it is well-formed; keep the draft for anything missing or out of range."""
    if not live:
        return base
    try:
        got = Narration.model_validate(live)
    except Exception:  # noqa: BLE001 - malformed model output: keep the deterministic draft
        return base
    by_index = {t.index: t for t in got.options if 0 <= t.index < n_options and t.variantName.strip() and t.explanation.strip() and t.tradeoff.strip()}
    options = [by_index.get(i, t) for i, t in enumerate(base.options)]
    rec = got.recommended_index if 0 <= got.recommended_index < n_options else base.recommended_index
    return Narration(room_summary=got.room_summary.strip() or base.room_summary, options=options, recommended_index=rec, reply=got.reply.strip() or base.reply)
