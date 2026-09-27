"""RoomPlan USDZ (`CapturedRoom.export(to:, exportOptions: .parametric)`) -> canonical skeleton + detected objects.

Pure and synchronous: a file path in, a `ConvertedScan` out (callers run it in a worker thread). Steps follow the backend spec:
read stage units/up axis -> classify prims by name prefix (never by parent path) -> oriented local box per prim -> walls / doors /
windows / openings / floor / objects -> rotate so the longest wall lies on +x at the north (min z) side -> translate so the floor
polygon's min x and min z are 0 -> sanity checks. Failures raise `ConversionError` carrying a `conversionReport`.

Conventions (see DECISIONS.md): meters, floor plane x/z, y up; item rotation 0 means its front (local +z) faces +z and 90 faces +x;
walls are listed clockwise on screen starting with the longest wall, and doors/windows keep `{wall, offset}` from the wall's (x1,z1).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.models import Dimensions, Door, RoomSkeleton, WallSegment, Window

Vec2 = tuple[float, float]
Kind = Literal["wall", "door", "window", "opening", "floor", "object"]

ARCHITECTURE: dict[str, Kind] = {"Wall": "wall", "Door": "door", "Window": "window", "Opening": "opening", "Floor": "floor"}
FURNITURE_CATEGORIES = ("Bed", "Table", "Chair", "Sofa", "Storage", "Television")
FIXTURE_CATEGORIES = ("Refrigerator", "Stove", "Oven", "Dishwasher", "Sink", "Toilet", "Bathtub", "WasherDryer", "Fireplace", "Stairs")
_PREFIXES = sorted([*ARCHITECTURE, *FURNITURE_CATEGORIES, *FIXTURE_CATEGORIES], key=len, reverse=True)
# `Wall`, `Wall0`, `Wall_3`, `Wall0_mesh`, `Wall_3F2504E0...` match; group containers like `Wall_grp` / `Walls` do not.
_NAME_RE = re.compile(rf"^({'|'.join(_PREFIXES)})(?:[_\-]?\d\w*|[_\-][0-9a-f]{{8,}}\w*)?$", re.IGNORECASE)

MIN_WALLS = 3
FLOOR_AREA_M2 = (3.0, 100.0)
CEILING_M = (2.0, 4.0)
CORNER_MERGE_M = 0.15
DOOR_WIDTH_M = (0.5, 2.5)
WALL_HEIGHT_M = (1.5, 6.0)


class ConversionError(Exception):
    def __init__(self, message: str, report: dict[str, Any]) -> None:
        super().__init__(message)
        self.report = {**report, "error": message}


@dataclass
class ScannedObject:
    category: str  # RoomPlan category, e.g. "Bed", "Toilet"
    x: float
    z: float
    rotation: int  # 0 / 90 / 180 / 270
    w: float
    d: float
    h: float
    prim: str


@dataclass
class ConvertedScan:
    skeleton: RoomSkeleton
    objects: list[ScannedObject]
    report: dict[str, Any]


@dataclass
class _Box:
    """A prim's local box in canonical world space (meters, Y up)."""

    path: str
    kind: Kind
    category: str
    corners: list[tuple[float, float, float]]
    axes: list[tuple[float, float, float]]  # world vectors of the local x, y, z box edges
    points: list[tuple[float, float, float]] = field(default_factory=list)  # mesh points (floors only)

    @property
    def center(self) -> Vec2:
        return (sum(c[0] for c in self.corners) / 8, sum(c[2] for c in self.corners) / 8)

    @property
    def y_range(self) -> tuple[float, float]:
        ys = [c[1] for c in self.corners]
        return min(ys), max(ys)

    def horizontal_axes(self) -> list[tuple[int, float, Vec2]]:
        """(local axis index, horizontal length, unit xz direction) for the two axes that are not the vertical one."""
        up = max(range(3), key=lambda i: abs(self.axes[i][1]))
        out = []
        for i in range(3):
            if i == up:
                continue
            vx, vz = self.axes[i][0], self.axes[i][2]
            length = math.hypot(vx, vz)
            out.append((i, length, (vx / length, vz / length) if length > 1e-9 else (0.0, 0.0)))
        return out


