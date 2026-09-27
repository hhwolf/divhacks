import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useGLTF, Html } from '@react-three/drei';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import type { FurnitureItem, LayoutItem } from '@arp/contracts';
import { footprint } from '@arp/geometry';
import { aoTexture } from './textures';
import { makeMaterial, modelKey, recolorable, specFor, swatchesFor, tone, type StyleId } from './materials';
import { apiBase } from '../lib/api';
import { ENTRANCE_STAGGER, useEditor } from '../store';

const ENTER_MS = 450;
/** Rugs/mats are ~1 cm thick but the floor surface sits at y = 0.012 (Room.tsx); lift them just above it or they render under the boards. */
const FLOOR_LIFT = 0.006;
const easeOutBack = (t: number) => { const c = 1.70158; return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2; };

/** Flat floor decals (AO blobs, selection outline, overlays) live on this layer so ContactShadows ignores them. */
export const DECAL_LAYER = 1;

export function glbUrl(f: FurnitureItem): string | null {
  if (!f.glbUrl) return null;
  return f.glbUrl.startsWith('http') ? f.glbUrl : f.glbUrl.startsWith('/assets') ? f.glbUrl : `${apiBase()}${f.glbUrl}`;
}

/** GLB scaled per-axis to real dims, footprint centred at origin, base on y=0. Falls back to a colored box. */
export function FurnitureModel({ f, tint, color, opacity = 1, style }: { f: FurnitureItem; tint: string | null; color?: string | null; opacity?: number; style?: StyleId | null }) {
  const active = useEditor((s) => s.style); const st = style === undefined ? active : style;
  const url = glbUrl(f);
  return url ? <GlbModel url={url} f={f} tint={tint} color={color} opacity={opacity} style={st} /> : <BoxModel f={f} tint={tint} color={color} opacity={opacity} />;
}
function GlbModel({ url, f, tint, color, opacity, style }: { url: string; f: FurnitureItem; tint: string | null; color?: string | null; opacity: number; style: StyleId | null }) {
  const { scene } = useGLTF(url);
  const obj = useMemo(() => {
    const s = scene.clone(true);
    const box = new THREE.Box3().setFromObject(s); const size = new THREE.Vector3(); box.getSize(size);
    const sx = f.dims.w / (size.x || 1), sy = f.dims.h / (size.y || 1), sz = f.dims.d / (size.z || 1);
    s.scale.set(sx, sy, sz);
    const box2 = new THREE.Box3().setFromObject(s); const c = new THREE.Vector3(); box2.getCenter(c);
    s.position.set(-c.x, -box2.min.y, -c.z);
    // Kenney models share one flat palette; swap each material slot for this model's grounded finish (see materials.ts).
    const key = modelKey(url); const made = new Map<string, THREE.MeshStandardMaterial>();
    s.traverse((o) => {
      if (!(o as THREE.Mesh).isMesh) return; const m = o as THREE.Mesh; m.castShadow = true; m.receiveShadow = true;
      const name = (Array.isArray(m.material) ? m.material[0] : m.material).name;
      let mat = made.get(name); if (!mat) { mat = makeMaterial(specFor(key, name, style), name); made.set(name, mat); }
      m.material = mat;
    });
    return s;
  }, [scene, url, f.dims.w, f.dims.h, f.dims.d, style]);
  useEffect(() => {
    const seen = new Set<THREE.Material>();
    obj.traverse((o) => {
      const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined; if (!m || !(o as THREE.Mesh).isMesh || seen.has(m)) return; seen.add(m);
      if (tint) { m.emissive.set(tint); m.emissiveIntensity = 0.55; } else { m.emissive.copy(m.userData.baseEmissive ?? new THREE.Color(0)); m.emissiveIntensity = m.userData.baseEmissiveIntensity ?? 0; }
      const transparent = opacity < 1; if (m.transparent !== transparent) { m.transparent = transparent; m.needsUpdate = true; }
      m.opacity = opacity; m.depthWrite = !transparent;
      const base = (m.userData.baseColor ??= m.color.clone()) as THREE.Color;
      if (color && recolorable(m.userData.surface)) m.color.copy(base).lerp(new THREE.Color(tone(color)), 0.8); else m.color.copy(base);
    });
  }, [obj, tint, color, opacity]);
  return <primitive object={obj} />;
}
function BoxModel({ f, tint, color, opacity }: { f: FurnitureItem; tint: string | null; color?: string | null; opacity: number }) {
  return (
    <mesh position={[0, f.dims.h / 2, 0]} castShadow>
      <boxGeometry args={[f.dims.w, f.dims.h, f.dims.d]} />
      <meshStandardMaterial color={tone(color ?? f.color ?? '#B7AD9E')} roughness={0.8} emissive={tint ?? '#000'} emissiveIntensity={tint ? 0.5 : 0} transparent={opacity < 1} opacity={opacity} flatShading />
    </mesh>
  );
}

