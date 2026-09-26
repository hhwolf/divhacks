"""Placement solver: turns zone-level plan actions into grid coordinates that pass the fit validator."""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.models import AgentPlan, FurnitureItem, LayoutItem, RoomSkeleton, Rotation, ValidationResult, Violation, Zone
from app.solver.constants import EPS, GRID, WINDOW_BAND
from app.solver.grid import Grid, any_mask_in_rect, fill_rect, footprint, front_dir, item_rect, make_grid, rects_overlap
from app.solver.skeleton import Rect, opening_span, wall_dir, wall_inward_normal, wall_length, window_band
from app.solver.validate import door_keep_clear, validate_layout
from app.solver.zones import ZoneSpec, parse_zone, wall_label

Catalog = Mapping[str, FurnitureItem]
NEW_WARNING_PENALTY = 10.0
IN_FRONT_OF_WINDOW_PENALTY = 1.0
_REF_SUFFIX = re.compile(r"[_\-\s]?(?:mkt|\d+)$")


@dataclass
class Candidate:
    x: float
    z: float
    rotation: Rotation
    wall: int
    score: float
    result: ValidationResult


@dataclass
class SolveResult:
    ok: bool
    items: list[LayoutItem]
    zones: list[Zone] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    validation: ValidationResult | None = None
    gap_m: float | None = None
    shortfall_m: float | None = None
    failed_wall: int | None = None
    notes: list[str] = field(default_factory=list)


def _ref_base(ref: str) -> str:
    return _REF_SUFFIX.sub("", ref.strip().lower())


def resolve_instance(ref: str, items: list[LayoutItem], catalog: Catalog) -> LayoutItem | None:
    """instance id -> furnitureId match -> kind match -> name substring -> furnitureId prefix."""
    base = _ref_base(ref)
    for pred in (
        lambda it: it.id == ref,
        lambda it: it.furnitureId == ref,
        lambda it: it.furnitureId == base,
        lambda it: it.furnitureId in catalog and catalog[it.furnitureId].kind == base,
        lambda it: it.furnitureId in catalog and base in catalog[it.furnitureId].name.lower(),
        lambda it: it.furnitureId.startswith(base),
    ):
        hit = next((it for it in items if pred(it)), None)
        if hit:
            return hit
    return None


def resolve_catalog(ref: str, catalog: Catalog, furniture_id: str | None) -> FurnitureItem | None:
    """For `add`: the imported item passed with the request wins unless the plan names a different exact catalog id."""
    base = _ref_base(ref)
    imported = catalog.get(furniture_id) if furniture_id else None
    if imported and (ref == imported.id or base in (imported.kind, imported.category) or base in imported.name.lower() or ref not in catalog):
        return imported
    if ref in catalog:
        return catalog[ref]
    if base in catalog:
        return catalog[base]
    for pred in (lambda f: f.kind == base, lambda f: base in f.name.lower(), lambda f: f.id.startswith(base)):
        hit = next((f for f in catalog.values() if pred(f)), None)
        if hit:
            return hit
    return None


def next_instance_id(furniture_id: str, items: list[LayoutItem]) -> str:
    n = len(items) + 1
    taken = {it.id for it in items}
    while f"{furniture_id}_{n}" in taken:
        n += 1
    return f"{furniture_id}_{n}"


def _rotation_facing(n: tuple[float, float]) -> Rotation | None:
    target = (round(n[0]), round(n[1]))
    if abs(n[0] - target[0]) > 1e-6 or abs(n[1] - target[1]) > 1e-6:
        return None
    for rot in (0, 90, 180, 270):
        if front_dir(rot) == target:
            return rot  # type: ignore[return-value]
    return None


def _snap(v: float) -> float:
    return round(v, 4)