# ---- geometry helpers ------------------------------------------------------------------------------------------------------


def _rot(p: Vec2, c: float, s: float) -> Vec2:
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def _shoelace(poly: list[Vec2]) -> float:
    return sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly))) / 2


def _angle_sorted(points: list[Vec2]) -> list[Vec2]:
    cx = sum(p[0] for p in points) / len(points)
    cz = sum(p[1] for p in points) / len(points)
    return sorted(points, key=lambda p: math.atan2(p[1] - cz, p[0] - cx))


def _merge(points: list[Vec2], tol: float) -> list[Vec2]:
    """Collapse points closer than `tol` (shared wall corners, top/bottom rings of a floor slab) into their mean."""
    clusters: list[list[Vec2]] = []
    for p in points:
        for cl in clusters:
            if math.dist(cl[0], p) <= tol:
                cl.append(p)
                break
        else:
            clusters.append([p])
    return [(sum(q[0] for q in cl) / len(cl), sum(q[1] for q in cl) / len(cl)) for cl in clusters]


def _seg_distance(p: Vec2, a: Vec2, b: Vec2) -> tuple[float, float]:
    """(distance from p to segment ab, projection t along ab in meters)."""
    dx, dz = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dz)
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / length if length else 0.0
    tc = min(max(t, 0.0), length)
    q = (a[0] + dx / length * tc, a[1] + dz / length * tc) if length else a
    return math.dist(p, q), t


def _r(v: float) -> float:
    return round(v, 3) + 0.0  # + 0.0 turns -0.0 into 0.0


# ---- USD reading -----------------------------------------------------------------------------------------------------------


def classify(name: str) -> tuple[Kind, str] | None:
    m = _NAME_RE.match(name)
    if not m:
        return None
    prefix = next(p for p in _PREFIXES if p.lower() == m.group(1).lower())
    return ARCHITECTURE.get(prefix, "object"), prefix


def _local_box(element: Any, element_to_world: Any, bbox_cache: Any, xf_cache: Any) -> tuple[Any, Any] | None:
    """Tight box of an element in its own frame, or None without geometry.

    `BBoxCache.ComputeUntransformedBound(element)` is loose when the element's geometry sits under a child transform (RoomPlan puts
    each wall's scaled box one level below the wall Xform): children are merged as world-aligned boxes. So each leaf gprim's own
    untransformed extent (tight, in its local space) is mapped into the element frame and accumulated there. Nested elements of
    another category (a door under its wall) are skipped.
    """
    from pxr import Gf, Usd, UsdGeom

    to_element = element_to_world.GetInverse()
    acc = Gf.Range3d()
    it = iter(Usd.PrimRange(element))
    for p in it:
        if p != element and classify(p.GetName()) not in (None, classify(element.GetName())):
            it.PruneChildren()
            continue
        if not p.IsA(UsdGeom.Gprim):
            continue
        r = bbox_cache.ComputeUntransformedBound(p).ComputeAlignedBox()
        if r.IsEmpty():
            continue
        m = xf_cache.GetLocalToWorldTransform(p) * to_element
        lo, hi = r.GetMin(), r.GetMax()
        for x in (lo[0], hi[0]):
            for y in (lo[1], hi[1]):
                for z in (lo[2], hi[2]):
                    acc.UnionWith(m.Transform(Gf.Vec3d(x, y, z)))
    return None if acc.IsEmpty() else (acc.GetMin(), acc.GetMax())


