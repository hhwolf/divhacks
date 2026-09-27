import { useMemo } from 'react';
import * as THREE from 'three';
import type { RoomSkeleton } from '@arp/contracts';
import { doorHinge, openingSpan, roomBounds, wallDir, wallInwardNormal, wallLength } from '@arp/geometry';
import { floorTexture } from './textures';
import type { FloorStyle, ViewMode } from '../store';

const SLAB = 0.5, WALL_T = 0.14, TRIM = 0.12;
export const COLORS = { slab: '#8A4E37', slabTeal: '#5B4339', trim: '#EFE8DE', frame: '#F4EEE6', pane: '#E8BE82', paneNight: '#F3D28A', door: '#C99A6B' };

function roundedPolygonShape(poly: [number, number][], grow: number, radius: number): THREE.Shape {
  // grow polygon outward (assumes convex-ish rectangle-like rooms), then round corners
  const cx = poly.reduce((s, p) => s + p[0], 0) / poly.length, cz = poly.reduce((s, p) => s + p[1], 0) / poly.length;
  const pts = poly.map(([x, z]) => [x + Math.sign(x - cx) * grow, z + Math.sign(z - cz) * grow] as [number, number]);
  const sh = new THREE.Shape(); const n = pts.length;
  for (let i = 0; i < n; i++) {
    const p = pts[i], prev = pts[(i - 1 + n) % n], next = pts[(i + 1) % n];
    const d1 = [prev[0] - p[0], prev[1] - p[1]], d2 = [next[0] - p[0], next[1] - p[1]];
    const l1 = Math.hypot(...d1), l2 = Math.hypot(...d2); const r = Math.min(radius, l1 / 2, l2 / 2);
    const a: [number, number] = [p[0] + (d1[0] / l1) * r, p[1] + (d1[1] / l1) * r], b: [number, number] = [p[0] + (d2[0] / l2) * r, p[1] + (d2[1] / l2) * r];
    if (i === 0) sh.moveTo(a[0], a[1]); else sh.lineTo(a[0], a[1]);
    sh.quadraticCurveTo(p[0], p[1], b[0], b[1]);
  }
  sh.closePath(); return sh;
}

export function RoomMesh({ sk, hidden, viewMode, wallColor, floorStyle, floorColor, night, theme }: {
  sk: RoomSkeleton; hidden: Set<number>; viewMode: ViewMode; wallColor: string; floorStyle: FloorStyle; floorColor: string; night: boolean; theme: 'peach' | 'teal';
}) {
  const b = roomBounds(sk);
  const slabGeo = useMemo(() => {
    const shape = roundedPolygonShape(sk.floorPolygon, WALL_T + 0.08, 0.34);
    const g = new THREE.ExtrudeGeometry(shape, { depth: SLAB, bevelEnabled: false });
    g.rotateX(Math.PI / 2); g.translate(0, 0.0, 0); return g;
  }, [sk]);
  const floorGeo = useMemo(() => { const s = new THREE.Shape(sk.floorPolygon.map(([x, z]) => new THREE.Vector2(x, z))); const g = new THREE.ShapeGeometry(s); g.rotateX(Math.PI / 2); return g; }, [sk]);
  const floorTex = useMemo(() => floorTexture(floorStyle, floorColor), [floorStyle, floorColor]);
  const wallH = viewMode === 'half' ? 1.1 : sk.dimensions.h;
  return (
    <group>
      {/* slab (dark brown edge) */}
      <mesh geometry={slabGeo} position={[0, 0.001, 0]} receiveShadow><meshStandardMaterial color={theme === 'teal' ? COLORS.slabTeal : COLORS.slab} roughness={0.9} /></mesh>
      {/* floor */}
      <mesh geometry={floorGeo} position={[0, 0.012, 0]} receiveShadow>
        <meshStandardMaterial map={floorTex} color={night ? '#9a9aa8' : '#ffffff'} roughness={0.95} side={THREE.DoubleSide} />
      </mesh>
      {/* faint grid in plan view */}
      {viewMode === 'plan' && <gridHelper args={[Math.max(b.x1 - b.x0, b.z1 - b.z0) * 2, Math.round(Math.max(b.x1 - b.x0, b.z1 - b.z0) * 2 / 0.5), '#7a4a33', '#7a4a33']} position={[(b.x0 + b.x1) / 2, 0.02, (b.z0 + b.z1) / 2]} />}
      {viewMode !== 'plan' && sk.walls.map((_, i) => (
        <Wall key={i} sk={sk} i={i} hidden={hidden.has(i)} height={wallH} color={wallColor} night={night} theme={theme} />
      ))}
      {/* Door markers on the floor for doors on hidden walls (or in plan view) */}
      {sk.doors.map((d, i) => (hidden.has(d.wall) || viewMode === 'plan') && <DoorFloorMarker key={i} sk={sk} door={d} />)}
    </group>
  );
}

