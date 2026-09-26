"""Port of packages/geometry/src/grid.ts. Masks are bytearrays indexed j * nx + i."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.models import Dims, RoomSkeleton
from app.solver.constants import EPS, GRID, js_round
from app.solver.skeleton import Rect, point_in_polygon, room_bounds


@dataclass(frozen=True)
class Grid:
    nx: int
    nz: int
    ox: float
    oz: float
    room: bytearray


@dataclass(frozen=True)
class CellRange:
    i0: int
    i1: int
    j0: int
    j1: int


def make_grid(sk: RoomSkeleton) -> Grid:
    """Cells whose centers fall inside the floor polygon are room cells."""
    b = room_bounds(sk)
    nx, nz = js_round((b.x1 - b.x0) / GRID), js_round((b.z1 - b.z0) / GRID)
    room = bytearray(nx * nz)
    for j in range(nz):
        for i in range(nx):
            cx, cz = b.x0 + (i + 0.5) * GRID, b.z0 + (j + 0.5) * GRID
            if point_in_polygon(cx, cz, sk.floorPolygon):
                room[j * nx + i] = 1
    return Grid(nx, nz, b.x0, b.z0, room)


def _quarter_turns(rotation: float) -> int:
    return ((js_round(rotation / 90) % 4) + 4) % 4


def footprint(dims: Dims, rotation: float) -> tuple[float, float]:
    """Footprint (extent along x, extent along z) after rotation."""
    r = _quarter_turns(rotation)
    return (dims.w, dims.d) if r % 2 == 0 else (dims.d, dims.w)


def item_rect(x: float, z: float, rotation: float, dims: Dims) -> Rect:
    fx, fz = footprint(dims, rotation)
    return Rect(x - fx / 2, z - fz / 2, x + fx / 2, z + fz / 2)


def front_dir(rotation: float) -> tuple[int, int]:
    """Unit front direction in (x,z): 0 -> +z, 90 -> +x, 180 -> -z, 270 -> -x."""
    return ((0, 1), (1, 0), (0, -1), (-1, 0))[_quarter_turns(rotation)]


def rects_overlap(a: Rect, b: Rect) -> bool:
    return a.x0 < b.x1 - EPS and b.x0 < a.x1 - EPS and a.z0 < b.z1 - EPS and b.z0 < a.z1 - EPS


def rect_cells(g: Grid, r: Rect) -> CellRange:
    """Inclusive-exclusive cell index range covering the rect (cells with > EPS overlap)."""
    i0 = max(0, math.floor((r.x0 - g.ox) / GRID + EPS * 10))
    i1 = min(g.nx, math.ceil((r.x1 - g.ox) / GRID - EPS * 10))
    j0 = max(0, math.floor((r.z0 - g.oz) / GRID + EPS * 10))
    j1 = min(g.nz, math.ceil((r.z1 - g.oz) / GRID - EPS * 10))
    return CellRange(i0, i1, j0, j1)


def fill_rect(g: Grid, mask: bytearray, r: Rect, v: int = 1) -> None:
    c = rect_cells(g, r)
    for j in range(c.j0, c.j1):
        for i in range(c.i0, c.i1):
            mask[j * g.nx + i] = v


def fill_disc(g: Grid, mask: bytearray, cx: float, cz: float, radius: float) -> None:
    """Cells whose centers are within radius of (cx,cz)."""
    r2 = radius * radius
    for j in range(g.nz):
        for i in range(g.nx):
            x, z = g.ox + (i + 0.5) * GRID - cx, g.oz + (j + 0.5) * GRID - cz
            if x * x + z * z <= r2 + EPS:
                mask[j * g.nx + i] = 1


def count_mask_in_rect(g: Grid, mask: bytearray, r: Rect, room_only: bool = True) -> tuple[int, int]:
    """Returns (total, hit); cells outside the room count as obstructed when room_only."""
    c = rect_cells(g, r)
    total = hit = 0
    for j in range(c.j0, c.j1):
        for i in range(c.i0, c.i1):
            k = j * g.nx + i
            total += 1
            if room_only and not g.room[k]:
                hit += 1
                continue
            if mask[k]:
                hit += 1
    return total, hit


def any_mask_in_rect(g: Grid, mask: bytearray, r: Rect) -> bool:
    c = rect_cells(g, r)
    for j in range(c.j0, c.j1):
        for i in range(c.i0, c.i1):
            if mask[j * g.nx + i]:
                return True
    return False


def flood_fill(g: Grid, passable: bytearray, seeds: list[int]) -> bytearray:
    """4-neighbour flood fill over passable cells from seeds; returns the reachable mask."""
    seen = bytearray(g.nx * g.nz)
    stack: list[int] = []
    for s in seeds:
        if passable[s] and not seen[s]:
            seen[s] = 1
            stack.append(s)
    while stack:
        k = stack.pop()
        i = k % g.nx
        j = (k - i) // g.nx
        for n in (k - 1 if i > 0 else -1, k + 1 if i < g.nx - 1 else -1, k - g.nx if j > 0 else -1, k + g.nx if j < g.nz - 1 else -1):
            if n >= 0 and passable[n] and not seen[n]:
                seen[n] = 1
                stack.append(n)
    return seen


def erode(g: Grid, passable: bytearray, r: int) -> bytearray:
    """Erode a passable mask by r cells (Chebyshev) so only corridors >= (2r+1) cells wide survive."""
    out = bytearray(g.nx * g.nz)
    for j in range(g.nz):
        for i in range(g.nx):
            ok = passable[j * g.nx + i] == 1
            dj = -r
            while ok and dj <= r:
                di = -r
                while ok and di <= r:
                    ii, jj = i + di, j + dj
                    if ii < 0 or jj < 0 or ii >= g.nx or jj >= g.nz or not passable[jj * g.nx + ii]:
                        ok = False
                    di += 1
                dj += 1
            if ok:
                out[j * g.nx + i] = 1
    return out


def rect_neighbours(g: Grid, r: Rect) -> list[int]:
    """Cells adjacent (4-neighbour) to the rect but outside it."""
    c = rect_cells(g, r)
    out: list[int] = []
    for i in range(c.i0, c.i1):
        if c.j0 > 0:
            out.append((c.j0 - 1) * g.nx + i)
        if c.j1 < g.nz:
            out.append(c.j1 * g.nx + i)
    for j in range(c.j0, c.j1):
        if c.i0 > 0:
            out.append(j * g.nx + c.i0 - 1)
        if c.i1 < g.nx:
            out.append(j * g.nx + c.i1)
    return out


def largest_free_rect(g: Grid, occupied: bytearray) -> Rect | None:
    """Largest all-zero axis-aligned rectangle in the mask (1 = occupied/outside). Histogram method."""
    h = [0] * g.nx
    best = 0
    best_rect: Rect | None = None
    for j in range(g.nz):
        for i in range(g.nx):
            h[i] = 0 if occupied[j * g.nx + i] else h[i] + 1
        stack: list[int] = []
        for i in range(g.nx + 1):
            cur = 0 if i == g.nx else h[i]
            while stack and h[stack[-1]] >= cur:
                top = stack.pop()
                height = h[top]
                left = stack[-1] + 1 if stack else 0
                width = i - left
                area = height * width
                if area > best:
                    best = area
                    best_rect = Rect(g.ox + left * GRID, g.oz + (j - height + 1) * GRID, g.ox + i * GRID, g.oz + (j + 1) * GRID)
            stack.append(i)
    return best_rect
