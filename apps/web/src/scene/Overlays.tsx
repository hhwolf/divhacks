import { useMemo } from 'react';
import * as THREE from 'three';
import type { Zone } from '@arp/contracts';
import { GRID, type OverlayMasks } from '@arp/geometry';
import { maskTexture } from './textures';

export function FloorOverlays({ masks, show }: { masks: OverlayMasks | null; show: { walkable: boolean; keepClear: boolean; lowClearance: boolean } }) {
  const tex = useMemo(() => {
    if (!masks || (!show.walkable && !show.keepClear && !show.lowClearance)) return null;
    const { grid } = masks; const layers: { mask: Uint8Array; rgba: [number, number, number, number] }[] = [];
    if (show.walkable) layers.push({ mask: masks.walkable, rgba: [92, 183, 120, 120] });
    if (show.lowClearance) layers.push({ mask: masks.lowClearance, rgba: [255, 190, 40, 150] });
    if (show.keepClear) layers.push({ mask: masks.keepClear, rgba: [235, 70, 60, 165] });
    return maskTexture(grid.nx, grid.nz, layers);
  }, [masks, show.walkable, show.keepClear, show.lowClearance]);
  if (!tex || !masks) return null;
  const { grid } = masks; const w = grid.nx * GRID, d = grid.nz * GRID;
  return (
    <mesh position={[grid.ox + w / 2, 0.018, grid.oz + d / 2]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[w, d]} />
      <meshBasicMaterial map={tex} transparent depthWrite={false} side={THREE.DoubleSide} />
    </mesh>
  );
}
export function ZoneMarkers({ zones }: { zones: Zone[] }) {
  return (
    <group>
      {zones.map((z, k) => (
        <group key={k} position={[z.x + z.w / 2, 0.016, z.z + z.d / 2]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[z.w, z.d]} /><meshBasicMaterial color="#7FA8C9" transparent opacity={0.28} depthWrite={false} /></mesh>
          <lineSegments rotation={[-Math.PI / 2, 0, 0]}><edgesGeometry args={[new THREE.PlaneGeometry(z.w, z.d)]} /><lineBasicMaterial color="#F7F2EA" /></lineSegments>
        </group>
      ))}
    </group>
  );
}
