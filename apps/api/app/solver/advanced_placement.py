"""Stage 2 placement solver: turns a Stage 1 plan (intent + constraints, never coordinates) into a layout that passes validation.

Locked items never move: layout locks, the plan's `lock` constraints and Backboard non-negotiables all count, even when Gemini
forgot one. Candidates for the new or moved item: flush against each wall (back to the wall; beds also side-on) and on the open
floor, on the 10 cm grid, rotations 0/90/180/270. They are pre-filtered on an occupancy grid (room cells, solid items, door swing +
clearance), filtered by `adjacent` / `keep_clear`, ranked cheaply, and only the best few get the full validator. Winner order: hard
rules pass (no new conflict) > constraints satisfied > fewer new soft warnings > fewer items moved > closeness.
"""

from __future__ import annotations

import copy
import math
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from app.models import FurnitureItem, LayoutItem, RoomSkeleton, Rotation, ValidationResult, Violation, Zone
from app.planning_models import PlacementPlan as GeminiPlan, Placement
from app.solver.constants import ACCESS_EDGE, ACCESS_FREE_RATIO, EPS, GRID, WINDOW_BAND
from app.solver.grid import Grid, any_mask_in_rect, count_mask_in_rect, fill_rect, footprint, front_dir, item_rect, largest_free_rect, make_grid, rects_overlap
from app.solver.skeleton import Rect, door_clearance_rect, opening_span, room_bounds, wall_dir, wall_inward_normal, wall_length, window_band
from app.solver.validate import door_keep_clear, validate_layout
from app.solver.zones import wall_label

DEFAULT_YOGA_ZONE = (1.8, 1.2)
STORAGE_FRONT = ACCESS_EDGE  # retain the existing validator clearance; not a new rule
Catalog = Mapping[str, FurnitureItem]
ADJACENT_M = 0.3  # an item is "beside" a window/door/outlet when its footprint is within this distance of it
TOP_K = 40  # candidates that get the full validator
OPEN_FLOOR_PENALTY = 0.5  # furniture prefers walls; rugs and mats don't care
IN_FRONT_OF_WINDOW_PENALTY = 1.0  # "beside the window" means next to it, not in front of it
DISPLACEMENT_WEIGHT = 0.1  # moved items prefer to stay close to where they were
OPEN_RECT_WEIGHT = 0.3  # per m² the placement takes out of the room's largest open rectangle ("keep one open rectangle")
BACK_TO_DOOR_PENALTY = 0.3  # a desk whose chair would sit with its back to the door
MAX_OPTIONS = 3
DISTINCT_M = 1.0  # two options must be this far apart to count as different ideas...
TURNED_DISTINCT_M = 0.25  # ...or turned 90 degrees and at least this far apart
_REF_SUFFIX = re.compile(r"[_\-\s]?(?:mkt|\d+)$")
FRONT_ROOM = {"desk": ACCESS_EDGE, "dresser": STORAGE_FRONT, "wardrobe": STORAGE_FRONT, "storage": STORAGE_FRONT}  # chair / drawer room
_WORDS = {"shelf": "storage", "bookshelf": "storage", "bookcase": "storage", "chair": "seating", "sofa": "seating", "couch": "seating", "yoga_mat": "floor", "yoga mat": "floor", "mat": "floor", "rug": "floor"}


@dataclass
class Cand:
    x: float
    z: float
    rotation: Rotation
    wall: int | None
    unsatisfied: int
    cheap: float


@dataclass
class SolveResult:
    ok: bool
    items: list[LayoutItem]
    zones: list[Zone] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    validation: ValidationResult | None = None
    placement: Placement | None = None
    moves: list[Placement] = field(default_factory=list)
    new_furniture: FurnitureItem | None = None  # created from the plan's item dims; the pipeline stores it
    gap_m: float | None = None
    nearest_miss: str | None = None
    notes: list[str] = field(default_factory=list)
    noop: bool = False  # nothing needed to change (e.g. nothing was blocking the window): no variant is created
    wall: int | None = None  # wall the placed item stands against (None: open floor)
    relaxed: list[str] = field(default_factory=list)  # constraints this option gives up, e.g. ["adjacent window"]


# ---- resolving plain-language item references ------------------------------------------------------------------------------


def _ref_base(ref: str) -> str:
    return _REF_SUFFIX.sub("", ref.strip().lower().removeprefix("my ").removeprefix("the "))


def matching_instances(ref: str, items: list[LayoutItem], catalog: Catalog) -> list[LayoutItem]:
    """instance id -> furnitureId -> kind -> name substring -> furnitureId prefix; all matches of the first rule that matches."""
    base = _ref_base(ref)
    kind = _WORDS.get(base, base)
    for pred in (
        lambda it: it.id == ref,
        lambda it: it.furnitureId in (ref, base),
        lambda it: it.furnitureId in catalog and catalog[it.furnitureId].kind == kind,
        lambda it: it.furnitureId in catalog and base in catalog[it.furnitureId].name.lower(),
        lambda it: it.furnitureId.startswith(base),
    ):
        hits = [it for it in items if pred(it)]
        if hits:
            return hits
    return []


