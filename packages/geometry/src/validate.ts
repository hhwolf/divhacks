import type { FurnitureItem, Layout, LayoutItem, LayoutMetrics, RoomSkeleton, ValidationResult, Violation, Walkability, Zone } from '@arp/contracts';
import { ACCESS_EDGE, ACCESS_FREE_RATIO, CORRIDOR_CELLS, DOOR_CLEARANCE, EPS, GRID, M2_TO_SQFT, STORAGE_FRONT, WINDOW_BAND } from './constants';
import {
  anyMaskInRect, countMaskInRect, erode, fillDisc, fillRect, floodFill, footprint, frontDir, itemRect, largestFreeRect, makeGrid,
  rectCells, rectNeighbours, rectsOverlap, type Grid,
} from './grid';
import { doorClearanceRect, doorHinge, pointInPolygon, windowBand, type Rect } from './skeleton';

export type FurnitureLookup = Record<string, Pick<FurnitureItem, 'id' | 'name' | 'kind' | 'dims'>>;
export interface ValidateInput {
  skeleton: RoomSkeleton;
  furniture: FurnitureLookup;
  layout: Pick<Layout, 'items' | 'zones'>;
  /** When given (agent/solver context), locked items in base must be unchanged in layout. */
  baseLayout?: Pick<Layout, 'items'> | null;
}

const BLOCKING = new Set(['bounds', 'overlap']);
const round1 = (v: number) => Math.round(v * 10) / 10;
const round2 = (v: number) => Math.round(v * 100) / 100;

function nameOf(f: FurnitureLookup, it: LayoutItem): string { return f[it.furnitureId]?.name ?? it.furnitureId; }
function isFloor(f: FurnitureLookup, it: LayoutItem): boolean { return f[it.furnitureId]?.kind === 'floor'; }

/** Cells of the 0.75 m band outside one edge of a rect. side: 'x0'|'x1'|'z0'|'z1'. */
function bandRect(r: Rect, side: 'x0' | 'x1' | 'z0' | 'z1', depth: number): Rect {
  switch (side) {
    case 'x0': return { x0: r.x0 - depth, x1: r.x0, z0: r.z0, z1: r.z1 };
    case 'x1': return { x0: r.x1, x1: r.x1 + depth, z0: r.z0, z1: r.z1 };
    case 'z0': return { x0: r.x0, x1: r.x1, z0: r.z0 - depth, z1: r.z0 };
    case 'z1': return { x0: r.x0, x1: r.x1, z0: r.z1, z1: r.z1 + depth };
  }
}
function bandFree(g: Grid, occupied: Uint8Array, band: Rect): number {
  const { total, hit } = countMaskInRect(g, occupied, band, true);
  return total === 0 ? 0 : (total - hit) / total;
}
function fitsLabel(w: number, d: number): string {
  const cands: [string, number, number][] = [
    ['a queen bed', 1.5, 2.0], ['a desk and chair', 1.2, 1.4], ['a yoga mat', 0.61, 1.83], ['a desk', 1.2, 0.6], ['an armchair', 0.9, 0.9], ['a nightstand', 0.45, 0.4],
  ];
  const a = Math.max(w, d), b = Math.min(w, d);
  for (const [label, cw, cd] of cands) if (a + EPS >= Math.max(cw, cd) && b + EPS >= Math.min(cw, cd)) return label;
  return 'not much';
}

