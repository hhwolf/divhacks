import type { Door, RoomSkeleton, WallSegment, Window } from '@arp/contracts';

export interface Rect { x0: number; z0: number; x1: number; z1: number }

export function wallLength(w: WallSegment): number { return Math.hypot(w.x2 - w.x1, w.z2 - w.z1); }
/** Unit direction along the wall from (x1,z1) to (x2,z2). */
export function wallDir(w: WallSegment): [number, number] { const L = wallLength(w); return [(w.x2 - w.x1) / L, (w.z2 - w.z1) / L]; }
/** Inward normal for walls listed clockwise on screen (x right, z toward viewer): rotate dir by -90°. Verified against the polygon centroid. */
export function wallInwardNormal(sk: RoomSkeleton, i: number): [number, number] {
  const w = sk.walls[i]; const [dx, dz] = wallDir(w);
  let n: [number, number] = [-dz, dx];
  const cx = sk.floorPolygon.reduce((s, p) => s + p[0], 0) / sk.floorPolygon.length;
  const cz = sk.floorPolygon.reduce((s, p) => s + p[1], 0) / sk.floorPolygon.length;
  const mx = (w.x1 + w.x2) / 2, mz = (w.z1 + w.z2) / 2;
  if ((cx - mx) * n[0] + (cz - mz) * n[1] < 0) n = [dz, -dx];
  return n;
}
/** World-space span of an opening along its wall: start and end points. */
export function openingSpan(sk: RoomSkeleton, o: { wall: number; offset: number; width: number }): { a: [number, number]; b: [number, number] } {
  const w = sk.walls[o.wall]; const [dx, dz] = wallDir(w);
  return { a: [w.x1 + dx * o.offset, w.z1 + dz * o.offset], b: [w.x1 + dx * (o.offset + o.width), w.z1 + dz * (o.offset + o.width)] };
}
/** Axis-aligned rect covering the opening span extended `depth` into the room. */
export function openingBand(sk: RoomSkeleton, o: { wall: number; offset: number; width: number }, depth: number): Rect {
  const { a, b } = openingSpan(sk, o); const n = wallInwardNormal(sk, o.wall);
  const xs = [a[0], b[0], a[0] + n[0] * depth, b[0] + n[0] * depth];
  const zs = [a[1], b[1], a[1] + n[1] * depth, b[1] + n[1] * depth];
  return { x0: Math.min(...xs), z0: Math.min(...zs), x1: Math.max(...xs), z1: Math.max(...zs) };
}
export function doorClearanceRect(sk: RoomSkeleton, d: Door, depth: number): Rect { return openingBand(sk, d, depth); }
/** Hinge point and swing radius for an inward-swinging door (quarter disc keep-clear). */
export function doorHinge(sk: RoomSkeleton, d: Door): { hinge: [number, number]; radius: number } {
  const { a, b } = openingSpan(sk, d);
  return { hinge: d.hinge === 'left' ? a : b, radius: d.width };
}
export function windowBand(sk: RoomSkeleton, w: Window, depth: number): Rect { return openingBand(sk, w, depth); }
export function roomBounds(sk: RoomSkeleton): Rect {
  const xs = sk.floorPolygon.map((p) => p[0]), zs = sk.floorPolygon.map((p) => p[1]);
  return { x0: Math.min(...xs), z0: Math.min(...zs), x1: Math.max(...xs), z1: Math.max(...zs) };
}
export function pointInPolygon(px: number, pz: number, poly: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, zi] = poly[i], [xj, zj] = poly[j];
    if (zi > pz !== zj > pz && px < ((xj - xi) * (pz - zi)) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}
/** Which wall a compass word refers to, by wall midpoint. north = min z, south = max z, west = min x, east = max x. */
export function wallByCompass(sk: RoomSkeleton, word: 'north' | 'south' | 'east' | 'west'): number {
  let best = 0, bestV = word === 'north' || word === 'west' ? Infinity : -Infinity;
  sk.walls.forEach((w, i) => {
    const v = word === 'north' || word === 'south' ? (w.z1 + w.z2) / 2 : (w.x1 + w.x2) / 2;
    const better = word === 'north' || word === 'west' ? v < bestV : v > bestV;
    if (better) { bestV = v; best = i; }
  });
  return best;
}
