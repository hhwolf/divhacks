import type { Dims, LayoutItem, RoomSkeleton, Rotation } from '@arp/contracts';
import { EPS, GRID } from './constants';
import { pointInPolygon, roomBounds, type Rect } from './skeleton';

export interface Grid { nx: number; nz: number; ox: number; oz: number; room: Uint8Array }

/** Cells whose centers fall inside the floor polygon are room cells. */
export function makeGrid(sk: RoomSkeleton): Grid {
  const b = roomBounds(sk);
  const nx = Math.round((b.x1 - b.x0) / GRID), nz = Math.round((b.z1 - b.z0) / GRID);
  const room = new Uint8Array(nx * nz);
  for (let j = 0; j < nz; j++) for (let i = 0; i < nx; i++) {
    const cx = b.x0 + (i + 0.5) * GRID, cz = b.z0 + (j + 0.5) * GRID;
    if (pointInPolygon(cx, cz, sk.floorPolygon)) room[j * nx + i] = 1;
  }
  return { nx, nz, ox: b.x0, oz: b.z0, room };
}

/** Footprint (w along x, d along z) after rotation. */
export function footprint(dims: Dims, rotation: Rotation | number): { fx: number; fz: number } {
  const r = ((Math.round(rotation / 90) % 4) + 4) % 4;
  return r % 2 === 0 ? { fx: dims.w, fz: dims.d } : { fx: dims.d, fz: dims.w };
}
export function itemRect(item: { x: number; z: number; rotation: number }, dims: Dims): Rect {
  const { fx, fz } = footprint(dims, item.rotation);
  return { x0: item.x - fx / 2, z0: item.z - fz / 2, x1: item.x + fx / 2, z1: item.z + fz / 2 };
}
/** Unit front direction in (x,z) for a rotation: 0 → +z, 90 → +x, 180 → -z, 270 → -x. */
export function frontDir(rotation: number): [number, number] {
  const r = ((Math.round(rotation / 90) % 4) + 4) % 4;
  return ([[0, 1], [1, 0], [0, -1], [-1, 0]] as [number, number][])[r];
}
/** Whether a rect's long axis runs along x. */
export function longAxisIsX(dims: Dims, rotation: number): boolean { const { fx, fz } = footprint(dims, rotation); return fx >= fz; }