export function validateLayout(input: ValidateInput): ValidationResult {
  const { skeleton: sk, furniture: fur, layout, baseLayout } = input;
  const g = makeGrid(sk);
  const N = g.nx * g.nz;
  const violations: Violation[] = [];
  const items = layout.items;
  const rects = new Map<string, Rect>();
  for (const it of items) { const f = fur[it.furnitureId]; if (f) rects.set(it.id, itemRect(it, f.dims)); }

  // Occupancy by solid (non-floor) items.
  const occupied = new Uint8Array(N);
  const occupiedBy = new Map<string, Uint8Array>();
  for (const it of items) {
    if (!rects.has(it.id) || isFloor(fur, it)) continue;
    const m = new Uint8Array(N); fillRect(g, m, rects.get(it.id)!); occupiedBy.set(it.id, m);
    for (let k = 0; k < N; k++) if (m[k]) occupied[k] = 1;
  }

  // 1. Room bounds: all four corners inside the polygon (inclusive).
  for (const it of items) {
    const r = rects.get(it.id); if (!r) continue;
    const corners: [number, number][] = [[r.x0, r.z0], [r.x1, r.z0], [r.x0, r.z1], [r.x1, r.z1]];
    const inside = corners.every(([x, z]) => {
      // nudge toward the rect center so exact-edge contact counts as inside
      const cx = (r.x0 + r.x1) / 2, cz = (r.z0 + r.z1) / 2;
      return pointInPolygon(x + Math.sign(cx - x) * 1e-4, z + Math.sign(cz - z) * 1e-4, sk.floorPolygon);
    });
    if (!inside) violations.push({ rule: 'bounds', severity: 'error', items: [it.id], message: `${nameOf(fur, it)} is outside the room` });
  }

  // 2. Overlap between solid items.
  const solids = items.filter((it) => rects.has(it.id) && !isFloor(fur, it));
  for (let a = 0; a < solids.length; a++) for (let b = a + 1; b < solids.length; b++) {
    const A = solids[a], B = solids[b];
    if (rectsOverlap(rects.get(A.id)!, rects.get(B.id)!))
      violations.push({ rule: 'overlap', severity: 'error', items: [A.id, B.id].sort(), message: `${nameOf(fur, A)} overlaps ${nameOf(fur, B)}` });
  }

  // 3. Locked items unchanged vs base layout (agent context).
  if (baseLayout) {
    const byId = new Map(items.map((i) => [i.id, i]));
    for (const b of baseLayout.items) {
      if (!b.locked) continue;
      const cur = byId.get(b.id);
      if (!cur || Math.abs(cur.x - b.x) > EPS || Math.abs(cur.z - b.z) > EPS || cur.rotation !== b.rotation)
        violations.push({ rule: 'locked', severity: 'error', items: [b.id], message: `${nameOf(fur, b)} is locked and was moved` });
    }
  }

  // 4. Door swing arc + 0.9 m clearance.
  const keepClear = new Uint8Array(N);
  const doorSeeds: number[] = [];
  for (const d of sk.doors) {
    const clr = doorClearanceRect(sk, d, DOOR_CLEARANCE);
    fillRect(g, keepClear, clr);
    if (d.swing === 'in') { const { hinge, radius } = doorHinge(sk, d); fillDisc(g, keepClear, hinge[0], hinge[1], radius); }
    const { i0, i1, j0, j1 } = rectCells(g, clr);
    for (let j = j0; j < j1; j++) for (let i = i0; i < i1; i++) doorSeeds.push(j * g.nx + i);
  }
  for (let k = 0; k < N; k++) if (!g.room[k]) keepClear[k] = 0;
  for (const it of solids) {
    if (anyMaskInRect(g, keepClear, rects.get(it.id)!))
      violations.push({ rule: 'door_clearance', severity: 'error', items: [it.id], message: `${nameOf(fur, it)} blocks the door swing` });
  }

  // 5. Window keep-clear (warning): items taller than the sill inside the window band.
  for (const w of sk.windows) {
    const band = windowBand(sk, w, WINDOW_BAND);
    for (const it of solids) {
      const f = fur[it.furnitureId];
      if (f.dims.h > w.sillHeight + EPS && rectsOverlap(band, rects.get(it.id)!))
        violations.push({ rule: 'window_keep_clear', severity: 'warning', items: [it.id], message: `${nameOf(fur, it)} is taller than the window sill and blocks the window` });
    }
  }

  // 6. Access edges: beds/desks one long edge; wardrobes/dressers the front.
  const storageReach: boolean[] = [];
  for (const it of solids) {
    const f = fur[it.furnitureId]; const r = rects.get(it.id)!;
    const others = new Uint8Array(occupied); const own = occupiedBy.get(it.id)!;
    for (let k = 0; k < N; k++) if (own[k]) others[k] = 0;
    if (f.kind === 'bed' || f.kind === 'desk') {
      const { fx, fz } = footprint(f.dims, it.rotation);
      const sides: ('x0' | 'x1' | 'z0' | 'z1')[] = fx >= fz ? ['z0', 'z1'] : ['x0', 'x1'];
      const free = sides.map((s) => bandFree(g, others, bandRect(r, s, ACCESS_EDGE)));
      if (!free.some((v) => v + EPS >= ACCESS_FREE_RATIO))
        violations.push({ rule: 'access_edge', severity: 'warning', items: [it.id], message: `${nameOf(fur, it)} has no free long edge (${Math.round(ACCESS_EDGE * 100)} cm)` });
    } else if (f.kind === 'wardrobe' || f.kind === 'dresser' || f.kind === 'storage') {
      const [dx, dz] = frontDir(it.rotation);
      const side = dx > 0 ? 'x1' : dx < 0 ? 'x0' : dz > 0 ? 'z1' : 'z0';
      const ratio = bandFree(g, others, bandRect(r, side, STORAGE_FRONT));
      const ok = ratio + EPS >= ACCESS_FREE_RATIO;
      storageReach.push(ok);
      if ((f.kind === 'wardrobe' || f.kind === 'dresser') && !ok)
        violations.push({ rule: 'access_edge', severity: 'warning', items: [it.id], message: `${nameOf(fur, it)} needs ${Math.round(STORAGE_FRONT * 100)} cm clear in front` });
    }
  }

  // 7. Requested clear zones must be free.
  for (const z of layout.zones ?? []) {
    const zr: Rect = { x0: z.x, z0: z.z, x1: z.x + z.w, z1: z.z + z.d };
    const blockers = solids.filter((it) => rectsOverlap(zr, rects.get(it.id)!)).map((it) => it.id).sort();
    if (blockers.length) violations.push({ rule: 'clear_zone', severity: 'warning', items: blockers, message: `${z.label} zone is blocked by ${blockers.map((id) => nameOf(fur, items.find((i) => i.id === id)!)).join(', ')}` });
  }

  // 8. Walkable path from the door to every bed and desk.
  const passable = new Uint8Array(N); for (let k = 0; k < N; k++) passable[k] = g.room[k] && !occupied[k] ? 1 : 0;
  const seeds = doorSeeds.length ? doorSeeds : [...Array(N).keys()].filter((k) => passable[k]).slice(0, 1);
  const reach = floodFill(g, passable, seeds);
  const eroded = erode(g, passable, CORRIDOR_CELLS);
  const wide = floodFill(g, eroded, seeds.filter((k) => eroded[k]));
  let walk: Walkability = 'Good';
  for (const it of solids) {
    const f = fur[it.furnitureId]; if (f.kind !== 'bed' && f.kind !== 'desk') continue;
    const nb = rectNeighbours(g, rects.get(it.id)!);
    const reachable = nb.some((k) => reach[k]);
    if (!reachable) { violations.push({ rule: 'walkable_path', severity: 'warning', items: [it.id], message: `Path blocked to ${nameOf(fur, it).toLowerCase()}` }); walk = 'Blocked'; }
    else if (walk === 'Good' && !nb.some((k) => wide[k] || nbNearWide(g, wide, k))) walk = 'Tight';
  }

  // Metrics
  let roomCells = 0, freeCells = 0;
  for (let k = 0; k < N; k++) if (g.room[k]) { roomCells++; if (!occupied[k]) freeCells++; }
  const occOrOutside = new Uint8Array(N); for (let k = 0; k < N; k++) occOrOutside[k] = !g.room[k] || occupied[k] ? 1 : 0;
  const lfr = largestFreeRect(g, occOrOutside);
  const conflicts = violations.filter((v) => v.severity === 'error').length;
  const metrics: LayoutMetrics = {
    openFloor: roomCells ? round1((freeCells / roomCells) * 100) : 0,
    conflicts,
    walkability: walk,
    reachableStorage: storageReach.length ? round1((storageReach.filter(Boolean).length / storageReach.length) * 100) : 100,
    largestFreeRect: lfr ? { x: round2(lfr.x0), z: round2(lfr.z0), w: round2(lfr.x1 - lfr.x0), d: round2(lfr.z1 - lfr.z0), areaM2: round2((lfr.x1 - lfr.x0) * (lfr.z1 - lfr.z0)), fits: fitsLabel(lfr.x1 - lfr.x0, lfr.z1 - lfr.z0) } : null,
  };
  return { violations, metrics, blocked: violations.some((v) => BLOCKING.has(v.rule)) };
}
function nbNearWide(g: Grid, wide: Uint8Array, k: number): boolean {
  const i = k % g.nx, j = (k - i) / g.nx;
  for (let dj = -CORRIDOR_CELLS; dj <= CORRIDOR_CELLS; dj++) for (let di = -CORRIDOR_CELLS; di <= CORRIDOR_CELLS; di++) {
    const ii = i + di, jj = j + dj; if (ii >= 0 && jj >= 0 && ii < g.nx && jj < g.nz && wide[jj * g.nx + ii]) return true;
  }
  return false;
}

export function sqft(m2: number): number { return Math.round(m2 * M2_TO_SQFT); }
export { GRID };
export type { Zone };
