import type { ValidationResult } from '@arp/contracts';
import { ACCESS_EDGE, DOOR_CLEARANCE } from './constants';
import { fillDisc, fillRect, floodFill, footprint, frontDir, itemRect, makeGrid, rectCells, type Grid } from './grid';
import { doorClearanceRect, doorHinge, type Rect } from './skeleton';
import type { ValidateInput } from './validate';

export interface OverlayMasks { grid: Grid; keepClear: Uint8Array; walkable: Uint8Array; lowClearance: Uint8Array; occupied: Uint8Array }

/** Cell masks for the floor overlays (green walkable / red keep-clear / yellow low-clearance). */
export function overlayMasks(input: ValidateInput, result?: ValidationResult): OverlayMasks {
  const { skeleton: sk, furniture: fur, layout } = input;
  const g = makeGrid(sk); const N = g.nx * g.nz;
  const occupied = new Uint8Array(N);
  const rects = new Map<string, Rect>();
  for (const it of layout.items) {
    const f = fur[it.furnitureId]; if (!f) continue;
    const r = itemRect(it, f.dims); rects.set(it.id, r);
    if (f.kind !== 'floor') fillRect(g, occupied, r);
  }
  const keepClear = new Uint8Array(N); const seeds: number[] = [];
  for (const d of sk.doors) {
    const clr = doorClearanceRect(sk, d, DOOR_CLEARANCE); fillRect(g, keepClear, clr);
    if (d.swing === 'in') { const { hinge, radius } = doorHinge(sk, d); fillDisc(g, keepClear, hinge[0], hinge[1], radius); }
    const { i0, i1, j0, j1 } = rectCells(g, clr); for (let j = j0; j < j1; j++) for (let i = i0; i < i1; i++) seeds.push(j * g.nx + i);
  }
  for (let k = 0; k < N; k++) if (!g.room[k]) keepClear[k] = 0;
  const passable = new Uint8Array(N); for (let k = 0; k < N; k++) passable[k] = g.room[k] && !occupied[k] ? 1 : 0;
  const walkable = floodFill(g, passable, seeds);
  const lowClearance = new Uint8Array(N);
  const flagged = new Set((result?.violations ?? []).filter((v) => v.rule === 'access_edge').flatMap((v) => v.items));
  for (const it of layout.items) {
    if (!flagged.has(it.id)) continue;
    const f = fur[it.furnitureId]; const r = rects.get(it.id)!;
    if (f.kind === 'bed' || f.kind === 'desk') {
      const { fx, fz } = footprint(f.dims, it.rotation);
      const bands: Rect[] = fx >= fz
        ? [{ x0: r.x0, x1: r.x1, z0: r.z0 - ACCESS_EDGE, z1: r.z0 }, { x0: r.x0, x1: r.x1, z0: r.z1, z1: r.z1 + ACCESS_EDGE }]
        : [{ x0: r.x0 - ACCESS_EDGE, x1: r.x0, z0: r.z0, z1: r.z1 }, { x0: r.x1, x1: r.x1 + ACCESS_EDGE, z0: r.z0, z1: r.z1 }];
      for (const b of bands) fillRect(g, lowClearance, b);
    } else {
      const [dx, dz] = frontDir(it.rotation);
      const b: Rect = dx > 0 ? { x0: r.x1, x1: r.x1 + ACCESS_EDGE, z0: r.z0, z1: r.z1 } : dx < 0 ? { x0: r.x0 - ACCESS_EDGE, x1: r.x0, z0: r.z0, z1: r.z1 }
        : dz > 0 ? { x0: r.x0, x1: r.x1, z0: r.z1, z1: r.z1 + ACCESS_EDGE } : { x0: r.x0, x1: r.x1, z0: r.z0 - ACCESS_EDGE, z1: r.z0 };
      fillRect(g, lowClearance, b);
    }
  }
  for (let k = 0; k < N; k++) if (!g.room[k]) lowClearance[k] = 0;
  return { grid: g, keepClear, walkable, lowClearance, occupied };
}

/** Distance from an item's rect to the nearest wall of a rectangular room bounds (m). */
export function gapToNearestWall(r: Rect, bounds: Rect): number {
  return Math.max(0, Math.min(r.x0 - bounds.x0, bounds.x1 - r.x1, r.z0 - bounds.z0, bounds.z1 - r.z1));
}