export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x0 < b.x1 - EPS && b.x0 < a.x1 - EPS && a.z0 < b.z1 - EPS && b.z0 < a.z1 - EPS;
}
export function rectCells(g: Grid, r: Rect): { i0: number; i1: number; j0: number; j1: number } {
  // inclusive-exclusive cell index range covering the rect (cells with > EPS overlap)
  const i0 = Math.max(0, Math.floor((r.x0 - g.ox) / GRID + EPS * 10)), i1 = Math.min(g.nx, Math.ceil((r.x1 - g.ox) / GRID - EPS * 10));
  const j0 = Math.max(0, Math.floor((r.z0 - g.oz) / GRID + EPS * 10)), j1 = Math.min(g.nz, Math.ceil((r.z1 - g.oz) / GRID - EPS * 10));
  return { i0, i1, j0, j1 };
}
export function fillRect(g: Grid, mask: Uint8Array, r: Rect, v = 1): void {
  const { i0, i1, j0, j1 } = rectCells(g, r);
  for (let j = j0; j < j1; j++) for (let i = i0; i < i1; i++) mask[j * g.nx + i] = v;
}
/** Fill a quarter/whole disc: cells whose centers are within radius of (cx,cz). */
export function fillDisc(g: Grid, mask: Uint8Array, cx: number, cz: number, radius: number): void {
  const r2 = radius * radius;
  for (let j = 0; j < g.nz; j++) for (let i = 0; i < g.nx; i++) {
    const x = g.ox + (i + 0.5) * GRID - cx, z = g.oz + (j + 0.5) * GRID - cz;
    if (x * x + z * z <= r2 + EPS) mask[j * g.nx + i] = 1;
  }
}
export function countMaskInRect(g: Grid, mask: Uint8Array, r: Rect, roomOnly = true): { total: number; hit: number } {
  const { i0, i1, j0, j1 } = rectCells(g, r);
  let total = 0, hit = 0;
  for (let j = j0; j < j1; j++) for (let i = i0; i < i1; i++) {
    const k = j * g.nx + i;
    if (roomOnly && !g.room[k]) { total++; hit++; continue; } // outside the room counts as obstructed
    total++; if (mask[k]) hit++;
  }
  return { total, hit };
}
export function anyMaskInRect(g: Grid, mask: Uint8Array, r: Rect): boolean {
  const { i0, i1, j0, j1 } = rectCells(g, r);
  for (let j = j0; j < j1; j++) for (let i = i0; i < i1; i++) if (mask[j * g.nx + i]) return true;
  return false;
}
/** 4-neighbour flood fill over `passable` cells from `seeds`; returns reachable mask. */
export function floodFill(g: Grid, passable: Uint8Array, seeds: number[]): Uint8Array {
  const seen = new Uint8Array(g.nx * g.nz); const stack: number[] = [];
  for (const s of seeds) if (passable[s] && !seen[s]) { seen[s] = 1; stack.push(s); }
  while (stack.length) {
    const k = stack.pop()!; const i = k % g.nx, j = (k - i) / g.nx;
    const nb = [i > 0 ? k - 1 : -1, i < g.nx - 1 ? k + 1 : -1, j > 0 ? k - g.nx : -1, j < g.nz - 1 ? k + g.nx : -1];
    for (const n of nb) if (n >= 0 && passable[n] && !seen[n]) { seen[n] = 1; stack.push(n); }
  }
  return seen;
}
/** Erode a passable mask by `r` cells (Chebyshev) so only corridors ≥ (2r+1) cells wide survive. */
export function erode(g: Grid, passable: Uint8Array, r: number): Uint8Array {
  const out = new Uint8Array(g.nx * g.nz);
  for (let j = 0; j < g.nz; j++) for (let i = 0; i < g.nx; i++) {
    let ok = passable[j * g.nx + i] === 1;
    for (let dj = -r; ok && dj <= r; dj++) for (let di = -r; ok && di <= r; di++) {
      const ii = i + di, jj = j + dj;
      if (ii < 0 || jj < 0 || ii >= g.nx || jj >= g.nz || !passable[jj * g.nx + ii]) ok = false;
    }
    if (ok) out[j * g.nx + i] = 1;
  }
  return out;
}
/** Cells adjacent (4-neighbour) to the rect but outside it. */
export function rectNeighbours(g: Grid, r: Rect): number[] {
  const { i0, i1, j0, j1 } = rectCells(g, r); const out: number[] = [];
  for (let i = i0; i < i1; i++) { if (j0 > 0) out.push((j0 - 1) * g.nx + i); if (j1 < g.nz) out.push(j1 * g.nx + i); }
  for (let j = j0; j < j1; j++) { if (i0 > 0) out.push(j * g.nx + i0 - 1); if (i1 < g.nx) out.push(j * g.nx + i1); }
  return out;
}
/** Largest all-zero (free) axis-aligned rectangle in the mask (1 = occupied/outside). Histogram method. */
export function largestFreeRect(g: Grid, occupied: Uint8Array): Rect | null {
  const h = new Int32Array(g.nx); let best = 0; let bestRect: Rect | null = null;
  for (let j = 0; j < g.nz; j++) {
    for (let i = 0; i < g.nx; i++) h[i] = occupied[j * g.nx + i] ? 0 : h[i] + 1;
    const stack: number[] = [];
    for (let i = 0; i <= g.nx; i++) {
      const cur = i === g.nx ? 0 : h[i];
      while (stack.length && h[stack[stack.length - 1]] >= cur) {
        const top = stack.pop()!; const height = h[top]; const left = stack.length ? stack[stack.length - 1] + 1 : 0; const width = i - left;
        const area = height * width;
        if (area > best) { best = area; bestRect = { x0: g.ox + left * GRID, z0: g.oz + (j - height + 1) * GRID, x1: g.ox + i * GRID, z1: g.oz + (j + 1) * GRID }; }
      }
      stack.push(i);
    }
  }
  return bestRect;
}
export type { LayoutItem };