def wall_positions(sk: RoomSkeleton, wall: int, item: FurnitureItem, corners_only: bool) -> list[tuple[float, float, Rotation, float]]:
    """(x, z, rotation, t_center) for the item flush against `wall`, back to the wall, edge on the 10 cm grid."""
    w = sk.walls[wall]
    n = wall_inward_normal(sk, wall)
    rot = _rotation_facing(n)
    if rot is None:
        return []
    dx, dz = wall_dir(w)
    fx, fz = footprint(item.dims, rot)
    along = abs(dx) * fx + abs(dz) * fz
    depth = abs(n[0]) * fx + abs(n[1]) * fz
    length = wall_length(w)
    if along > length + EPS:
        return []
    steps = int(math.floor((length - along) / GRID + EPS))
    t0s = [0.0, length - along] if corners_only else [k * GRID for k in range(steps + 1)]
    out = []
    for t0 in t0s:
        tc = t0 + along / 2
        out.append((_snap(w.x1 + dx * tc + n[0] * depth / 2), _snap(w.z1 + dz * tc + n[1] * depth / 2), rot, tc))
    return out


def _rect_distance(a: Rect, b: Rect) -> float:
    ddx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    ddz = max(0.0, max(a.z0, b.z0) - min(a.z1, b.z1))
    return math.hypot(ddx, ddz)