def resolve_catalog(ref: str, catalog: Catalog) -> FurnitureItem | None:
    base = _ref_base(ref)
    kind = _WORDS.get(base, base)
    if ref in catalog:
        return catalog[ref]
    presets = [f for f in catalog.values() if f.source == "preset"]
    for pred in (lambda f: f.id == base, lambda f: f.kind == kind, lambda f: base in f.name.lower(), lambda f: f.id.startswith(base)):
        hit = next((f for f in presets if pred(f)), None)
        if hit:
            return hit
    return None


def next_instance_id(furniture_id: str, items: list[LayoutItem]) -> str:
    n = len(items) + 1
    taken = {it.id for it in items}
    while f"{furniture_id}_{n}" in taken:
        n += 1
    return f"{furniture_id}_{n}"


# ---- geometry helpers --------------------------------------------------------------------------------------------------------


def _rotation_facing(n: tuple[float, float]) -> Rotation | None:
    target = (round(n[0]), round(n[1]))
    if abs(n[0] - target[0]) > 1e-6 or abs(n[1] - target[1]) > 1e-6:
        return None
    for rot in (0, 90, 180, 270):
        if front_dir(rot) == target:
            return rot  # type: ignore[return-value]
    return None


def _rect_distance(a: Rect, b: Rect) -> float:
    ddx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    ddz = max(0.0, max(a.z0, b.z0) - min(a.z1, b.z1))
    return math.hypot(ddx, ddz)


def _fits(w: float, d: float, want_w: float, want_d: float) -> bool:
    return (w + EPS >= want_w and d + EPS >= want_d) or (w + EPS >= want_d and d + EPS >= want_w)


def _err_keys(res: ValidationResult, severity: str) -> set[tuple[str, tuple[str, ...]]]:
    return {(v.rule, tuple(sorted(v.items))) for v in res.violations if v.severity == severity}


def _summed(g: Grid, mask: bytearray) -> list[int]:
    """Summed-area table ((nx+1) x (nz+1)) of a mask, for O(1) "is anything in this cell window?" queries."""
    w = g.nx + 1
    sat = [0] * (w * (g.nz + 1))
    for j in range(g.nz):
        row = 0
        for i in range(g.nx):
            row += mask[j * g.nx + i]
            sat[(j + 1) * w + i + 1] = sat[j * w + i + 1] + row
    return sat


def _window_sum(sat: list[int], nx: int, i: int, j: int, ci: int, cj: int) -> int:
    w = nx + 1
    return sat[(j + cj) * w + i + ci] - sat[j * w + i + ci] - sat[(j + cj) * w + i] + sat[j * w + i]


def _replace(items: list[LayoutItem], moved: LayoutItem) -> list[LayoutItem]:
    """Keep item order stable: a moved item stays where it was in the list; a new one is appended."""
    out = [moved if it.id == moved.id else it for it in items]
    return out if any(it.id == moved.id for it in items) else [*out, moved]


