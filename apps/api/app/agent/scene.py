"""The 3D editor's scene, written the way the interior-designer skill reads rooms (references/room-data.md).

The designer never sees the render. It reads the same numbers the editor draws from: the skeleton
(apps/web/src/scene/Room.tsx places openings at `wall offset` along each wall, walls at `height`) and
each item (Furniture.tsx puts the model at x/z, turns it by `rotation` like three.js rotation.y, and
scales the GLB to w/d/h). `scene()` is that data in the skill's format; `facts()` says in words what
the editor shows (which wall a piece stands against, which way its front faces, what's in front of
the window), so Gemini doesn't have to do trigonometry to picture the room.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from app.models import FurnitureItem, LayoutItem, RoomSkeleton
from app.solver.grid import front_dir, item_rect, rects_overlap
from app.solver.skeleton import (
    Rect,
    opening_span,
    wall_by_compass,
    wall_inward_normal,
    wall_length,
    window_band,
)
from app.solver.units import format_length_imperial

UNITS = ("meters; the floor is the x/z plane and y is up; an item's x, z is the center of its footprint; "
         "rotation is degrees like three.js rotation.y; at rotation 0 width runs along +x, depth along +z "
         "and the front (the side you use) faces +z, at 90 it faces +x, at 180 -z, at 270 -x")
# FurnitureKind -> the category words validate_layout.py understands ("floor" pieces are rugs and mats: underfoot)
SKILL_CATEGORY = {"floor": "rug"}
OUTLET_LEN = 0.1
TOUCH_M = 0.06
NEAR_M = 0.3


def _r(v: float) -> float:
    return round(v + 0.0, 3)


def _pt(p: tuple[float, float]) -> list[float]:
    return [_r(p[0]), _r(p[1])]


def compass(sk: RoomSkeleton, i: int) -> str:
    """Which side of the plan a wall is on, from its inward normal (north = min z, the top of the screen)."""
    nx, nz = wall_inward_normal(sk, i)
    if abs(nz) >= abs(nx):
        return "north" if nz > 0 else "south"
    return "west" if nx > 0 else "east"


def wall_names(sk: RoomSkeleton) -> list[str]:
    """'north wall' for the wall the solver resolves that phrase to; any other wall facing the same way gets its index."""
    names = []
    for i in range(len(sk.walls)):
        c = compass(sk, i)
        names.append(f"{c} wall" if wall_by_compass(sk, c) == i else f"{c}-facing wall {i}")  # type: ignore[arg-type]
    return names


def feet(m: float) -> str:
    return f"about {round(m / 0.3048)} ft"


def scene(sk: RoomSkeleton, items: list[LayoutItem], catalog: Mapping[str, FurnitureItem], style: str | None = None) -> dict[str, Any]:
    """Room + Current Room in the skill's format. `furniture` is keyed by instance id so two of the same piece stay distinct."""
    names = wall_names(sk)
    walls = [{"id": f"wall{i}", "name": names[i], "a": [w.x1, w.z1], "b": [w.x2, w.z2], "length": _r(wall_length(w)), "height": w.height}
             for i, w in enumerate(sk.walls)]
    doors = []
    for n, d in enumerate(sk.doors, 1):
        a, b = opening_span(sk, d)
        doors.append({"id": f"door{n}", "wall": f"wall{d.wall}", "a": _pt(a), "b": _pt(b), "width": d.width, "height": d.height,
                      "swing": d.swing, "hinge": d.hinge})
    windows = []
    for n, w in enumerate(sk.windows, 1):
        a, b = opening_span(sk, w)
        windows.append({"id": f"window{n}", "wall": f"wall{w.wall}", "a": _pt(a), "b": _pt(b), "width": w.width,
                        "sill": w.sillHeight, "height": w.height})
    outlets = []
    for n, o in enumerate(sk.outlets, 1):
        wall = sk.walls[o.wall]
        dx, dz = (wall.x2 - wall.x1) / wall_length(wall), (wall.z2 - wall.z1) / wall_length(wall)
        a = (wall.x1 + dx * o.offset, wall.z1 + dz * o.offset)
        outlets.append({"id": f"outlet{n}", "wall": f"wall{o.wall}", "a": _pt(a), "b": _pt((a[0] + dx * OUTLET_LEN, a[1] + dz * OUTLET_LEN))})
    furniture: dict[str, Any] = {}
    placed = []
    for it in items:
        f = catalog.get(it.furnitureId)
        if f is None:
            continue
        furniture[it.id] = {"name": f.name, "category": SKILL_CATEGORY.get(f.kind, f.kind), "catalogId": f.id,
                            "w": f.dims.w, "d": f.dims.d, "h": f.dims.h, "estimated": f.estimated, "source": f.source}
        placed.append({"furnitureId": it.id, "x": it.x, "z": it.z, "rotation": it.rotation, "locked": it.locked,
                       **({"color": it.color} if it.color else {})})
    return {
        "units": UNITS,
        "room": {"floor_polygon": [list(p) for p in sk.floorPolygon], "ceiling_height": sk.dimensions.h, "walls": walls,
                 "doors": doors, "windows": windows, "outlets": outlets},
        "furniture": furniture,
        "base_items": placed,
        **({"style": style} if style else {}),
    }