function Wall({ sk, i, hidden, height, color, night, theme }: { sk: RoomSkeleton; i: number; hidden: boolean; height: number; color: string; night: boolean; theme: 'peach' | 'teal' }) {
  const w = sk.walls[i]; const L = wallLength(w); const [dx, dz] = wallDir(w); const n = wallInwardNormal(sk, i);
  const angle = Math.atan2(-dz, dx); // rotation about y so local +x runs along the wall
  const geo = useMemo(() => {
    const shape = new THREE.Shape(); shape.moveTo(0, 0); shape.lineTo(L, 0); shape.lineTo(L, height); shape.lineTo(0, height); shape.closePath();
    for (const win of sk.windows) if (win.wall === i && win.sillHeight < height) {
      const top = Math.min(height, win.sillHeight + win.height); const h = new THREE.Path();
      h.moveTo(win.offset, win.sillHeight); h.lineTo(win.offset + win.width, win.sillHeight); h.lineTo(win.offset + win.width, top); h.lineTo(win.offset, top); h.closePath(); shape.holes.push(h);
    }
    for (const d of sk.doors) if (d.wall === i) {
      const top = Math.min(height, d.height ?? 2.0); const h = new THREE.Path();
      h.moveTo(d.offset, 0); h.lineTo(d.offset + d.width, 0); h.lineTo(d.offset + d.width, top); h.lineTo(d.offset, top); h.closePath(); shape.holes.push(h);
    }
    return new THREE.ExtrudeGeometry(shape, { depth: WALL_T, bevelEnabled: false });
  }, [sk, i, L, height]);
  if (hidden) return null;
  // Place: local x along wall, local y up, extrude along local +z which we orient outward (−n)
  const pos: [number, number, number] = [w.x1, 0, w.z1];
  const depthScale = wallDepthScale(dx, dz, n);
  return (
    <group position={pos} rotation={[0, angle, 0]}>
      {/* Flip depth only when local +z points inward. Rotating the wall 180° would mirror opening offsets. */}
      <group scale={depthScale}>
        <mesh geometry={geo} castShadow receiveShadow><meshStandardMaterial color={night ? shadeHex(color, -0.25) : color} roughness={0.95} /></mesh>
        {/* baseboard trim */}
        <mesh position={[L / 2, TRIM / 2, -0.012]}><boxGeometry args={[L, TRIM, 0.024]} /><meshStandardMaterial color={COLORS.trim} /></mesh>
        {/* top trim */}
        <mesh position={[L / 2, height - 0.03, WALL_T / 2]}><boxGeometry args={[L + 0.02, 0.06, WALL_T + 0.02]} /><meshStandardMaterial color={COLORS.trim} /></mesh>
        {sk.windows.filter((x) => x.wall === i && x.sillHeight < height).map((win, k) => <WindowFrame key={k} offset={win.offset} width={win.width} sill={win.sillHeight} h={Math.min(height - win.sillHeight, win.height)} night={night} theme={theme} />)}
        {sk.doors.filter((d) => d.wall === i).map((d, k) => <DoorFrame key={k} offset={d.offset} width={d.width} h={Math.min(height, d.height ?? 2.0)} hinge={d.hinge} />)}
      </group>
    </group>
  );
}
export function wallOutwardFlip(dx: number, dz: number, n: [number, number]): boolean {
  // after rotation by angle=atan2(-dz,dx), local +z maps to world (−dz·?…). Compute world dir of local +z: rotate (0,0,1) by angle about y → (sin a, 0, cos a)
  const a = Math.atan2(-dz, dx); const wx = Math.sin(a), wz = Math.cos(a);
  return wx * n[0] + wz * n[1] > 0; // local +z points inward → flip so the extrusion goes outward
}
export function wallDepthScale(dx: number, dz: number, n: [number, number]): [number, number, number] {
  return [1, 1, wallOutwardFlip(dx, dz, n) ? -1 : 1];
}
export function wallLocalPointToWorld(sk: RoomSkeleton, i: number, x: number, z = 0): [number, number] {
  const w = sk.walls[i]; const [dx, dz] = wallDir(w); const n = wallInwardNormal(sk, i);
  const localZ = z * wallDepthScale(dx, dz, n)[2];
  return [w.x1 + x * dx - localZ * dz, w.z1 + x * dz + localZ * dx];
}
function shadeHex(hex: string, amt: number): string { const c = new THREE.Color(hex); const h = { h: 0, s: 0, l: 0 }; c.getHSL(h); c.setHSL(h.h, h.s, Math.max(0, Math.min(1, h.l + amt))); return `#${c.getHexString()}`; }

