"""Port of packages/geometry/src/validate.ts. Rule order, messages and rounding must match the TS validator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from app.models import FreeRect, FurnitureRef, LayoutItem, LayoutMetrics, RoomSkeleton, ValidationResult, Violation, Walkability, Zone
from app.solver.constants import ACCESS_EDGE, ACCESS_FREE_RATIO, CORRIDOR_CELLS, DOOR_CLEARANCE, EPS, STORAGE_FRONT, WINDOW_BAND, js_round
from app.solver.grid import (
    Grid,
    any_mask_in_rect,
    count_mask_in_rect,
    erode,
    fill_disc,
    fill_rect,
    flood_fill,
    footprint,
    front_dir,
    item_rect,
    largest_free_rect,
    make_grid,
    rect_cells,
    rect_neighbours,
    rects_overlap,
)
from app.solver.skeleton import Rect, door_clearance_rect, door_hinge, point_in_polygon, window_band

FurnitureLookup = Mapping[str, FurnitureRef]
Side = Literal["x0", "x1", "z0", "z1"]

BLOCKING = {"bounds", "overlap"}
_FITS: list[tuple[str, float, float]] = [
    ("a queen bed", 1.5, 2.0),
    ("a desk and chair", 1.2, 1.4),
    ("a yoga mat", 0.61, 1.83),
    ("a desk", 1.2, 0.6),
    ("an armchair", 0.9, 0.9),
    ("a nightstand", 0.45, 0.4),
]


def _round1(v: float) -> float:
    return js_round(v * 10) / 10


def _round2(v: float) -> float:
    return js_round(v * 100) / 100


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _name(fur: FurnitureLookup, it: LayoutItem) -> str:
    f = fur.get(it.furnitureId)
    return f.name if f else it.furnitureId


def _is_floor(fur: FurnitureLookup, it: LayoutItem) -> bool:
    f = fur.get(it.furnitureId)
    return f is not None and f.kind == "floor"


def _band_rect(r: Rect, side: Side, depth: float) -> Rect:
    if side == "x0":
        return Rect(r.x0 - depth, r.z0, r.x0, r.z1)
    if side == "x1":
        return Rect(r.x1, r.z0, r.x1 + depth, r.z1)
    if side == "z0":
        return Rect(r.x0, r.z0 - depth, r.x1, r.z0)
    return Rect(r.x0, r.z1, r.x1, r.z1 + depth)


def _band_free(g: Grid, occupied: bytearray, band: Rect) -> float:
    total, hit = count_mask_in_rect(g, occupied, band, True)
    return 0 if total == 0 else (total - hit) / total


def fits_label(w: float, d: float) -> str:
    a, b = max(w, d), min(w, d)
    for label, cw, cd in _FITS:
        if a + EPS >= max(cw, cd) and b + EPS >= min(cw, cd):
            return label
    return "not much"


def _nb_near_wide(g: Grid, wide: bytearray, k: int) -> bool:
    i = k % g.nx
    j = (k - i) // g.nx
    for dj in range(-CORRIDOR_CELLS, CORRIDOR_CELLS + 1):
        for di in range(-CORRIDOR_CELLS, CORRIDOR_CELLS + 1):
            ii, jj = i + di, j + dj
            if 0 <= ii < g.nx and 0 <= jj < g.nz and wide[jj * g.nx + ii]:
                return True
    return False


def door_keep_clear(g: Grid, sk: RoomSkeleton) -> tuple[bytearray, list[int]]:
    """Door clearance rect + inward swing disc as a mask (room cells only), plus the clearance cells used as flood-fill seeds."""
    keep_clear = bytearray(g.nx * g.nz)
    door_seeds: list[int] = []
    for d in sk.doors:
        clr = door_clearance_rect(sk, d, DOOR_CLEARANCE)
        fill_rect(g, keep_clear, clr)
        if d.swing == "in":
            hinge, radius = door_hinge(sk, d)
            fill_disc(g, keep_clear, hinge[0], hinge[1], radius)
        c = rect_cells(g, clr)
        for j in range(c.j0, c.j1):
            for i in range(c.i0, c.i1):
                door_seeds.append(j * g.nx + i)
    for k in range(g.nx * g.nz):
        if not g.room[k]:
            keep_clear[k] = 0
    return keep_clear, door_seeds


def validate_layout(
    skeleton: RoomSkeleton,
    furniture: FurnitureLookup,
    items: list[LayoutItem],
    zones: list[Zone] | None = None,
    base_items: list[LayoutItem] | None = None,
) -> ValidationResult:
    sk, fur = skeleton, furniture
    g = make_grid(sk)
    n_cells = g.nx * g.nz
    violations: list[Violation] = []
    rects: dict[str, Rect] = {}
    for it in items:
        f = fur.get(it.furnitureId)
        if f:
            rects[it.id] = item_rect(it.x, it.z, it.rotation, f.dims)

    # Occupancy by solid (non-floor) items.
    occupied = bytearray(n_cells)
    occupied_by: dict[str, bytearray] = {}
    for it in items:
        if it.id not in rects or _is_floor(fur, it):
            continue
        m = bytearray(n_cells)
        fill_rect(g, m, rects[it.id])
        occupied_by[it.id] = m
        for k in range(n_cells):
            if m[k]:
                occupied[k] = 1

    # 1. Room bounds: all four corners inside the polygon (inclusive).
    for it in items:
        r = rects.get(it.id)
        if r is None:
            continue
        cx, cz = (r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2
        corners = ((r.x0, r.z0), (r.x1, r.z0), (r.x0, r.z1), (r.x1, r.z1))
        inside = all(point_in_polygon(x + _sign(cx - x) * 1e-4, z + _sign(cz - z) * 1e-4, sk.floorPolygon) for x, z in corners)
        if not inside:
            violations.append(Violation(rule="bounds", severity="error", items=[it.id], message=f"{_name(fur, it)} is outside the room"))

    # 2. Overlap between solid items.
    solids = [it for it in items if it.id in rects and not _is_floor(fur, it)]
    for a in range(len(solids)):
        for b in range(a + 1, len(solids)):
            A, B = solids[a], solids[b]
            if rects_overlap(rects[A.id], rects[B.id]):
                violations.append(Violation(rule="overlap", severity="error", items=sorted([A.id, B.id]), message=f"{_name(fur, A)} overlaps {_name(fur, B)}"))

    # 3. Locked items unchanged vs base layout (agent context).
    if base_items is not None:
        by_id = {i.id: i for i in items}
        for b in base_items:
            if not b.locked:
                continue
            cur = by_id.get(b.id)
            if cur is None or abs(cur.x - b.x) > EPS or abs(cur.z - b.z) > EPS or cur.rotation != b.rotation:
                violations.append(Violation(rule="locked", severity="error", items=[b.id], message=f"{_name(fur, b)} is locked and was moved"))

    # 4. Door swing arc + 0.9 m clearance.
    keep_clear, door_seeds = door_keep_clear(g, sk)
    for it in solids:
        if any_mask_in_rect(g, keep_clear, rects[it.id]):
            violations.append(Violation(rule="door_clearance", severity="error", items=[it.id], message=f"{_name(fur, it)} blocks the door swing"))

    # 5. Window keep-clear (warning): items taller than the sill inside the window band.
    for w in sk.windows:
        band = window_band(sk, w, WINDOW_BAND)
        for it in solids:
            f = fur[it.furnitureId]
            if f.dims.h > w.sillHeight + EPS and rects_overlap(band, rects[it.id]):
                violations.append(Violation(rule="window_keep_clear", severity="warning", items=[it.id], message=f"{_name(fur, it)} is taller than the window sill and blocks the window"))

    # 6. Access edges: beds/desks one long edge; wardrobes/dressers the front.
    storage_reach: list[bool] = []
    for it in solids:
        f = fur[it.furnitureId]
        r = rects[it.id]
        others = bytearray(occupied)
        own = occupied_by[it.id]
        for k in range(n_cells):
            if own[k]:
                others[k] = 0
        if f.kind in ("bed", "desk"):
            fx, fz = footprint(f.dims, it.rotation)
            sides: list[Side] = ["z0", "z1"] if fx >= fz else ["x0", "x1"]
            free = [_band_free(g, others, _band_rect(r, s, ACCESS_EDGE)) for s in sides]
            if not any(v + EPS >= ACCESS_FREE_RATIO for v in free):
                violations.append(Violation(rule="access_edge", severity="warning", items=[it.id], message=f"{_name(fur, it)} has no free long edge ({js_round(ACCESS_EDGE * 100)} cm)"))
        elif f.kind in ("wardrobe", "dresser", "storage"):
            dx, dz = front_dir(it.rotation)
            side: Side = "x1" if dx > 0 else "x0" if dx < 0 else "z1" if dz > 0 else "z0"
            ratio = _band_free(g, others, _band_rect(r, side, STORAGE_FRONT))
            ok = ratio + EPS >= ACCESS_FREE_RATIO
            storage_reach.append(ok)
            if f.kind in ("wardrobe", "dresser") and not ok:
                violations.append(Violation(rule="access_edge", severity="warning", items=[it.id], message=f"{_name(fur, it)} needs {js_round(STORAGE_FRONT * 100)} cm clear in front"))

    # 7. Requested clear zones must be free.
    for z in zones or []:
        zr = Rect(z.x, z.z, z.x + z.w, z.z + z.d)
        blockers = sorted(it.id for it in solids if rects_overlap(zr, rects[it.id]))
        if blockers:
            names = ", ".join(_name(fur, next(i for i in items if i.id == bid)) for bid in blockers)
            violations.append(Violation(rule="clear_zone", severity="warning", items=blockers, message=f"{z.label} zone is blocked by {names}"))

    # 8. Walkable path from the door to every bed and desk.
    passable = bytearray(1 if g.room[k] and not occupied[k] else 0 for k in range(n_cells))
    seeds = door_seeds if door_seeds else [k for k in range(n_cells) if passable[k]][:1]
    reach = flood_fill(g, passable, seeds)
    eroded = erode(g, passable, CORRIDOR_CELLS)
    wide = flood_fill(g, eroded, [k for k in seeds if eroded[k]])
    walk: Walkability = "Good"
    for it in solids:
        f = fur[it.furnitureId]
        if f.kind not in ("bed", "desk"):
            continue
        nb = rect_neighbours(g, rects[it.id])
        if not any(reach[k] for k in nb):
            violations.append(Violation(rule="walkable_path", severity="warning", items=[it.id], message=f"Path blocked to {_name(fur, it).lower()}"))
            walk = "Blocked"
        elif walk == "Good" and not any(wide[k] or _nb_near_wide(g, wide, k) for k in nb):
            walk = "Tight"

    # Metrics
    room_cells = free_cells = 0
    for k in range(n_cells):
        if g.room[k]:
            room_cells += 1
            if not occupied[k]:
                free_cells += 1
    occ_or_outside = bytearray(1 if (not g.room[k] or occupied[k]) else 0 for k in range(n_cells))
    lfr = largest_free_rect(g, occ_or_outside)
    conflicts = sum(1 for v in violations if v.severity == "error")
    metrics = LayoutMetrics(
        openFloor=_round1(free_cells / room_cells * 100) if room_cells else 0,
        conflicts=conflicts,
        walkability=walk,
        reachableStorage=_round1(sum(storage_reach) / len(storage_reach) * 100) if storage_reach else 100,
        largestFreeRect=FreeRect(
            x=_round2(lfr.x0),
            z=_round2(lfr.z0),
            w=_round2(lfr.x1 - lfr.x0),
            d=_round2(lfr.z1 - lfr.z0),
            areaM2=_round2((lfr.x1 - lfr.x0) * (lfr.z1 - lfr.z0)),
            fits=fits_label(lfr.x1 - lfr.x0, lfr.z1 - lfr.z0),
        )
        if lfr
        else None,
    )
    return ValidationResult(violations=violations, metrics=metrics, blocked=any(v.rule in BLOCKING for v in violations))