def _corner_word(sk: RoomSkeleton, wall: int, t: float) -> str:
    """Where along a wall a point at fraction t sits, named by the neighbouring wall ('near the east corner')."""
    n = len(sk.walls)
    if t < 1 / 3:
        return f"near the {compass(sk, (wall - 1) % n)} corner"
    if t > 2 / 3:
        return f"near the {compass(sk, (wall + 1) % n)} corner"
    return "in the middle"


def _opening_where(sk: RoomSkeleton, o: Any) -> str:
    t = (o.offset + o.width / 2) / wall_length(sk.walls[o.wall])
    return _corner_word(sk, o.wall, t)


def say_back(sk: RoomSkeleton, purpose: str | None = None) -> str:
    """SKILL.md step 1: the room in one plain sentence, e.g. 'A 3.4 by 3 m bedroom (about 11 by 10 ft), window ...'."""
    names = wall_names(sk)
    kind = (purpose or "room").split(";")[0].split(",")[0].strip() or "room"
    kind = f"{kind} room" if kind in ("living", "dining", "family", "guest") else kind
    xs, zs = [p[0] for p in sk.floorPolygon], [p[1] for p in sk.floorPolygon]
    l, w = max(xs) - min(xs), max(zs) - min(zs)
    shape = "" if len(sk.floorPolygon) == 4 else "L-shaped " if len(sk.floorPolygon) == 6 else f"{len(sk.floorPolygon)}-sided "
    parts = [f"A {l:g} by {w:g} m {shape}{kind} (about {round(l / 0.3048)} by {round(w / 0.3048)} ft)"]
    by_wall: dict[int, list[Any]] = {}
    for win in sk.windows:
        by_wall.setdefault(win.wall, []).append(win)
    for wall, wins in by_wall.items():
        parts.append(f"window {_opening_where(sk, wins[0])} of the {names[wall]}" if len(wins) == 1 else f"{len(wins)} windows on the {names[wall]}")
    for d in sk.doors:
        parts.append(f"door on the {names[d.wall]} {_opening_where(sk, d)}".replace(" in the middle", ", in the middle"))
    return ", ".join(parts) + "."


def _touching(sk: RoomSkeleton, r: Rect) -> list[int]:
    """Walls a footprint stands against: at least 10 cm of the wall within TOUCH_M of the rect."""
    out = []
    for i, w in enumerate(sk.walls):
        length = wall_length(w)
        steps = max(1, int(length / 0.05))
        hits = 0
        for s in range(steps + 1):
            px, pz = w.x1 + (w.x2 - w.x1) * s / steps, w.z1 + (w.z2 - w.z1) * s / steps
            dx, dz = max(r.x0 - px, 0, px - r.x1), max(r.z0 - pz, 0, pz - r.z1)
            if math.hypot(dx, dz) <= TOUCH_M:
                hits += 1
        if hits * length / steps >= 0.1:
            out.append(i)
    return out


def _gap(a: Rect, b: Rect) -> float:
    return math.hypot(max(b.x0 - a.x1, a.x0 - b.x1, 0), max(b.z0 - a.z1, a.z0 - b.z1, 0))