export interface ItemProps {
  item: LayoutItem; f: FurnitureItem; selected: boolean; level: 'error' | 'warning' | null; shake: boolean; bounce: boolean; ghost?: boolean; units: 'imperial' | 'metric';
  onPointerDown?: (e: ThreeEvent<PointerEvent>) => void; onHover?: (h: boolean) => void; showPill?: boolean; interactive?: boolean;
}
export function Item({ item, f, selected, level, shake, bounce, ghost, onPointerDown, onHover, showPill = true, interactive = true }: ItemProps) {
  const g = useRef<THREE.Group>(null!);
  const t0 = useRef(0);
  const { fx, fz } = footprint(f.dims, item.rotation);
  const tint = ghost ? null : level === 'error' ? '#ff2d2d' : level === 'warning' ? '#ffb020' : selected ? '#3a2a20' : null;
  const sw = swatchesFor(modelKey(f.glbUrl));
  const enterIdx = useEditor((s) => (ghost ? undefined : s.entrance?.order[item.id]));
  const lift = f.kind === 'floor' ? FLOOR_LIFT : 0;
  useEffect(() => { t0.current = performance.now(); }, [shake, bounce]);
  useFrame(() => {
    if (!g.current) return;
    const dt = (performance.now() - t0.current) / 1000; let dx = 0, y = 0, s = 1;
    if (shake && dt < 0.4) dx = Math.sin(dt * 60) * 0.04 * (1 - dt / 0.4);
    if (bounce && dt < 0.35) { const k = dt / 0.35; y = Math.sin(k * Math.PI) * 0.08; s = 1 + Math.sin(k * Math.PI) * 0.04; }
    const ent = enterIdx === undefined ? null : useEditor.getState().entrance;
    if (ent && enterIdx !== undefined) {
      // furnish drop-in: hidden until its turn, then falls from ~1.4 m and settles with a small overshoot
      const k = (performance.now() - ent.at - enterIdx * ENTRANCE_STAGGER) / ENTER_MS;
      if (k < 1) { const c = Math.max(0, k); y += (1 - c) ** 2 * 1.4; s *= c <= 0 ? 0.001 : 0.55 + 0.45 * easeOutBack(c); }
    }
    g.current.position.set(item.x + dx, y + lift, item.z); g.current.scale.setScalar(s);
  });
  return (
    <group ref={g} position={[item.x, lift, item.z]}
      onPointerDown={interactive ? onPointerDown : undefined}
      onPointerOver={interactive ? (e) => { e.stopPropagation(); onHover?.(true); } : undefined}
      onPointerOut={interactive ? () => onHover?.(false) : undefined}>
      <group rotation={[0, (item.rotation * Math.PI) / 180, 0]}>
        <FurnitureModel f={f} tint={tint} color={item.color} opacity={ghost ? 0.35 : 1} />
      </group>
      {/* AO blob */}
      {!ghost && f.kind !== 'floor' && (
        <mesh position={[0, 0.006, 0]} rotation={[-Math.PI / 2, 0, 0]} layers={DECAL_LAYER}><planeGeometry args={[fx * 1.25, fz * 1.25]} /><meshBasicMaterial map={aoTexture()} transparent depthWrite={false} /></mesh>
      )}
      {/* selection: white footprint outline (reads as a diamond in iso) + corner ticks */}
      {selected && !ghost && <SelectionDiamond fx={fx} fz={fz} />}
      {selected && !ghost && showPill && (
        <Html position={[0, f.dims.h + 0.35, 0]} center zIndexRange={[5, 0]} style={{ pointerEvents: 'none' }}>
          <div className="pill">
            <span className="dot" style={{ background: item.color ?? sw?.[0] ?? f.colors?.[0] ?? f.color ?? '#c9a27e' }} />
            <span className="dot" style={{ background: sw?.[1] ?? f.colors?.[1] ?? '#5c3b2a' }} />
            <span className="pill-name">{f.name}{item.locked ? ' 🔒' : ''}</span>
          </div>
        </Html>
      )}
      {item.locked && !ghost && (
        <Html position={[fx / 2 - 0.1, f.dims.h + 0.08, fz / 2 - 0.1]} center zIndexRange={[4, 0]} style={{ pointerEvents: 'none' }}><div className="lock-badge" title="Locked">🔒</div></Html>
      )}
    </group>
  );
}
function SelectionDiamond({ fx, fz }: { fx: number; fz: number }) {
  const outline = useMemo(() => {
    const m = 0.06; const pts = [new THREE.Vector3(-fx / 2 - m, 0, -fz / 2 - m), new THREE.Vector3(fx / 2 + m, 0, -fz / 2 - m), new THREE.Vector3(fx / 2 + m, 0, fz / 2 + m), new THREE.Vector3(-fx / 2 - m, 0, fz / 2 + m), new THREE.Vector3(-fx / 2 - m, 0, -fz / 2 - m)];
    const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: '#ffffff' })); l.layers.set(DECAL_LAYER); return l;
  }, [fx, fz]);
  return (
    <group position={[0, 0.02, 0]}>
      <primitive object={outline} />
      {[[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sz], k) => (
        <mesh key={k} layers={DECAL_LAYER} position={[(sx * (fx / 2 + 0.06)), 0.005, (sz * (fz / 2 + 0.06))]} rotation={[-Math.PI / 2, 0, Math.PI / 4]}><planeGeometry args={[0.09, 0.09]} /><meshBasicMaterial color="#ffffff" /></mesh>
      ))}
    </group>
  );
}