function WindowFrame({ offset, width, sill, h, night, theme }: { offset: number; width: number; sill: number; h: number; night: boolean; theme: 'peach' | 'teal' }) {
  const t = 0.05; const cols = Math.max(1, Math.round(width / 0.4)), rows = Math.max(1, Math.round(h / 0.45));
  const pane = night ? COLORS.paneNight : theme === 'teal' ? '#CFE8E2' : COLORS.pane;
  return (
    <group position={[offset, sill, 0]}>
      <mesh position={[width / 2, h / 2, WALL_T / 2]}><planeGeometry args={[width, h]} /><meshStandardMaterial color={pane} transparent opacity={night ? 0.95 : 0.72} emissive={pane} emissiveIntensity={night ? 0.9 : 0.25} side={THREE.DoubleSide} /></mesh>
      {/* outer frame */}
      {[[width / 2, t / 2, width + t, t], [width / 2, h - t / 2, width + t, t]].map(([x, y, w, hh], k) => <mesh key={`h${k}`} position={[x, y, WALL_T / 2]}><boxGeometry args={[w, hh, WALL_T + 0.04]} /><meshStandardMaterial color={COLORS.frame} /></mesh>)}
      {[[t / 2, h / 2], [width - t / 2, h / 2]].map(([x, y], k) => <mesh key={`v${k}`} position={[x, y, WALL_T / 2]}><boxGeometry args={[t, h, WALL_T + 0.04]} /><meshStandardMaterial color={COLORS.frame} /></mesh>)}
      {/* mullions */}
      {Array.from({ length: cols - 1 }, (_, k) => <mesh key={`m${k}`} position={[((k + 1) * width) / cols, h / 2, WALL_T / 2]}><boxGeometry args={[0.03, h, WALL_T + 0.02]} /><meshStandardMaterial color={COLORS.frame} /></mesh>)}
      {Array.from({ length: rows - 1 }, (_, k) => <mesh key={`r${k}`} position={[width / 2, ((k + 1) * h) / rows, WALL_T / 2]}><boxGeometry args={[width, 0.03, WALL_T + 0.02]} /><meshStandardMaterial color={COLORS.frame} /></mesh>)}
    </group>
  );
}
function DoorFrame({ offset, width, h, hinge }: { offset: number; width: number; h: number; hinge: 'left' | 'right' }) {
  const t = 0.06;
  return (
    <group position={[offset, 0, 0]}>
      <mesh position={[t / 2, h / 2, WALL_T / 2]}><boxGeometry args={[t, h, WALL_T + 0.04]} /><meshStandardMaterial color={COLORS.frame} /></mesh>
      <mesh position={[width - t / 2, h / 2, WALL_T / 2]}><boxGeometry args={[t, h, WALL_T + 0.04]} /><meshStandardMaterial color={COLORS.frame} /></mesh>
      <mesh position={[width / 2, h - t / 2, WALL_T / 2]}><boxGeometry args={[width + t, t, WALL_T + 0.04]} /><meshStandardMaterial color={COLORS.frame} /></mesh>
      {/* door leaf, open ~80° into the room (toward local −z = inward after our flip) */}
      <group position={[hinge === 'left' ? t : width - t, 0, 0]} rotation={[0, (hinge === 'left' ? -1 : 1) * (Math.PI * 0.44), 0]}>
        <mesh position={[(hinge === 'left' ? 1 : -1) * (width - 2 * t) / 2, (h - t) / 2, 0]}><boxGeometry args={[width - 2 * t, h - t, 0.04]} /><meshStandardMaterial color={COLORS.door} /></mesh>
      </group>
    </group>
  );
}
function DoorFloorMarker({ sk, door }: { sk: RoomSkeleton; door: RoomSkeleton['doors'][number] }) {
  const { a, b } = openingSpan(sk, door); const { hinge, radius } = doorHinge(sk, door); const n = wallInwardNormal(sk, door.wall);
  const pts = useMemo(() => {
    const toHinge = [hinge[0] === a[0] && hinge[1] === a[1] ? b : a];
    const other = toHinge[0]; const start = Math.atan2(other[1] - hinge[1], other[0] - hinge[0]);
    const inward = Math.atan2(n[1], n[0]); let sweep = inward - start; while (sweep > Math.PI) sweep -= 2 * Math.PI; while (sweep < -Math.PI) sweep += 2 * Math.PI;
    const arr: THREE.Vector3[] = [new THREE.Vector3(hinge[0], 0.03, hinge[1])];
    for (let k = 0; k <= 16; k++) { const t = start + (sweep * k) / 16 * (Math.abs(sweep) > 1e-6 ? 1 : 0); arr.push(new THREE.Vector3(hinge[0] + Math.cos(t) * radius, 0.03, hinge[1] + Math.sin(t) * radius)); }
    arr.push(new THREE.Vector3(hinge[0], 0.03, hinge[1]));
    return arr;
  }, [a, b, hinge, radius, n]);
  const geo = useMemo(() => new THREE.BufferGeometry().setFromPoints(pts), [pts]);
  return (
    <group>
      <line><primitive object={geo} attach="geometry" /><lineBasicMaterial color="#F7F2EA" transparent opacity={0.8} /></line>
      {/* the leaf itself as a thin slab, lying open */}
      <mesh position={[(a[0] + b[0]) / 2 + n[0] * 0.02, 0.02, (a[1] + b[1]) / 2 + n[1] * 0.02]} rotation={[-Math.PI / 2, 0, Math.atan2(-(b[1] - a[1]), b[0] - a[0])]}>
        <planeGeometry args={[door.width, 0.06]} /><meshBasicMaterial color={COLORS.door} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}