def _in_front(sk: RoomSkeleton, it: LayoutItem, r: Rect, others: dict[str, Rect], names: list[str], label: Mapping[str, str]) -> str:
    """What the front of a piece looks at, and how much open floor there is before it: a 5 cm ray march from the front edge."""
    from app.solver.skeleton import point_in_polygon

    dx, dz = front_dir(it.rotation)
    cx, cz = (r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2
    ox = r.x1 if dx > 0 else r.x0 if dx < 0 else cx
    oz = r.z1 if dz > 0 else r.z0 if dz < 0 else cz
    half = (r.z1 - r.z0) / 2 if dx else (r.x1 - r.x0) / 2
    for step in range(1, 200):
        d = step * 0.05
        # a strip as wide as the piece, 5 cm deep, d metres out
        strip = Rect(min(ox + dx * (d - 0.05), ox + dx * d) if dx else cx - half, min(oz + dz * (d - 0.05), oz + dz * d) if dz else cz - half,
                     max(ox + dx * (d - 0.05), ox + dx * d) if dx else cx + half, max(oz + dz * (d - 0.05), oz + dz * d) if dz else cz + half)
        hit = next((k for k, o in others.items() if rects_overlap(strip, o)), None)
        if hit:
            return f"{format_length_imperial(d - 0.05)} ({d - 0.05:.2f} m) of open floor, then the {label[hit]}"
        if not point_in_polygon(ox + dx * (d - 0.025), oz + dz * (d - 0.025), sk.floorPolygon):
            wall = min(range(len(sk.walls)), key=lambda i: _seg_dist(sk, i, ox + dx * d, oz + dz * d))
            return f"{format_length_imperial(d - 0.05)} ({d - 0.05:.2f} m) of open floor, then the {names[wall]}"
    return "open floor"


def _seg_dist(sk: RoomSkeleton, i: int, px: float, pz: float) -> float:
    w = sk.walls[i]
    vx, vz = w.x2 - w.x1, w.z2 - w.z1
    t = max(0.0, min(1.0, ((px - w.x1) * vx + (pz - w.z1) * vz) / (vx * vx + vz * vz)))
    return math.hypot(px - (w.x1 + vx * t), pz - (w.z1 + vz * t))


FACING = {(0, 1): "south (+z)", (1, 0): "east (+x)", (0, -1): "north (-z)", (-1, 0): "west (-x)"}


def facts(sk: RoomSkeleton, items: list[LayoutItem], catalog: Mapping[str, FurnitureItem], purpose: str | None = None) -> list[str]:
    """Plain-language lines for what the 3D editor shows. Every line is computed from the same numbers as scene()."""
    names = wall_names(sk)
    lines = [say_back(sk, purpose)]
    for i, w in enumerate(sk.walls):
        lines.append(f"wall{i} is the {names[i]}: {wall_length(w):.2f} m long ({format_length_imperial(wall_length(w))}), {w.height} m tall.")
    for n, d in enumerate(sk.doors, 1):
        lines.append(f"door{n} is on the {names[d.wall]} {_opening_where(sk, d)}, {d.width} m wide and {d.height} m tall, swings "
                     f"{'into the room' if d.swing == 'in' else 'out of the room'} with the hinge on the {d.hinge}; its swing and the 0.9 m in front of it stay empty.")
    for n, w in enumerate(sk.windows, 1):
        lines.append(f"window{n} is on the {names[w.wall]} {_opening_where(sk, w)}, {w.width} m wide, sill {w.sillHeight} m above the floor, top at {w.sillHeight + w.height:.2f} m.")
    for n, o in enumerate(sk.outlets, 1):
        t = o.offset / wall_length(sk.walls[o.wall])
        lines.append(f"outlet{n} is on the {names[o.wall]} {_corner_word(sk, o.wall, t)}.")

    rects: dict[str, Rect] = {}
    label: dict[str, str] = {}
    for it in items:
        f = catalog.get(it.furnitureId)
        if f:
            rects[it.id] = item_rect(it.x, it.z, it.rotation, f.dims)
            label[it.id] = f"{f.name.lower()} ({it.id})"
    solid = {k: r for k, r in rects.items() if catalog[next(i.furnitureId for i in items if i.id == k)].kind != "floor"}
    if not items:
        lines.append("The Current Room is empty.")
    for it in items:
        f = catalog.get(it.furnitureId)
        if f is None:
            lines.append(f"{it.id}: unknown furniture '{it.furnitureId}', left out of the scene.")
            continue
        r = rects[it.id]
        against = [names[i] for i in _touching(sk, r)]
        parts = [f"{it.id} is a {f.name.lower()}, {f.dims.w} m wide x {f.dims.d} m deep x {f.dims.h} m tall"
                 + (" (size estimated from a photo)" if f.estimated else "")
                 + f"; it covers x {r.x0:.2f} to {r.x1:.2f} and z {r.z0:.2f} to {r.z1:.2f}"
                 + (", LOCKED (never move it)" if it.locked else "")]
        parts.append("stands against the " + " and ".join(against) if against else "stands in open floor, away from the walls")
        if f.kind == "floor":
            parts.append("lies flat on the floor; things can stand on it")
        else:
            facing = FACING[front_dir(it.rotation)]
            others = {k: o for k, o in solid.items() if k != it.id}
            parts.append(f"its front faces {facing}, with {_in_front(sk, it, r, others, names, label)}")
        for n, w in enumerate(sk.windows, 1):
            if f.kind != "floor" and rects_overlap(window_band(sk, w, 0.6), r):
                parts.append(f"it is taller than window{n}'s sill and blocks part of it" if f.dims.h > w.sillHeight else f"it sits under window{n}, below the sill")
        for n, d in enumerate(sk.doors, 1):
            a, b = opening_span(sk, d)
            if _gap(r, Rect(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))) <= 1.0:
                parts.append(f"it is within 1 m of door{n}")
        near = sorted(label[k] for k, o in rects.items() if k != it.id and _gap(r, o) <= NEAR_M)
        if near:
            parts.append("next to the " + ", the ".join(near))
        lines.append("; ".join(parts) + ".")
    return lines