def _feature_rects(sk: RoomSkeleton, feature: str) -> list[Rect]:
    rects: list[Rect] = []
    if feature == "outlet":
        for o in sk.outlets:
            w = sk.walls[o.wall]
            dx, dz = wall_dir(w)
            px, pz = w.x1 + dx * o.offset, w.z1 + dz * o.offset
            rects.append(Rect(px, pz, px, pz))
        return rects
    for o in sk.windows if feature == "window" else sk.doors:
        a, b = opening_span(sk, o)
        rects.append(Rect(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
    return rects


def _closeness(sk: RoomSkeleton, spec: ZoneSpec, rect: Rect, wall: int, t_center: float) -> float:
    score = 0.0
    if spec.feature:
        targets = _feature_rects(sk, spec.feature)
        if targets:
            score += min(_rect_distance(rect, t) for t in targets)
        if spec.feature == "window":
            if any(rects_overlap(window_band(sk, w, WINDOW_BAND), rect) for w in sk.windows):
                score += IN_FRONT_OF_WINDOW_PENALTY
    if spec.centered:
        score += abs(t_center - wall_length(sk.walls[wall]) / 2)
    return score


def _warning_keys(res: ValidationResult) -> set[tuple[str, tuple[str, ...]]]:
    return {(v.rule, tuple(v.items)) for v in res.violations if v.severity == "warning"}


class Solver:
    def __init__(self, sk: RoomSkeleton, catalog: Catalog, base_items: list[LayoutItem], furniture_id: str | None = None) -> None:
        self.sk = sk
        self.catalog = catalog
        self.base_items = base_items
        self.furniture_id = furniture_id
        self.grid: Grid = make_grid(sk)
        self.keep_clear, _ = door_keep_clear(self.grid, sk)

    def _validate(self, items: list[LayoutItem], zones: list[Zone] | None = None) -> ValidationResult:
        return validate_layout(self.sk, self.catalog, items, zones or [], self.base_items)

    def solve(self, plan: AgentPlan) -> SolveResult:
        items = copy.deepcopy(self.base_items)
        base_warnings = _warning_keys(self._validate(items))
        placed: tuple[LayoutItem, int] | None = None
        for action in plan.actions:
            if action.type == "add":
                fur = resolve_catalog(action.item, self.catalog, self.furniture_id)
                if fur is None:
                    return SolveResult(False, items, violations=[Violation(rule="bounds", severity="error", items=[action.item], message=f"Unknown furniture '{action.item}'")])
                target = LayoutItem(id=next_instance_id(fur.id, items), furnitureId=fur.id, x=0, z=0, rotation=0, locked=False)
                working = items
            else:
                found = resolve_instance(action.item, items, self.catalog)
                if found is None:
                    return SolveResult(False, items, violations=[Violation(rule="bounds", severity="error", items=[action.item], message=f"No '{action.item}' in the room")])
                if found.locked:
                    name = self.catalog[found.furnitureId].name if found.furnitureId in self.catalog else found.id
                    return SolveResult(False, items, violations=[Violation(rule="locked", severity="error", items=[found.id], message=f"{name} is locked and was moved")])
                target = found
                working = [it for it in items if it.id != found.id]
            if action.type == "remove":
                items = working
                continue
            if action.type == "rotate":
                rot = action.rotation if action.rotation is not None else target.rotation + 90
                rotated = target.model_copy(update={"rotation": ((round(rot / 90) % 4) + 4) % 4 * 90})
                res = self._validate([*working, rotated])
                if res.metrics.conflicts:
                    return SolveResult(False, items, violations=[v for v in res.violations if v.severity == "error"], validation=res)
                items = [*working, rotated]
                continue
            feature = next((c.feature for c in plan.constraints if c.type == "adjacent" and c.feature and c.item and _ref_base(c.item) in (_ref_base(target.id), target.furnitureId, _ref_base(action.item))), None)
            best, failing = self._place(target, working, parse_zone(self.sk, action.zone), base_warnings, feature)
            if best is None:
                return self._rejection(target, working, failing, parse_zone(self.sk, action.zone))
            moved = target.model_copy(update={"x": best.x, "z": best.z, "rotation": best.rotation})
            items = [*working, moved]
            placed = (moved, best.wall)

        zones, notes = self._clear_zones(plan, items)
        result = self._validate(items, zones)
        if result.metrics.conflicts:
            return SolveResult(False, items, zones, [v for v in result.violations if v.severity == "error"], result)
        gap = self._wall_gap(*placed, items) if placed else None
        return SolveResult(True, items, zones, [], result, gap_m=gap, notes=notes)

    def _place(
        self, target: LayoutItem, others: list[LayoutItem], specs: list[ZoneSpec], base_warnings: set[tuple[str, tuple[str, ...]]], feature: str | None
    ) -> tuple[Candidate | None, Candidate | None]:
        fur = self.catalog[target.furnitureId]
        best: Candidate | None = None
        failing: Candidate | None = None
        for spec in specs:
            if feature and spec.feature is None:
                spec = ZoneSpec(spec.wall, feature, spec.centered, spec.corner, spec.label)  # type: ignore[arg-type]
            walls = [spec.wall] if spec.wall is not None else list(range(len(self.sk.walls)))
            for wall in walls:
                for x, z, rot, tc in wall_positions(self.sk, wall, fur, spec.corner):
                    cand_item = target.model_copy(update={"x": x, "z": z, "rotation": rot})
                    res = self._validate([*others, cand_item])
                    rect = item_rect(x, z, rot, fur.dims)
                    score = _closeness(self.sk, spec, rect, wall, tc) + NEW_WARNING_PENALTY * len(_warning_keys(res) - base_warnings)
                    cand = Candidate(x, z, rot, wall, score, res)
                    if res.metrics.conflicts == 0:
                        if best is None or cand.score < best.score:
                            best = cand
                    elif failing is None or (res.metrics.conflicts, cand.score) < (failing.result.metrics.conflicts, failing.score):
                        failing = cand
            if best is not None:
                return best, failing
        return best, failing

    def _rejection(self, target: LayoutItem, others: list[LayoutItem], failing: Candidate | None, specs: list[ZoneSpec]) -> SolveResult:
        violations = [v for v in failing.result.violations if v.severity == "error"] if failing else []
        fur = self.catalog[target.furnitureId]
        wall = specs[0].wall if specs and specs[0].wall is not None else (failing.wall if failing else None)
        shortfall = self._shortfall(fur, others, wall) if wall is not None else None
        if not violations:
            violations = [Violation(rule="bounds", severity="error", items=[target.id], message=f"{fur.name} does not fit on the {wall_label(self.sk, wall) if wall is not None else 'requested wall'}")]
        return SolveResult(False, others, violations=violations, validation=failing.result if failing else None, shortfall_m=shortfall, failed_wall=wall)

    def _blocked_mask(self, items: list[LayoutItem]) -> bytearray:
        g = self.grid
        mask = bytearray(1 if (not g.room[k] or self.keep_clear[k]) else 0 for k in range(g.nx * g.nz))
        for it in items:
            f = self.catalog.get(it.furnitureId)
            if f and f.kind != "floor":
                fill_rect(g, mask, item_rect(it.x, it.z, it.rotation, f.dims))
        return mask

    def _wall_strips(self, wall: int, depth: float) -> list[Rect]:
        w = self.sk.walls[wall]
        dx, dz = wall_dir(w)
        n = wall_inward_normal(self.sk, wall)
        cells = int(round(wall_length(w) / GRID))
        strips = []
        for k in range(cells):
            xs = [w.x1 + dx * k * GRID, w.x1 + dx * (k + 1) * GRID]
            zs = [w.z1 + dz * k * GRID, w.z1 + dz * (k + 1) * GRID]
            strips.append(Rect(min(xs + [x + n[0] * depth for x in xs]), min(zs + [z + n[1] * depth for z in zs]), max(xs + [x + n[0] * depth for x in xs]), max(zs + [z + n[1] * depth for z in zs])))
        return strips

    def _shortfall(self, fur: FurnitureItem, others: list[LayoutItem], wall: int) -> float | None:
        """How much wider the item is than the longest free run along `wall` (None when it would fit lengthwise)."""
        n = wall_inward_normal(self.sk, wall)
        rot = _rotation_facing(n)
        if rot is None:
            return None
        fx, fz = footprint(fur.dims, rot)
        along = abs(n[1]) * fx + abs(n[0]) * fz
        depth = abs(n[0]) * fx + abs(n[1]) * fz
        blocked = self._blocked_mask(others)
        run = best = 0
        for strip in self._wall_strips(wall, depth):
            run = 0 if any_mask_in_rect(self.grid, blocked, strip) else run + 1
            best = max(best, run)
        shortfall = along - best * GRID
        return round(shortfall, 3) if shortfall > EPS else None

    def _wall_gap(self, placed: LayoutItem, wall: int, items: list[LayoutItem]) -> float:
        """Free distance along the wall from the placed item to the nearest solid item sharing its band, or the wall end."""
        w = self.sk.walls[wall]
        dx, dz = wall_dir(w)
        length = wall_length(w)

        def span(r: Rect) -> tuple[float, float]:
            ts = [(cx - w.x1) * dx + (cz - w.z1) * dz for cx in (r.x0, r.x1) for cz in (r.z0, r.z1)]
            return min(ts), max(ts)

        mine = item_rect(placed.x, placed.z, placed.rotation, self.catalog[placed.furnitureId].dims)
        t0, t1 = span(mine)
        gap = min(t0, length - t1)
        for it in items:
            f = self.catalog.get(it.furnitureId)
            if it.id == placed.id or f is None or f.kind == "floor":
                continue
            r = item_rect(it.x, it.z, it.rotation, f.dims)
            wall_along_x = abs(dx) > 0.5
            shares_band = (r.z0 < mine.z1 - EPS and r.z1 > mine.z0 + EPS) if wall_along_x else (r.x0 < mine.x1 - EPS and r.x1 > mine.x0 + EPS)
            if not shares_band:
                continue
            o0, o1 = span(r)
            if o0 >= t1 - EPS:
                gap = min(gap, o0 - t1)
            elif o1 <= t0 + EPS:
                gap = min(gap, t0 - o1)
        return max(0.0, round(gap, 3))

    def _clear_zones(self, plan: AgentPlan, items: list[LayoutItem]) -> tuple[list[Zone], list[str]]:
        """Each clear_zone constraint becomes a zone at the largest free rectangle; if the request doesn't fit, the largest found is reported."""
        zones: list[Zone] = []
        notes: list[str] = []
        for c in plan.constraints:
            if c.type != "clear_zone" or not c.w_m or not c.d_m:
                continue
            lfr = self._validate(items).metrics.largestFreeRect
            if lfr is None:
                continue
            label = c.label or "Clear zone"
            if lfr.w + EPS >= c.w_m and lfr.d + EPS >= c.d_m:
                zones.append(Zone(label=label, x=lfr.x, z=lfr.z, w=c.w_m, d=c.d_m))
            elif lfr.w + EPS >= c.d_m and lfr.d + EPS >= c.w_m:
                zones.append(Zone(label=label, x=lfr.x, z=lfr.z, w=c.d_m, d=c.w_m))
            else:
                zones.append(Zone(label=label, x=lfr.x, z=lfr.z, w=lfr.w, d=lfr.d))
                notes.append(f"the largest clear stretch is {lfr.w:.1f} x {lfr.d:.1f} m, short of {c.w_m:.1f} x {c.d_m:.1f}")
        return zones, notes
