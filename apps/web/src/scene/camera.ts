import * as THREE from 'three';
import type { RoomSkeleton } from '@arp/contracts';
import { roomBounds } from '@arp/geometry';

export const ELEVATION_DEG = 35;
/** Horizontal unit direction from room center toward the camera for orbit step k (0 = +x,+z quadrant). */
export function orbitDir(k: number): [number, number] {
  const a = Math.PI / 4 + (k * Math.PI) / 2; return [Math.cos(a), Math.sin(a)];
}
export function cameraPose(sk: RoomSkeleton, orbit: number, viewMode: 'cutaway' | 'half' | 'plan') {
  const b = roomBounds(sk); const cx = (b.x0 + b.x1) / 2, cz = (b.z0 + b.z1) / 2;
  const target = new THREE.Vector3(cx, viewMode === 'plan' ? 0 : 0.7, cz);
  const D = 30;
  if (viewMode === 'plan') {
    // straight down; "up" on screen is north (−z) rotated by the orbit step so plan view follows the same 90° steps
    const a = (orbit * Math.PI) / 2; const up = new THREE.Vector3(-Math.sin(a), 0, -Math.cos(a));
    return { position: new THREE.Vector3(cx + up.x * 0.001, D, cz + up.z * 0.001), target, up };
  }
  const [dx, dz] = orbitDir(orbit); const el = (ELEVATION_DEG * Math.PI) / 180;
  const position = new THREE.Vector3(cx + dx * D * Math.cos(el), D * Math.sin(el), cz + dz * D * Math.cos(el));
  return { position, target, up: new THREE.Vector3(0, 1, 0) };
}
/** Which wall indices face away from the camera (i.e. are nearest to it) and should be hidden. */
export function hiddenWalls(sk: RoomSkeleton, orbit: number, inward: (i: number) => [number, number]): Set<number> {
  const [dx, dz] = orbitDir(orbit); const out = new Set<number>();
  sk.walls.forEach((_, i) => { const n = inward(i); if (n[0] * dx + n[1] * dz < -0.3) out.add(i); });
  return out;
}
/** Ortho frustum half-height so the room fits with margins. */
export function fitZoom(sk: RoomSkeleton, aspect: number): number {
  const b = roomBounds(sk); const diag = Math.hypot(b.x1 - b.x0, b.z1 - b.z0);
  const halfH = Math.max(diag * 0.52, (sk.dimensions.h + diag * 0.3) * 0.78);
  const fitted = aspect < 1.4 ? halfH * 1.25 : halfH;
  // Portrait: the isometric footprint is about `diag` wide, so the horizontal half-extent must cover it too.
  return Math.max(fitted, (diag * 0.62) / aspect);
}
