import { Suspense, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Canvas } from '@react-three/fiber';
import { Environment, Lightformer, OrthographicCamera } from '@react-three/drei';
import * as THREE from 'three';
import type { FurnitureItem } from '@arp/contracts';
import { FurnitureModel } from '../scene/Furniture';
/** 256×256 transparent render of one catalog item for the palette tiles. */
export function ThumbPage() {
  const { furnitureId } = useParams(); const [f, setF] = useState<FurnitureItem | null>(null);
  useEffect(() => { fetch('/assets/furniture/manifest.json').then((r) => r.json()).then((m) => setF(m.items.find((x: FurnitureItem) => x.id === furnitureId) ?? null)); }, [furnitureId]);
  if (!f) return null;
  // frame by the iso-projected extent: vertical ≈ h·cos35° + (w+d)/2·sin35°, horizontal ≈ (w+d)·cos45°
  const d = Math.max(0.5 * (f.dims.h * 0.82 + ((f.dims.w + f.dims.d) / 2) * 0.57), ((f.dims.w + f.dims.d) * 0.707) / 2) * 1.12;
  return (
    <div style={{ width: 256, height: 256 }} data-ready="1">
      <Canvas gl={{ alpha: true, preserveDrawingBuffer: true, antialias: true }} style={{ background: 'transparent' }} onCreated={({ gl }) => { gl.toneMapping = THREE.NeutralToneMapping; }}>
        <OrthographicCamera makeDefault position={[6, 5, 6]} zoom={1} left={-d} right={d} top={d * 1.15} bottom={-d * 0.85} near={0.1} far={100} onUpdate={(c) => c.lookAt(0, f.dims.h / 2, 0)} />
        {/* same daylight language as the room: sky/ground bounce + a soft key from the upper left */}
        <hemisphereLight args={['#dfe8f0', '#b9a58e', 1.2]} /><directionalLight position={[-3, 6, 4]} intensity={2.4} color="#fff0da" /><directionalLight position={[4, 3, 5]} intensity={0.5} color="#f3eee8" />
        <Environment resolution={32} frames={1} environmentIntensity={0.35}><Lightformer form="rect" intensity={2} position={[0, 5, -6]} scale={[10, 5, 1]} /></Environment>
        <Suspense fallback={null}><group rotation={[0, Math.PI * 0.15, 0]}><FurnitureModel f={f} tint={null} /></group></Suspense>
      </Canvas>
    </div>
  );
}