class Solver:
    def __init__(self, sk: RoomSkeleton, catalog: Catalog, base_items: list[LayoutItem], furniture_id: str | None = None, extra_locks: Iterable[str] = ()) -> None:
        self.sk = sk
        self.catalog: dict[str, FurnitureItem] = dict(catalog)
        self.base_items = base_items
        self.furniture_id = furniture_id
        self.extra_locks = list(extra_locks)
        self.grid: Grid = make_grid(sk)
        self.keep_clear, _ = door_keep_clear(self.grid, sk)
        self.bounds = room_bounds(sk)
        base = self._validate(base_items)
        self.base_errors, self.base_warnings = _err_keys(base, "error"), _err_keys(base, "warning")

    # -- validation / masks ----------------------------------------------------------------------------------------------------
    def _validate(self, items: list[LayoutItem], zones: list[Zone] | None = None) -> ValidationResult:
        return validate_layout(self.sk, self.catalog, items, zones or [], self.base_items)

    def _solid(self, it: LayoutItem) -> bool:
        f = self.catalog.get(it.furnitureId)
        return f is not None and f.kind != "floor"

    def _occupied(self, items: list[LayoutItem], with_door: bool) -> bytearray:
        g = self.grid
        mask = bytearray(1 if (not g.room[k] or (with_door and self.keep_clear[k])) else 0 for k in range(g.nx * g.nz))
        for it in items:
            if self._solid(it):
                fill_rect(g, mask, item_rect(it.x, it.z, it.rotation, self.catalog[it.furnitureId].dims))
        return mask

    def _lfr(self, items: list[LayoutItem], with_door: bool = True) -> Rect | None:
        """Largest free rectangle; by default outside the door swing + clearance, so a clear zone never sits where the door opens."""
        return largest_free_rect(self.grid, self._occupied(items, with_door=with_door))

    def _name(self, it: LayoutItem) -> str:
        f = self.catalog.get(it.furnitureId)
        return f.name if f else it.furnitureId

    def _placement(self, it: LayoutItem) -> Placement:
        return Placement(item=it.id, name=self._name(it), furnitureId=it.furnitureId, x=it.x, z=it.z, rotation=it.rotation)

    # -- constraints -----------------------------------------------------------------------------------------------------------
    def locked_ids(self, plan: GeminiPlan) -> set[str]:
        ids = {it.id for it in self.base_items if it.locked}
        for ref in [c.item for c in plan.constraints if c.type == "lock" and c.item] + self.extra_locks:
            ids.update(it.id for it in matching_instances(ref, self.base_items, self.catalog))
        return ids

    def _refers_to(self, ref: str | None, target: LayoutItem, fur: FurnitureItem) -> bool:
        if ref is None:
            return True
        base = _ref_base(ref)
        return ref == target.id or base == target.furnitureId or _WORDS.get(base, base) == fur.kind or base in fur.name.lower() or ref == self.furniture_id

    def _features(self, plan: GeminiPlan, kind: str, target: LayoutItem, fur: FurnitureItem) -> list[str]:
        return [c.feature for c in plan.constraints if c.type == kind and c.feature and self._refers_to(c.item, target, fur)]

    def _feature_rects(self, feature: str) -> list[Rect]:
        if feature == "outlet":
            out = []
            for o in self.sk.outlets:
                w = self.sk.walls[o.wall]
                dx, dz = wall_dir(w)
                px, pz = w.x1 + dx * o.offset, w.z1 + dz * o.offset
                out.append(Rect(px, pz, px, pz))
            return out
        spans = [opening_span(self.sk, o) for o in (self.sk.windows if feature == "window" else self.sk.doors if feature == "door" else [])]
        return [Rect(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])) for a, b in spans]

    def _blocks(self, feature: str, rect: Rect, fur: FurnitureItem, height_aware: bool) -> bool:
        if feature == "window":
            return any(rects_overlap(window_band(self.sk, w, WINDOW_BAND), rect) and (not height_aware or fur.dims.h > w.sillHeight + EPS) for w in self.sk.windows)
        if feature == "door":
            return any_mask_in_rect(self.grid, self.keep_clear, rect)
        return False

    # -- candidates ------------------------------------------------------------------------------------------------------------
    def _wall_spots(self, wall: int, fur: FurnitureItem, rot: Rotation) -> list[tuple[float, float]]:
        w = self.sk.walls[wall]
        dx, dz = wall_dir(w)
        if min(abs(dx), abs(dz)) > 1e-6:
            return []  # diagonal wall: axis-aligned footprints can't sit flush against it
        n = wall_inward_normal(self.sk, wall)
        fx, fz = footprint(fur.dims, rot)
        along = abs(dx) * fx + abs(dz) * fz
        depth = abs(n[0]) * fx + abs(n[1]) * fz
        length = wall_length(w)
        if along > length + EPS:
            return []
        t0s = [k * GRID for k in range(int(math.floor((length - along) / GRID + EPS)) + 1)]
        if length - along - t0s[-1] > EPS:
            t0s.append(length - along)  # flush with the far corner too
        return [(round(w.x1 + dx * (t0 + along / 2) + n[0] * depth / 2, 4), round(w.z1 + dz * (t0 + along / 2) + n[1] * depth / 2, 4)) for t0 in t0s]

    def _candidates(self, fur: FurnitureItem, others: list[LayoutItem], walls_only: bool = False) -> list[tuple[float, float, Rotation, int | None]]:
        floor_item = fur.kind == "floor"
        blocked = self._occupied([] if floor_item else others, with_door=not floor_item)
        out: list[tuple[float, float, Rotation, int | None]] = []
        seen: set[tuple[float, float, int]] = set()

        def add(x: float, z: float, rot: Rotation, wall: int | None) -> None:
            key = (round(x, 3), round(z, 3), rot)
            r = item_rect(x, z, rot, fur.dims)
            if key in seen or r.x0 < self.bounds.x0 - EPS or r.z0 < self.bounds.z0 - EPS or r.x1 > self.bounds.x1 + EPS or r.z1 > self.bounds.z1 + EPS:
                return
            if any_mask_in_rect(self.grid, blocked, r):
                return
            seen.add(key)
            out.append((x, z, rot, wall))

        for wall in range(len(self.sk.walls)):
            facing = _rotation_facing(wall_inward_normal(self.sk, wall))
            if facing is None:
                continue
            rots: list[int] = [facing] + ([(facing + 90) % 360, (facing + 270) % 360] if fur.kind == "bed" else [])
            for rot in rots:
                for x, z in self._wall_spots(wall, fur, rot):  # type: ignore[arg-type]
                    add(x, z, rot, wall)  # type: ignore[arg-type]
        if walls_only:
            return out
        g = self.grid
        for rot in (0, 90, 180, 270):
            fx, fz = footprint(fur.dims, rot)
            for j in range(g.nz):
                for i in range(g.nx):
                    add(round(g.ox + i * GRID + fx / 2, 4), round(g.oz + j * GRID + fz / 2, 4), rot, None)  # type: ignore[arg-type]
        return out

    def _front_room_ok(self, fur: FurnitureItem, rect: Rect, rot: Rotation, occupied: bytearray) -> bool:
        """The side you use (a desk's chair side, drawer fronts) needs its band mostly free. The validator only asks a desk for *a*
        free long edge, so without this a desk could face the wall with 10 cm for the chair."""
        depth = FRONT_ROOM.get(fur.kind)
        if depth is None:
            return True
        fx, fz = front_dir(rot)
        band = Rect(rect.x1, rect.z0, rect.x1 + depth, rect.z1) if fx > 0 else Rect(rect.x0 - depth, rect.z0, rect.x0, rect.z1) if fx < 0 else \
            Rect(rect.x0, rect.z1, rect.x1, rect.z1 + depth) if fz > 0 else Rect(rect.x0, rect.z0 - depth, rect.x1, rect.z0)
        inside, hit = count_mask_in_rect(self.grid, occupied, band, True)
        expected = round((band.x1 - band.x0) / GRID) * round((band.z1 - band.z0) / GRID)  # cells past the wall count as blocked
        return expected > 0 and (inside - hit) / expected + EPS >= ACCESS_FREE_RATIO

    def _score(self, fur: FurnitureItem, x: float, z: float, rot: Rotation, wall: int | None, adjacent: list[str], keep: list[str],
               origin: tuple[float, float] | None, occupied: bytearray | None = None) -> Cand:
        rect = item_rect(x, z, rot, fur.dims)
        unsatisfied, cheap = 0, 0.0
        if occupied is not None and not self._front_room_ok(fur, rect, rot, occupied):
            unsatisfied += 1
        for feature in adjacent:
            if feature == "wall":
                unsatisfied += wall is None
                continue
            targets = self._feature_rects(feature)
            if not targets:
                continue  # the room has no such feature; nothing to satisfy
            d = min(_rect_distance(rect, t) for t in targets)
            unsatisfied += d > ADJACENT_M + EPS
            cheap += d
            if feature == "window" and self._blocks("window", rect, fur, height_aware=False):
                cheap += IN_FRONT_OF_WINDOW_PENALTY
        unsatisfied += sum(self._blocks(f, rect, fur, height_aware=False) for f in keep)
        if wall is None and fur.kind != "floor":
            cheap += OPEN_FLOOR_PENALTY
        if origin is not None:
            cheap += DISPLACEMENT_WEIGHT * math.dist(origin, (x, z))
        return Cand(x, z, rot, wall, unsatisfied, cheap)

    def _touching(self, r: Rect) -> frozenset[int]:
        """Walls whose line one of the footprint's edges lies on (axis-aligned walls only)."""
        out = set()
        for i, w in enumerate(self.sk.walls):
            if abs(w.z1 - w.z2) < EPS and min(abs(r.z0 - w.z1), abs(r.z1 - w.z1)) < 0.011 and r.x0 < max(w.x1, w.x2) and r.x1 > min(w.x1, w.x2):
                out.add(i)
            elif abs(w.x1 - w.x2) < EPS and min(abs(r.x0 - w.x1), abs(r.x1 - w.x1)) < 0.011 and r.z0 < max(w.z1, w.z2) and r.z1 > min(w.z1, w.z2):
                out.add(i)
        return frozenset(out)

    def _design_penalty(self, fur: FurnitureItem, c: Cand, trial: list[LayoutItem], base_lfr_area: float) -> float:
        """Designer tie-breakers from the interior-designer skill: keep one open rectangle; no desk chair with its back to the door."""
        r = self._lfr(trial)
        penalty = OPEN_RECT_WEIGHT * max(0.0, base_lfr_area - ((r.x1 - r.x0) * (r.z1 - r.z0) if r else 0.0))
        if fur.kind == "desk" and self.sk.doors:
            a, b = opening_span(self.sk, self.sk.doors[0])
            fx, fz = front_dir(c.rotation)
            if ((a[0] + b[0]) / 2 - c.x) * fx + ((a[1] + b[1]) / 2 - c.z) * fz > 0:
                penalty += BACK_TO_DOOR_PENALTY
        return penalty

    def _ranked(self, target: LayoutItem, fur: FurnitureItem, items: list[LayoutItem], adjacent: list[str], keep: list[str]) -> tuple[list[tuple[tuple[int, float], Cand]], list[Violation]]:
        """Valid spots for `target` (no new conflict), best first by (new soft warnings, closeness + designer penalties), plus the
        violations of the best failing spot. `target` replaces its instance in `items`, or is appended when new."""
        others = [it for it in items if it.id != target.id]
        origin = (target.x, target.z) if any(it.id == target.id for it in items) else None
        occupied = self._occupied(others, with_door=False)
        cands = [self._score(fur, x, z, rot, wall, adjacent, keep, origin, occupied) for x, z, rot, wall in self._candidates(fur, others)]
        cands = sorted((c for c in cands if c.unsatisfied == 0), key=lambda c: c.cheap)
        base = self._lfr(others)
        base_area = (base.x1 - base.x0) * (base.z1 - base.z0) if base else 0.0
        ranked: list[tuple[tuple[int, float], Cand]] = []
        failing: list[Violation] = []
        for c in cands[:TOP_K]:
            trial = _replace(items, target.model_copy(update={"x": c.x, "z": c.z, "rotation": c.rotation}))
            res = self._validate(trial)
            new_errors = _err_keys(res, "error") - self.base_errors
            if new_errors or res.blocked:
                if not failing:
                    failing = [v for v in res.violations if (v.rule, tuple(sorted(v.items))) in new_errors or v.rule in ("bounds", "overlap")]
                continue
            ranked.append(((len(_err_keys(res, "warning") - self.base_warnings), c.cheap + self._design_penalty(fur, c, trial, base_area)), c))
        ranked.sort(key=lambda kc: kc[0])
        return ranked, failing

    def _place(self, target: LayoutItem, fur: FurnitureItem, items: list[LayoutItem], adjacent: list[str], keep: list[str]) -> tuple[Cand | None, list[Violation]]:
        ranked, failing = self._ranked(target, fur, items, adjacent, keep)
        return (ranked[0][1] if ranked else None), failing

    def _distinct(self, c: Cand, fur: FurnitureItem, chosen: list[Cand]) -> bool:
        """A different idea, not the same one nudged: at least DISTINCT_M from every chosen option; the only exception is the
        recommended spot turned 90 degrees (side-on vs flush is a real choice)."""
        for k, o in enumerate(chosen):
            d = math.dist((c.x, c.z), (o.x, o.z))
            turned_twin = k == 0 and c.rotation % 180 != o.rotation % 180 and d >= TURNED_DISTINCT_M
            if d < DISTINCT_M and not turned_twin:
                return False
        return True

    # -- intents ---------------------------------------------------------------------------------------------------------------
    def solve(self, plan: GeminiPlan) -> SolveResult:
        """The recommended option (or the rejection)."""
        return self.design(plan, 1)[0]

    def design(self, plan: GeminiPlan, max_options: int = MAX_OPTIONS) -> list[SolveResult]:
        """Up to `max_options` validated, genuinely different options, best first; or a single failed result explaining the miss."""
        imported = self.catalog.get(self.furniture_id) if self.furniture_id else None
        if imported and imported.source in ("link", "photo") and not imported.dimensionsConfirmed:
            return [SolveResult(False, list(self.base_items), nearest_miss="confirm imported dimensions before requesting a fit")]
        max_options = min(MAX_OPTIONS, max(1, max_options))
        locked = self.locked_ids(plan)
        if plan.intent == "fit_item":
            return self._fit(plan, locked, max_options)
        if plan.intent == "keep_clear":
            return [self._keep_clear(plan, locked)]
        if plan.intent == "make_space":
            return self._make_space(plan, locked, max_options)
        return [SolveResult(False, list(self.base_items), nearest_miss=f"there is nothing to place for a {plan.intent} request")]

    def _fit_target(self, plan: GeminiPlan, items: list[LayoutItem]) -> tuple[LayoutItem | None, FurnitureItem | None, FurnitureItem | None]:
        """(instance to place, its catalog entry, catalog entry to create). Imported item > move an existing one > new preset/dims."""
        if self.furniture_id and self.furniture_id in self.catalog:
            fur = self.catalog[self.furniture_id]
            return LayoutItem(id=next_instance_id(fur.id, items), furnitureId=fur.id, x=0, z=0, rotation=0, locked=False), fur, None
        word = (plan.item.type if plan.item else None) or next((c.item for c in plan.constraints if c.type in ("adjacent", "keep_clear") and c.item), None)
        if not word:
            return None, None, None
        has_dims = bool(plan.item and plan.item.w_m and plan.item.d_m)
        existing = matching_instances(word, items, self.catalog)
        if existing and not has_dims and plan.operation != "add":
            return existing[0], self.catalog[existing[0].furnitureId], None
        if plan.operation == "move":
            return None, None, None  # never add an item in response to a move
        preset = resolve_catalog(word, self.catalog)
        if has_dims and plan.item is not None:
            fur = FurnitureItem(
                id=f"imp_{uuid.uuid4().hex[:8]}", name=plan.item.name or (preset.name if preset else word.replace("_", " ").title()), category="imported",
                kind=preset.kind if preset else "decor", dims={"w": plan.item.w_m, "d": plan.item.d_m, "h": plan.item.h_m if plan.item.h_m is not None else (preset.dims.h if preset else 0.75)},  # type: ignore[arg-type]
                glbUrl=preset.glbUrl if preset else None, thumbUrl=preset.thumbUrl if preset else None, source="manual", price=plan.item.price_usd,
            )
            self.catalog[fur.id] = fur
            return LayoutItem(id=next_instance_id(fur.id, items), furnitureId=fur.id, x=0, z=0, rotation=0, locked=False), fur, fur
        if preset:
            return LayoutItem(id=next_instance_id(preset.id, items), furnitureId=preset.id, x=0, z=0, rotation=0, locked=False), preset, None
        return None, None, None

    def _locked_rejection(self, it: LayoutItem) -> SolveResult:
        name = self._name(it)
        return SolveResult(False, list(self.base_items), violations=[Violation(rule="locked", severity="error", items=[it.id], message=f"{name} is locked and was moved")],
                           nearest_miss=f"your {name.lower()} is locked, so I won't move it")

    def _fit(self, plan: GeminiPlan, locked: set[str], max_options: int) -> list[SolveResult]:
        items = copy.deepcopy(self.base_items)
        target, fur, new_fur = self._fit_target(plan, items)
        if target is None or fur is None:
            return [SolveResult(False, items, nearest_miss="I couldn't tell which piece of furniture you mean")]
        if fur.source in ("link", "photo") and not fur.dimensionsConfirmed:
            return [SolveResult(False, items, nearest_miss="confirm imported dimensions before requesting a fit")]
        if target.id in locked:
            return [self._locked_rejection(target)]
        adjacent, keep = self._features(plan, "adjacent", target, fur), self._features(plan, "keep_clear", target, fur)
        ranked, failing = self._ranked(target, fur, items, adjacent, keep)
        if not ranked:
            return [self._fit_rejection(target, fur, items, adjacent, failing)]
        picks: list[tuple[Cand, list[str]]] = []
        for _, c in ranked:
            if len(picks) < max_options and self._distinct(c, fur, [p[0] for p in picks]):
                picks.append((c, []))
        soft = [f for f in adjacent if f != "wall" and any(c.type == "adjacent" and c.feature == f and c.optional for c in plan.constraints)]
        if len(picks) < max_options and soft:  # a designer also shows the good spot that isn't where they asked, and says so
            loose, _ = self._ranked(target, fur, items, [f for f in adjacent if f not in soft], keep)
            for (new_warnings, _), c in loose:  # only good alternatives: against a wall, no new warnings
                if c.wall is not None and new_warnings == 0 and len(picks) < max_options and self._distinct(c, fur, [p[0] for p in picks]):
                    picks.append((c, [f"beside the {f}" for f in soft]))
        out = []
        for c, relaxed in picks:
            placed = target.model_copy(update={"x": c.x, "z": c.z, "rotation": c.rotation})
            final = _replace(items, placed)
            zones, notes = self._requested_zones(plan, final)
            walls = self._touching(item_rect(c.x, c.z, c.rotation, fur.dims))
            wall = c.wall if c.wall is not None else (min(walls) if walls else None)
            gap = self._wall_gap(placed, wall, final) if wall is not None else None
            res = self._finish(final, zones, placement=self._placement(placed), new_furniture=new_fur, gap=gap, notes=notes)
            res.wall, res.relaxed = wall, relaxed
            if res.ok:
                out.append(res)
        return out or [self._fit_rejection(target, fur, items, adjacent, failing)]

    def _keep_clear(self, plan: GeminiPlan, locked: set[str]) -> SolveResult:
        items = copy.deepcopy(self.base_items)
        features = [c.feature for c in plan.constraints if c.type == "keep_clear" and c.feature in ("window", "door")] or ["window"]
        named = [c.item for c in plan.constraints if c.type == "keep_clear" and c.item]
        if named:
            targets = [it for ref in named for it in matching_instances(ref, items, self.catalog)]
        else:  # whatever actually blocks: taller than the sill in front of a window, anything in a door swing
            targets = [it for it in items if self._solid(it) and any(self._blocks(f, item_rect(it.x, it.z, it.rotation, self.catalog[it.furnitureId].dims), self.catalog[it.furnitureId], height_aware=True) for f in features)]
        moves: list[Placement] = []
        for t in targets:
            fur = self.catalog[t.furnitureId]
            current = next(it for it in items if it.id == t.id)
            if not any(self._blocks(f, item_rect(current.x, current.z, current.rotation, fur.dims), fur, height_aware=False) for f in features):
                continue
            if t.id in locked:
                return self._locked_rejection(t)
            best, failing = self._place(current, fur, items, [], features)
            if best is None:
                where = " and ".join(features)
                return SolveResult(False, items, violations=failing, nearest_miss=f"there is no spot for the {fur.name.lower()} that keeps the {where} clear")
            moved = current.model_copy(update={"x": best.x, "z": best.z, "rotation": best.rotation})
            items = _replace(items, moved)
            moves.append(self._placement(moved))
        if not moves:
            unchanged = self._finish(items, [])
            unchanged.noop = unchanged.ok
            unchanged.notes = [f"nothing is blocking the {' or '.join(features)}, so the layout already keeps it clear"]
            return unchanged
        zones = [z for z in (self._keep_clear_zone(f, items) for f in features) if z is not None]
        return self._finish(items, zones, moves=moves)

    def _keep_clear_zone(self, feature: str, items: list[LayoutItem]) -> Zone | None:
        opening = self.sk.windows[0] if feature == "window" and self.sk.windows else self.sk.doors[0] if feature == "door" and self.sk.doors else None
        if opening is None:
            return None
        r = window_band(self.sk, opening, WINDOW_BAND) if feature == "window" else door_clearance_rect(self.sk, opening, 0.9)  # type: ignore[arg-type]
        if any(self._solid(it) and rects_overlap(r, item_rect(it.x, it.z, it.rotation, self.catalog[it.furnitureId].dims)) for it in items):
            return None  # e.g. a low locked bed under the window: don't draw a keep-clear zone that is already occupied
        return Zone(label=feature.title(), type="keep_clear", x=round(r.x0, 2), z=round(r.z0, 2), w=round(r.x1 - r.x0, 2), d=round(r.z1 - r.z0, 2))

    def _make_space(self, plan: GeminiPlan, locked: set[str], max_options: int) -> list[SolveResult]:
        """Slide the requested zone over the grid (both orientations; outside walls, the door swing and fixed items) and clear it with
        the fewest moves of unlocked items (0, 1 or 2), each to a free wall spot outside the zone, least displacement first. Options
        are different spots or different moves; zones hugging a wall or corner win ties (one open rectangle, the middle stays free)."""
        items = copy.deepcopy(self.base_items)
        c = next((c for c in plan.constraints if c.type == "clear_zone"), None)
        want_w, want_d = (c.w_m, c.d_m) if c and c.w_m and c.d_m else DEFAULT_YOGA_ZONE
        label = (c.label if c and c.label else None) or "Clear zone"
        movable = [it for it in items if it.id not in locked and self._solid(it)]
        movable_ids = {it.id for it in movable}
        g = self.grid
        sat = _summed(g, self._occupied([it for it in items if it.id not in movable_ids], with_door=True))  # outside | door | fixed items
        rects = {it.id: item_rect(it.x, it.z, it.rotation, self.catalog[it.furnitureId].dims) for it in movable}
        spots: dict[str, list[tuple[float, LayoutItem, Rect]]] = {}
        for it in movable:
            fur = self.catalog[it.furnitureId]
            others = [o for o in items if o.id != it.id]
            spots[it.id] = sorted((
                (math.dist((x, z), (it.x, it.z)), it.model_copy(update={"x": x, "z": z, "rotation": rot}), item_rect(x, z, rot, fur.dims))
                for x, z, rot, _ in self._candidates(fur, others, walls_only=True) if (x, z, rot) != (it.x, it.z, it.rotation)
            ), key=lambda s: s[0])
        found: list[tuple[int, float, Rect, list[tuple[LayoutItem, LayoutItem]]]] = []
        for zw, zd in {(want_w, want_d), (want_d, want_w)}:
            ci, cj = math.ceil(zw / GRID - EPS), math.ceil(zd / GRID - EPS)
            for j in range(g.nz - cj + 1):
                for i in range(g.nx - ci + 1):
                    if _window_sum(sat, g.nx, i, j, ci, cj):
                        continue
                    zr = Rect(g.ox + i * GRID, g.oz + j * GRID, g.ox + i * GRID + zw, g.oz + j * GRID + zd)
                    blockers = [it for it in movable if rects_overlap(rects[it.id], zr)]
                    hug = -0.01 * len(self._touching(zr))
                    if not blockers:
                        found.append((0, hug, zr, []))
                    elif len(blockers) <= 2 and (moved := self._relocate(blockers, zr, spots)):
                        found.append((len(blockers), moved[0] + hug, zr, moved[1]))
        found.sort(key=lambda o: (o[0], o[1]))
        out: list[SolveResult] = []
        chosen: list[tuple[Rect, frozenset[str]]] = []
        per_moves: dict[int, int] = {}
        attempts = 0
        for n_moves, _, zr, moves in found:
            if len(out) >= max_options:
                break
            ids = frozenset(a.id for a, _ in moves)
            center = ((zr.x0 + zr.x1) / 2, (zr.z0 + zr.z1) / 2)
            if any(math.dist(center, ((r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2)) < DISTINCT_M for r, _ in chosen):
                continue  # the same spot again (with or without moves) is not a different option
            if per_moves.get(n_moves, 0) >= 2 and len(found) > 1 and any(o[0] != n_moves for o in found):
                continue  # keep the options varied: not three "move nothing" spots when moving one piece gives a better one
            trial = items
            for _, after in moves:
                trial = _replace(trial, after)
            zone = Zone(label=label, type="clear", x=round(zr.x0, 2), z=round(zr.z0, 2), w=round(zr.x1 - zr.x0, 2), d=round(zr.z1 - zr.z0, 2))
            done = self._finish(trial, [zone], moves=[self._placement(after) for _, after in moves])
            if done.ok:
                out.append(done)
                chosen.append((zr, ids))
                per_moves[n_moves] = per_moves.get(n_moves, 0) + 1
            attempts += 1
            if attempts >= 60:  # each attempt runs the full validator; the good spots are at the front of the list
                break
        if out:
            return out
        lfr = self._lfr(items)
        size = f"{lfr.x1 - lfr.x0:.1f} x {lfr.z1 - lfr.z0:.1f} m" if lfr else "nothing"
        return [SolveResult(False, items, nearest_miss=f"largest free zone found: {size} (asked for {want_w:.1f} x {want_d:.1f} m)")]

    @staticmethod
    def _relocate(blockers: list[LayoutItem], zr: Rect, spots: dict) -> tuple[float, list[tuple[LayoutItem, LayoutItem]]] | None:  # type: ignore[type-arg]
        """Cheapest wall spots outside the zone for one or two blockers (spots were computed with everything else in place)."""
        free = [[s for s in spots[b.id] if not rects_overlap(s[2], zr)][:8] for b in blockers]
        if len(blockers) == 1:
            return (free[0][0][0], [(blockers[0], free[0][0][1])]) if free[0] else None
        best = None
        for da, a, ra in free[0]:
            for db, b, rb in free[1]:
                if not rects_overlap(ra, rb) and (best is None or da + db < best[0]):
                    best = (da + db, [(blockers[0], a), (blockers[1], b)])
        return best

    def _zone_at(self, r: Rect, want_w: float, want_d: float, label: str) -> Zone:
        w, d = (want_w, want_d) if (r.x1 - r.x0 + EPS >= want_w and r.z1 - r.z0 + EPS >= want_d) else (want_d, want_w)
        return Zone(label=label, type="clear", x=round(r.x0, 2), z=round(r.z0, 2), w=w, d=d)

    def _requested_zones(self, plan: GeminiPlan, items: list[LayoutItem]) -> tuple[list[Zone], list[str]]:
        """Optional clear zones on a fit_item plan: placed at the largest free rectangle, reported when the request doesn't fit."""
        zones, notes = [], []
        for c in plan.constraints:
            if c.type != "clear_zone":
                continue
            want_w, want_d = (c.w_m, c.d_m) if c.w_m and c.d_m else DEFAULT_YOGA_ZONE
            r = self._lfr(items)
            if r and _fits(r.x1 - r.x0, r.z1 - r.z0, want_w, want_d):
                zones.append(self._zone_at(r, want_w, want_d, c.label or "Clear zone"))
            else:
                notes.append(f"the largest clear stretch left is {(r.x1 - r.x0) if r else 0:.1f} x {(r.z1 - r.z0) if r else 0:.1f} m")
        return zones, notes

    def _finish(self, items: list[LayoutItem], zones: list[Zone], *, placement: Placement | None = None, moves: list[Placement] | None = None,
                new_furniture: FurnitureItem | None = None, gap: float | None = None, notes: list[str] | None = None) -> SolveResult:
        res = self._validate(items, zones)
        new_errors = _err_keys(res, "error") - self.base_errors
        if new_errors or res.blocked:
            bad = [v for v in res.violations if (v.rule, tuple(sorted(v.items))) in new_errors or v.rule in ("bounds", "overlap")]
            return SolveResult(False, items, zones, bad, res, nearest_miss=bad[0].message.lower())
        return SolveResult(True, items, zones, [], res, placement=placement, moves=moves or [], new_furniture=new_furniture, gap_m=gap, notes=notes or [])

    # -- rejection details -----------------------------------------------------------------------------------------------------
    def _fit_rejection(self, target: LayoutItem, fur: FurnitureItem, items: list[LayoutItem], adjacent: list[str], failing: list[Violation]) -> SolveResult:
        """Nearest miss in plain numbers, and an alternative wall only if the item really fits along it."""
        others = [it for it in items if it.id != target.id]
        feature = next((f for f in adjacent if f in ("window", "door")), None)
        openings = self.sk.windows if feature == "window" else self.sk.doors if feature == "door" else []
        runs = {w: self._free_run(fur, others, w) for w in range(len(self.sk.walls))}
        fits_on = [w for w, (need, have) in runs.items() if need is not None and have + EPS >= need]
        if openings:
            wall = openings[0].wall
            need, have = runs[wall]
            alt = next((w for w in fits_on if w != wall), None)
            suggestion = f"it would fit on the {wall_label(self.sk, alt)}; want me to try that?" if alt is not None else "it doesn't fit along any other wall either."
            if need is not None and need > have + EPS:
                miss = f"it's {round((need - have) * 100)} cm too wide for the {wall_label(self.sk, wall)}; {suggestion}"
            else:
                miss = f"there's no free spot beside the {feature} for the {fur.name.lower()}; {suggestion}"
        elif fits_on:
            miss = f"there's no spot for the {fur.name.lower()} that passes the fit check here; it would fit along the {wall_label(self.sk, fits_on[0])} if you clear it."
        else:
            longest = max((have for _, have in runs.values()), default=0.0)
            miss = f"the {fur.name.lower()} ({fur.dims.w:.2f} x {fur.dims.d:.2f} m) is too long for every wall in this room; the longest free stretch is {longest:.2f} m"
        return SolveResult(False, items, violations=failing, nearest_miss=miss)

    def _free_run(self, fur: FurnitureItem, others: list[LayoutItem], wall: int) -> tuple[float | None, float]:
        """(length the item needs along `wall` when backed against it, longest free run along that wall)."""
        n = wall_inward_normal(self.sk, wall)
        rot = _rotation_facing(n)
        if rot is None:
            return None, 0.0
        fx, fz = footprint(fur.dims, rot)
        along = abs(n[1]) * fx + abs(n[0]) * fz
        depth = abs(n[0]) * fx + abs(n[1]) * fz
        blocked = self._occupied(others, with_door=True)
        run = best = 0
        for strip in self._wall_strips(wall, depth):
            run = 0 if any_mask_in_rect(self.grid, blocked, strip) else run + 1
            best = max(best, run)
        return along, best * GRID

    def _wall_strips(self, wall: int, depth: float) -> list[Rect]:
        w = self.sk.walls[wall]
        dx, dz = wall_dir(w)
        n = wall_inward_normal(self.sk, wall)
        strips = []
        for k in range(int(round(wall_length(w) / GRID))):
            xs = [w.x1 + dx * k * GRID, w.x1 + dx * (k + 1) * GRID]
            zs = [w.z1 + dz * k * GRID, w.z1 + dz * (k + 1) * GRID]
            xs += [x + n[0] * depth for x in xs]
            zs += [z + n[1] * depth for z in zs]
            strips.append(Rect(min(xs), min(zs), max(xs), max(zs)))
        return strips

    def _wall_gap(self, placed: LayoutItem, wall: int, items: list[LayoutItem]) -> float | None:
        """Smallest free distance along the wall between the placed item and a neighbour (or a wall end it isn't flush with)."""
        w = self.sk.walls[wall]
        dx, dz = wall_dir(w)
        length = wall_length(w)

        def span(r: Rect) -> tuple[float, float]:
            ts = [(cx - w.x1) * dx + (cz - w.z1) * dz for cx in (r.x0, r.x1) for cz in (r.z0, r.z1)]
            return min(ts), max(ts)

        mine = item_rect(placed.x, placed.z, placed.rotation, self.catalog[placed.furnitureId].dims)
        t0, t1 = span(mine)
        gaps = [g for g in (t0, length - t1) if g > EPS]
        along_x = abs(dx) > 0.5
        for it in items:
            if it.id == placed.id or not self._solid(it):
                continue
            r = item_rect(it.x, it.z, it.rotation, self.catalog[it.furnitureId].dims)
            if not ((r.z0 < mine.z1 - EPS and r.z1 > mine.z0 + EPS) if along_x else (r.x0 < mine.x1 - EPS and r.x1 > mine.x0 + EPS)):
                continue
            o0, o1 = span(r)
            if o0 >= t1 - EPS:
                gaps.append(o0 - t1)
            elif o1 <= t0 + EPS:
                gaps.append(t0 - o1)
        return round(max(0.0, min(gaps)), 3) if gaps else None
