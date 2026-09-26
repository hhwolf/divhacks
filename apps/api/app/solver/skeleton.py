"""Port of packages/geometry/src/skeleton.ts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from app.models import Door, RoomSkeleton, WallSegment, Window

Vec = tuple[float, float]
Compass = Literal["north", "south", "east", "west"]


@dataclass(frozen=True)
class Rect:
    x0: float
    z0: float
    x1: float
    z1: float


def wall_length(w: WallSegment) -> float:
    return math.hypot(w.x2 - w.x1, w.z2 - w.z1)


def wall_dir(w: WallSegment) -> Vec:
    """Unit direction along the wall from (x1,z1) to (x2,z2)."""
    length = wall_length(w)
    return ((w.x2 - w.x1) / length, (w.z2 - w.z1) / length)


def wall_inward_normal(sk: RoomSkeleton, i: int) -> Vec:
    """Inward normal: rotate dir by -90 degrees, flipped if it points away from the polygon centroid."""
    w = sk.walls[i]
    dx, dz = wall_dir(w)
    n: Vec = (-dz, dx)
    cx = sum(p[0] for p in sk.floorPolygon) / len(sk.floorPolygon)
    cz = sum(p[1] for p in sk.floorPolygon) / len(sk.floorPolygon)
    mx, mz = (w.x1 + w.x2) / 2, (w.z1 + w.z2) / 2
    if (cx - mx) * n[0] + (cz - mz) * n[1] < 0:
        n = (dz, -dx)
    return n


def opening_span(sk: RoomSkeleton, o: Door | Window) -> tuple[Vec, Vec]:
    """World-space start and end points of an opening along its wall."""
    w = sk.walls[o.wall]
    dx, dz = wall_dir(w)
    a: Vec = (w.x1 + dx * o.offset, w.z1 + dz * o.offset)
    b: Vec = (w.x1 + dx * (o.offset + o.width), w.z1 + dz * (o.offset + o.width))
    return a, b


def opening_band(sk: RoomSkeleton, o: Door | Window, depth: float) -> Rect:
    """Axis-aligned rect covering the opening span extended `depth` into the room."""
    a, b = opening_span(sk, o)
    n = wall_inward_normal(sk, o.wall)
    xs = [a[0], b[0], a[0] + n[0] * depth, b[0] + n[0] * depth]
    zs = [a[1], b[1], a[1] + n[1] * depth, b[1] + n[1] * depth]
    return Rect(min(xs), min(zs), max(xs), max(zs))


def door_clearance_rect(sk: RoomSkeleton, d: Door, depth: float) -> Rect:
    return opening_band(sk, d, depth)


def door_hinge(sk: RoomSkeleton, d: Door) -> tuple[Vec, float]:
    """Hinge point and swing radius for an inward-swinging door (quarter disc keep-clear)."""
    a, b = opening_span(sk, d)
    return (a if d.hinge == "left" else b), d.width


def window_band(sk: RoomSkeleton, w: Window, depth: float) -> Rect:
    return opening_band(sk, w, depth)


def room_bounds(sk: RoomSkeleton) -> Rect:
    xs = [p[0] for p in sk.floorPolygon]
    zs = [p[1] for p in sk.floorPolygon]
    return Rect(min(xs), min(zs), max(xs), max(zs))


def point_in_polygon(px: float, pz: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, zi = poly[i]
        xj, zj = poly[j]
        if (zi > pz) != (zj > pz) and px < ((xj - xi) * (pz - zi)) / (zj - zi) + xi:
            inside = not inside
        j = i
    return inside


def wall_by_compass(sk: RoomSkeleton, word: Compass) -> int:
    """north = min z, south = max z, west = min x, east = max x, by wall midpoint."""
    minimize = word in ("north", "west")
    best, best_v = 0, math.inf if minimize else -math.inf
    for i, w in enumerate(sk.walls):
        v = (w.z1 + w.z2) / 2 if word in ("north", "south") else (w.x1 + w.x2) / 2
        if (v < best_v) if minimize else (v > best_v):
            best_v, best = v, i
    return best
