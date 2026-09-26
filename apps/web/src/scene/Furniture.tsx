import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useGLTF, Html } from '@react-three/drei';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import type { FurnitureItem, LayoutItem } from '@arp/contracts';
import { footprint } from '@arp/geometry';
import { aoTexture } from './textures';
import { styleMaterial } from './materials';
import { apiBase } from '../lib/api';

export function glbUrl(f: FurnitureItem): string | null {
  if (!f.glbUrl) return null;
  return f.glbUrl.startsWith('http') ? f.glbUrl : f.glbUrl.startsWith('/assets') ? f.glbUrl : `${apiBase()}${f.glbUrl}`;
}

/** GLB scaled per-axis to real dims, footprint centred at origin, base on y=0. Falls back to a colored box. */
export function FurnitureModel({ f, tint, color, opacity = 1 }: { f: FurnitureItem; tint: string | null; color?: string | null; opacity?: number }) {
  const url = glbUrl(f);
  return url ? <GlbModel url={url} f={f} tint={tint} color={color} opacity={opacity} /> : <BoxModel f={f} tint={tint} color={color} opacity={opacity} />;
}
function GlbModel({ url, f, tint, color, opacity }: { url: string; f: FurnitureItem; tint: string | null; color?: string | null; opacity: number }) {
  const { scene } = useGLTF(url);
  const obj = useMemo(() => {
    const s = scene.clone(true);
    const box = new THREE.Box3().setFromObject(s); const size = new THREE.Vector3(); box.getSize(size);
    const sx = f.dims.w / (size.x || 1), sy = f.dims.h / (size.y || 1), sz = f.dims.d / (size.z || 1);
    s.scale.set(sx, sy, sz);
    const box2 = new THREE.Box3().setFromObject(s); const c = new THREE.Vector3(); box2.getCenter(c);
    s.position.set(-c.x, -box2.min.y, -c.z);
    s.traverse((o) => { if ((o as THREE.Mesh).isMesh) { const m = o as THREE.Mesh; m.castShadow = true; m.receiveShadow = true; m.material = (Array.isArray(m.material) ? m.material[0] : m.material).clone(); } });
    return s;
  }, [scene, f.dims.w, f.dims.h, f.dims.d]);
  useEffect(() => {
    obj.traverse((o) => {
      const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined; if (!m || !(o as THREE.Mesh).isMesh) return;
      styleMaterial(m, f, color, tint, opacity);
    });
  }, [obj, f, tint, color, opacity]);
  return <primitive object={obj} />;
}
function BoxModel({ f, tint, color, opacity }: { f: FurnitureItem; tint: string | null; color?: string | null; opacity: number }) {
  return (
    <mesh position={[0, f.dims.h / 2, 0]} castShadow>
      <boxGeometry args={[f.dims.w, f.dims.h, f.dims.d]} />
      <meshStandardMaterial color={color ?? f.color ?? '#C9A27E'} roughness={0.75} emissive={tint ?? '#000'} emissiveIntensity={tint ? 0.5 : 0} transparent={opacity < 1} opacity={opacity} flatShading />
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
  useEffect(() => { t0.current = performance.now(); }, [shake, bounce]);
  useFrame(() => {
    if (!g.current) return;
    const dt = (performance.now() - t0.current) / 1000; let dx = 0, y = 0, s = 1;
    if (shake && dt < 0.4) dx = Math.sin(dt * 60) * 0.04 * (1 - dt / 0.4);
    if (bounce && dt < 0.35) { const k = dt / 0.35; y = Math.sin(k * Math.PI) * 0.08; s = 1 + Math.sin(k * Math.PI) * 0.04; }
    g.current.position.set(item.x + dx, y, item.z); g.current.scale.setScalar(s);
  });
  return (
    <group ref={g} position={[item.x, 0, item.z]}
      onPointerDown={interactive ? onPointerDown : undefined}
      onPointerOver={interactive ? (e) => { e.stopPropagation(); onHover?.(true); } : undefined}
      onPointerOut={interactive ? () => onHover?.(false) : undefined}>
      <group rotation={[0, (item.rotation * Math.PI) / 180, 0]}>
        <FurnitureModel f={f} tint={tint} color={item.color} opacity={ghost ? 0.35 : 1} />
      </group>
      {/* AO blob */}
      {!ghost && f.kind !== 'floor' && (
        <mesh position={[0, 0.006, 0]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[fx * 1.35, fz * 1.35]} /><meshBasicMaterial map={aoTexture()} transparent depthWrite={false} /></mesh>
      )}
      {/* selection: white footprint outline (reads as a diamond in iso) + corner ticks */}
      {selected && !ghost && <SelectionDiamond fx={fx} fz={fz} />}
      {selected && !ghost && showPill && (
        <Html position={[0, f.dims.h + 0.35, 0]} center zIndexRange={[5, 0]} style={{ pointerEvents: 'none' }}>
          <div className="pill">
            <span className="dot" style={{ background: item.color ?? f.colors?.[0] ?? f.color ?? '#c9a27e' }} />
            <span className="dot" style={{ background: f.colors?.[1] ?? '#5c3b2a' }} />
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
  const geo = useMemo(() => {
    const m = 0.06; const pts = [new THREE.Vector3(-fx / 2 - m, 0, -fz / 2 - m), new THREE.Vector3(fx / 2 + m, 0, -fz / 2 - m), new THREE.Vector3(fx / 2 + m, 0, fz / 2 + m), new THREE.Vector3(-fx / 2 - m, 0, fz / 2 + m), new THREE.Vector3(-fx / 2 - m, 0, -fz / 2 - m)];
    return new THREE.BufferGeometry().setFromPoints(pts);
  }, [fx, fz]);
  return (
    <group position={[0, 0.02, 0]}>
      <line><primitive object={geo} attach="geometry" /><lineBasicMaterial color="#ffffff" /></line>
      {[[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sz], k) => (
        <mesh key={k} position={[(sx * (fx / 2 + 0.06)), 0.005, (sz * (fz / 2 + 0.06))]} rotation={[-Math.PI / 2, 0, Math.PI / 4]}><planeGeometry args={[0.09, 0.09]} /><meshBasicMaterial color="#ffffff" /></mesh>
      ))}
    </group>
  );
}
