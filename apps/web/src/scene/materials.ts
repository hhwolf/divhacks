import * as THREE from 'three';
import type { FurnitureItem } from '@arp/contracts';

/** Physical look per Kenney material slot: roughness/metalness so wood, fabric, paint and metal read differently. */
const SLOT: Record<string, { roughness: number; metalness: number; color: string; emissive?: string; opacity?: number }> = {
  wood: { roughness: 0.62, metalness: 0.02, color: '#B08A5E' },
  woodDark: { roughness: 0.6, metalness: 0.02, color: '#5C3F2E' },
  carpet: { roughness: 0.95, metalness: 0, color: '#8A98A6' },
  carpetDarker: { roughness: 0.95, metalness: 0, color: '#5C6873' },
  carpetWhite: { roughness: 0.9, metalness: 0, color: '#F2EFEA' },
  metal: { roughness: 0.35, metalness: 0.75, color: '#A7ACB1' },
  metalMedium: { roughness: 0.4, metalness: 0.65, color: '#4F5A63' },
  metalDark: { roughness: 0.45, metalness: 0.6, color: '#3B4247' },
  metalLight: { roughness: 0.5, metalness: 0.25, color: '#ECEEEA' },
  glass: { roughness: 0.1, metalness: 0.1, color: '#BFD8D2', opacity: 0.55 },
  lamp: { roughness: 0.7, metalness: 0, color: '#F6E6B4', emissive: '#F2D488' },
  plant: { roughness: 0.85, metalness: 0, color: '#4F8A4B' },
  _defaultMat: { roughness: 0.6, metalness: 0.05, color: '#E8E4DE' },
};
const DEFAULT = { roughness: 0.7, metalness: 0.05, color: '#C9B7A0' };

/** Which slot carries the item's "main" colour — the one the side-panel swatches recolour. */
export function primarySlot(f: FurnitureItem): string {
  const slots = Object.keys(f.materials ?? {});
  return slots.find((s) => s.startsWith('carpet')) ?? slots.find((s) => s.startsWith('wood')) ?? slots[0] ?? 'wood';
}

/** Apply the item's palette + physical parameters to a cloned material. Idempotent (base colour cached on userData). */
export function styleMaterial(m: THREE.MeshStandardMaterial, f: FurnitureItem, override: string | null | undefined, tint: string | null, opacity: number): void {
  const slot = m.name || '_defaultMat';
  const spec = SLOT[slot] ?? DEFAULT;
  const wanted = f.materials?.[slot] ?? spec.color;
  const base = (m.userData.baseColor ??= new THREE.Color(wanted)) as THREE.Color;
  base.set(wanted);
  m.color.copy(base);
  if (override && slot === primarySlot(f)) m.color.copy(base).lerp(new THREE.Color(override), 0.85);
  m.roughness = spec.roughness; m.metalness = spec.metalness;
  m.emissive = new THREE.Color(tint ?? spec.emissive ?? '#000000'); m.emissiveIntensity = tint ? 0.55 : spec.emissive ? 0.35 : 0;
  const alpha = Math.min(opacity, spec.opacity ?? 1);
  m.transparent = alpha < 1; m.opacity = alpha; m.depthWrite = alpha >= 1;
  m.flatShading = true; m.vertexColors = false; m.needsUpdate = true;
}