def _read(path: Path) -> tuple[list[_Box], dict[str, Any]]:
    from pxr import Gf, Usd, UsdGeom  # imported lazily: usd-core is only needed for scan ingest

    stage = Usd.Stage.Open(str(path))
    if stage is None:
        raise ConversionError("could not open USDZ", {"primCounts": {}, "warnings": []})
    warnings: list[str] = []
    if stage.HasAuthoredMetadata("metersPerUnit"):
        mpu = float(UsdGeom.GetStageMetersPerUnit(stage))
    else:
        mpu = 1.0
        warnings.append("metersPerUnit not authored; assuming meters (RoomPlan's unit)")
    up = str(UsdGeom.GetStageUpAxis(stage))

    def canon(v: Any) -> tuple[float, float, float]:
        x, y, z = float(v[0]), float(v[1]), float(v[2])
        if up == "Z":  # Z-up right-handed -> Y-up right-handed
            x, y, z = x, z, -y
        return (x * mpu, y * mpu, z * mpu)

    time = Usd.TimeCode.Default()
    bbox_cache = UsdGeom.BBoxCache(time, [UsdGeom.Tokens.default_])
    xf_cache = UsdGeom.XformCache(time)
    counts: dict[str, int] = {}
    boxes: list[_Box] = []
    claimed: dict[str, str] = {}  # prim path -> category, to drop nested duplicates (only the highest prim per name counts)

    for prim in stage.Traverse():
        hit = classify(prim.GetName())
        if hit is None:
            continue
        kind, category = hit
        path_str = str(prim.GetPath())
        parent = prim.GetParent()
        duplicate = False
        while parent and not parent.IsPseudoRoot():
            if claimed.get(str(parent.GetPath())) == category:
                duplicate = True
                break
            parent = parent.GetParent()
        if duplicate:
            counts["duplicate"] = counts.get("duplicate", 0) + 1
            continue
        m = xf_cache.GetLocalToWorldTransform(prim)
        box = _local_box(prim, m, bbox_cache, xf_cache)
        if box is None:
            counts["noGeometry"] = counts.get("noGeometry", 0) + 1
            continue
        claimed[path_str] = category
        lo, hi = box
        corners = [canon(m.Transform(Gf.Vec3d(x, y, z))) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        origin = canon(m.Transform(Gf.Vec3d(lo[0], lo[1], lo[2])))
        ends = [canon(m.Transform(Gf.Vec3d(*(hi[i] if i == k else lo[i] for i in range(3))))) for k in range(3)]
        axes = [(e[0] - origin[0], e[1] - origin[1], e[2] - origin[2]) for e in ends]
        points: list[tuple[float, float, float]] = []
        if kind == "floor":
            for p in Usd.PrimRange(prim):
                if p.IsA(UsdGeom.Mesh):
                    pm = xf_cache.GetLocalToWorldTransform(p)
                    points.extend(canon(pm.Transform(Gf.Vec3d(*pt))) for pt in (UsdGeom.Mesh(p).GetPointsAttr().Get(time) or []))
        boxes.append(_Box(path_str, kind, category, corners, axes, points))
        counts[kind] = counts.get(kind, 0) + 1

    return boxes, {"primCounts": counts, "metersPerUnit": mpu, "upAxis": up, "warnings": warnings}


# ---- conversion ------------------------------------------------------------------------------------------------------------


def convert_usdz(path: str | Path) -> ConvertedScan:
    boxes, report = _read(Path(path))
    warnings: list[str] = report["warnings"]

    walls_raw: list[tuple[Vec2, Vec2, float, float]] = []  # a, b, height, thickness
    for b in (b for b in boxes if b.kind == "wall"):
        (_, la, da), (_, lb, db) = b.horizontal_axes()
        along, length, thick = (da, la, lb) if la >= lb else (db, lb, la)
        cx, cz = b.center
        y0, y1 = b.y_range
        a = (cx - along[0] * length / 2, cz - along[1] * length / 2)
        e = (cx + along[0] * length / 2, cz + along[1] * length / 2)
        walls_raw.append((a, e, y1 - y0, thick))
    if len(walls_raw) < MIN_WALLS:
        raise ConversionError(f"found {len(walls_raw)} walls; need at least {MIN_WALLS}", report)

    floors = [b for b in boxes if b.kind == "floor"]
    floor_y = min(b.y_range[0] for b in floors) if floors else min(b.y_range[0] for b in boxes if b.kind == "wall")
    if floors:
        pts = [p for f in floors for p in (f.points or f.corners)]
        polygon = _angle_sorted(_merge([(p[0], p[2]) for p in pts], 0.01))
        if len(polygon) < 3:
            warnings.append("Floor prim has fewer than 3 distinct points; using wall endpoints")
            polygon = []
    else:
        polygon = []
        warnings.append("no Floor prim; floor polygon chained from wall endpoints")
    if not polygon:
        polygon = _angle_sorted(_merge([p for a, e, _, _ in walls_raw for p in (a, e)], CORNER_MERGE_M))

    # Normalize: longest wall along +x at the min-z (north) side, then floor polygon min corner at the origin. Walls within 1 cm
    # of the longest tie (rectangular rooms have two); prefer a window wall, then one without a door, so the choice never depends
    # on float noise or prim order.
    def hosts(kind: str, a: Vec2, e: Vec2) -> bool:
        return any(_seg_distance(b.center, a, e)[0] < 0.3 for b in boxes if b.kind == kind)

    longest = max(math.dist(w[0], w[1]) for w in walls_raw)
    ties = [w for w in walls_raw if math.dist(w[0], w[1]) >= longest - 0.01]
    la_, le_, _, _ = min(ties, key=lambda w: (not hosts("window", w[0], w[1]), hosts("door", w[0], w[1])))
    phi = -math.atan2(le_[1] - la_[1], le_[0] - la_[0])
    c, s = math.cos(phi), math.sin(phi)
    cz = sum(_rot(p, c, s)[1] for p in polygon) / len(polygon)
    if (_rot(la_, c, s)[1] + _rot(le_, c, s)[1]) / 2 > cz:
        phi += math.pi
        c, s = math.cos(phi), math.sin(phi)
    rotated = [_rot(p, c, s) for p in polygon]
    ox, oz = min(p[0] for p in rotated), min(p[1] for p in rotated)

    def norm(p: Vec2) -> Vec2:
        q = _rot(p, c, s)
        return (_r(q[0] - ox), _r(q[1] - oz))

    polygon = [norm(p) for p in polygon]
    if _shoelace(polygon) < 0:
        polygon.reverse()  # clockwise on screen (x right, z toward the viewer), like the sample rooms
    start = min(range(len(polygon)), key=lambda i: math.hypot(*polygon[i]))
    polygon = polygon[start:] + polygon[:start]
    area = _shoelace(polygon)
    pcx = sum(p[0] for p in polygon) / len(polygon)
    pcz = sum(p[1] for p in polygon) / len(polygon)

    # Walls: clockwise on screen (a->b turns around the centroid), longest (north) wall first.
    oriented = []
    for a, e, h, t in walls_raw:
        a, e = norm(a), norm(e)
        mx, mz = (a[0] + e[0]) / 2, (a[1] + e[1]) / 2
        if (mx - pcx) * (e[1] - a[1]) - (mz - pcz) * (e[0] - a[0]) < 0:
            a, e = e, a
        oriented.append((a, e, h, t, math.atan2(mz - pcz, mx - pcx)))
    first = max(oriented, key=lambda w: math.dist(w[0], w[1]))[4]
    oriented.sort(key=lambda w: (w[4] - first) % (2 * math.pi))
    ceiling = max(w[2] for w in oriented)
    walls = []
    for i, (a, e, h, t, _) in enumerate(oriented):
        if not WALL_HEIGHT_M[0] <= h <= WALL_HEIGHT_M[1]:
            warnings.append(f"wall {i} height {h:.2f} m clamped to {WALL_HEIGHT_M}")
            h = min(max(h, WALL_HEIGHT_M[0]), WALL_HEIGHT_M[1])
        walls.append(WallSegment(x1=a[0], z1=a[1], x2=e[0], z2=e[1], height=_r(h), id=f"w{i}", thickness=_r(t)))

    def attach(center: Vec2, width: float, label: str) -> tuple[int, float, float]:
        """Nearest wall by point-segment distance; returns (wall index, offset from (x1,z1), width clamped to the wall)."""
        best = min(range(len(walls)), key=lambda i: _seg_distance(center, (walls[i].x1, walls[i].z1), (walls[i].x2, walls[i].z2))[0])
        w = walls[best]
        length = math.hypot(w.x2 - w.x1, w.z2 - w.z1)
        dist, t = _seg_distance(center, (w.x1, w.z1), (w.x2, w.z2))
        if dist > 0.3:
            warnings.append(f"{label} is {dist:.2f} m from the nearest wall")
        width = min(width, length)
        return best, _r(min(max(t - width / 2, 0.0), length - width)), width

    doors: list[Door] = []
    windows: list[Window] = []
    for b in boxes:
        if b.kind not in ("door", "opening", "window"):
            continue
        center = norm(b.center)
        width = max(length for _, length, _ in b.horizontal_axes())
        y0, y1 = b.y_range
        if b.kind == "window":
            wall, offset, width = attach(center, width, f"window {len(windows)}")
            windows.append(Window(
                wall=wall, offset=offset, width=_r(max(width, 0.3)), sillHeight=_r(max(y0 - floor_y, 0.0)), height=_r(max(y1 - y0, 0.3)),
                id=f"win{len(windows)}", wallId=walls[wall].id, center=center,
            ))
            continue
        if not DOOR_WIDTH_M[0] <= width <= DOOR_WIDTH_M[1]:
            warnings.append(f"{b.kind} {b.path} width {width:.2f} m clamped to {DOOR_WIDTH_M}")
            width = min(max(width, DOOR_WIDTH_M[0]), DOOR_WIDTH_M[1])
        wall, offset, width = attach(center, width, f"{b.kind} {len(doors)}")
        opening = b.kind == "opening"
        doors.append(Door(
            wall=wall, offset=offset, width=_r(width), height=_r(y1 - y0), swing="out" if opening else "in", hinge="left",
            id=f"d{len(doors)}", wallId=walls[wall].id, center=center, opening=True if opening else None,
        ))

    objects: list[ScannedObject] = []
    for b in (b for b in boxes if b.kind == "object"):
        axes = {i: (length, direction) for i, length, direction in b.horizontal_axes()}
        (wi, (w_len, _)), (di, (d_len, front)) = sorted(axes.items())  # lower local axis index = width, the other = depth/front
        fx, fz = _rot(front, c, s)
        yaw = math.degrees(math.atan2(fx, fz)) if (fx or fz) else 0.0
        x, z = norm(b.center)
        y0, y1 = b.y_range
        objects.append(ScannedObject(b.category, x, z, int(round(yaw / 90)) % 4 * 90, _r(w_len), _r(d_len), _r(y1 - y0), b.path))

    report = {**report, "floorAreaM2": round(area, 2), "ceilingHeightM": round(ceiling, 2), "objects": len(objects)}
    if not FLOOR_AREA_M2[0] <= area <= FLOOR_AREA_M2[1]:
        raise ConversionError(f"floor area {area:.1f} m² is outside {FLOOR_AREA_M2[0]}–{FLOOR_AREA_M2[1]} m²", report)
    if not CEILING_M[0] <= ceiling <= CEILING_M[1]:
        raise ConversionError(f"ceiling height {ceiling:.2f} m is outside {CEILING_M[0]}–{CEILING_M[1]} m", report)

    skeleton = RoomSkeleton(
        walls=walls,
        doors=doors,
        windows=windows,
        floorPolygon=polygon,
        dimensions=Dimensions(l=_r(max(p[0] for p in polygon)), w=_r(max(p[1] for p in polygon)), h=_r(ceiling)),
        ceilingHeight=_r(ceiling),
    )
    return ConvertedScan(skeleton, objects, report)
