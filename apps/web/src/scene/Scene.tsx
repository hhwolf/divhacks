import { Suspense, useCallback, useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { Canvas, useThree, type ThreeEvent } from '@react-three/fiber';
import { OrthographicCamera } from '@react-three/drei';
import type { Layout, LayoutItem, RoomSkeleton } from '@arp/contracts';
import { wallInwardNormal } from '@arp/geometry';
import { useEditor, violationLevel } from '../store';
import { RoomMesh } from './Room';
import { Item } from './Furniture';
import { FloorOverlays, ZoneMarkers } from './Overlays';
import { cameraPose, fitZoom, hiddenWalls } from './camera';

function Rig({ sk }: { sk: RoomSkeleton }) {
  const orbit = useEditor((s) => s.orbit); const viewMode = useEditor((s) => s.viewMode);
  const { camera, size } = useThree();
  useEffect(() => {
    const cam = camera as THREE.OrthographicCamera; const pose = cameraPose(sk, orbit, viewMode);
    cam.position.copy(pose.position); cam.up.copy(pose.up); cam.lookAt(pose.target);
    const halfH = fitZoom(sk, size.width / size.height); const aspect = size.width / size.height;
    cam.left = -halfH * aspect; cam.right = halfH * aspect; cam.top = halfH; cam.bottom = -halfH; cam.near = 0.1; cam.far = 200; cam.zoom = cam.zoom || 1; cam.updateProjectionMatrix();
  }, [camera, sk, orbit, viewMode, size]);
  return null;
}

/** Wheel = zoom, right-drag / two-finger = orbit in 90° steps. */
function Controls() {
  const { gl, camera } = useThree(); const orbitBy = useEditor((s) => s.orbitBy);
  useEffect(() => {
    const el = gl.domElement; let rx = 0, rdown = false;
    const wheel = (e: WheelEvent) => { e.preventDefault(); const c = camera as THREE.OrthographicCamera; c.zoom = Math.min(3, Math.max(0.6, c.zoom * (e.deltaY > 0 ? 0.92 : 1.08))); c.updateProjectionMatrix(); };
    const down = (e: PointerEvent) => { if (e.button === 2) { rdown = true; rx = e.clientX; } };
    const move = (e: PointerEvent) => { if (rdown && Math.abs(e.clientX - rx) > 80) { orbitBy(e.clientX > rx ? 1 : -1); rx = e.clientX; } };
    const up = () => { rdown = false; };
    const ctx = (e: MouseEvent) => e.preventDefault();
    let touches: Touch[] = [];
    const ts = (e: TouchEvent) => { touches = Array.from(e.touches); };
    const tm = (e: TouchEvent) => { if (e.touches.length === 2 && touches.length === 2) { const dx = (e.touches[0].clientX + e.touches[1].clientX) / 2 - (touches[0].clientX + touches[1].clientX) / 2; if (Math.abs(dx) > 90) { orbitBy(dx > 0 ? 1 : -1); touches = Array.from(e.touches); } } };
    el.addEventListener('wheel', wheel, { passive: false }); el.addEventListener('pointerdown', down); window.addEventListener('pointermove', move); window.addEventListener('pointerup', up); el.addEventListener('contextmenu', ctx);
    el.addEventListener('touchstart', ts); el.addEventListener('touchmove', tm);
    return () => { el.removeEventListener('wheel', wheel); el.removeEventListener('pointerdown', down); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); el.removeEventListener('contextmenu', ctx); el.removeEventListener('touchstart', ts); el.removeEventListener('touchmove', tm); };
  }, [gl, camera, orbitBy]);
  return null;
}

/** Invisible floor plane that receives drags/placing. */
function FloorPlane({ sk }: { sk: RoomSkeleton }) {
  const s = useEditor.getState; const cx = sk.dimensions.l / 2, cz = sk.dimensions.w / 2;
  const onMove = useCallback((e: ThreeEvent<PointerEvent>) => {
    const st = s(); const p = e.point;
    if (st.dragging) st.moveItem(st.dragging, p.x, p.z, { free: e.shiftKey });
    else if (st.placing) { const id = `__placing`; void id; }
  }, [s]);
  const onDown = useCallback((e: ThreeEvent<PointerEvent>) => {
    const st = s(); if (e.button !== 0) return;
    if (st.placing) { const id = st.addItem(st.placing.furnitureId, e.point.x, e.point.z); st.cancelPlacing(); st.select(id); e.stopPropagation(); return; }
    st.select(null);
  }, [s]);
  return (
    <mesh position={[cx, 0.0, cz]} rotation={[-Math.PI / 2, 0, 0]} onPointerMove={onMove} onPointerDown={onDown} visible={false}>
      <planeGeometry args={[60, 60]} /><meshBasicMaterial />
    </mesh>
  );
}

function Items({ interactive, override }: { interactive: boolean; override?: LayoutItem[] | null }) {
  const stateItems = useEditor((s) => s.items); const items = override ?? stateItems; const furniture = useEditor((s) => s.furniture); const selectedId = useEditor((s) => s.selectedId);
  const validation = useEditor((s) => s.validation); const shake = useEditor((s) => s.shake); const bounce = useEditor((s) => s.bounce); const units = useEditor((s) => s.units);
  const st = useEditor.getState;
  const onDown = useCallback((id: string) => (e: ThreeEvent<PointerEvent>) => {
    if (e.button !== 0) return; e.stopPropagation(); const s = st(); if (s.placing) return;
    s.select(id); const it = s.items.find((i) => i.id === id); if (it && !it.locked) s.setDragging(id);
  }, [st]);
  useEffect(() => {
    const up = () => { const s = st(); if (s.dragging) { const it = s.items.find((i) => i.id === s.dragging); if (it) s.moveItem(it.id, it.x, it.z, { commit: true }); s.setDragging(null); } };
    window.addEventListener('pointerup', up); return () => window.removeEventListener('pointerup', up);
  }, [st]);
  return (
    <>
      {items.map((it) => { const f = furniture[it.furnitureId]; if (!f) return null; return (
        <Item key={it.id} item={it} f={f} selected={selectedId === it.id} level={violationLevel(validation, it.id)} shake={shake === it.id} bounce={bounce === it.id} units={units}
          onPointerDown={onDown(it.id)} onHover={(h) => st().setHover(h ? it.id : null)} interactive={interactive} />
      ); })}
    </>
  );
}
function Ghosts({ layout }: { layout: Layout | null }) {
  const furniture = useEditor((s) => s.furniture); const units = useEditor((s) => s.units);
  if (!layout) return null;
  return <>{layout.items.map((it) => { const f = furniture[it.furnitureId]; return f ? <Item key={`g-${it.id}`} item={it} f={f} selected={false} level={null} shake={false} bounce={false} ghost units={units} interactive={false} showPill={false} /> : null; })}</>;
}
function PlacingPreview() {
  const placing = useEditor((s) => s.placing); const furniture = useEditor((s) => s.furniture); const units = useEditor((s) => s.units); const room = useEditor((s) => s.room);
  if (!placing || !room) return null; const f = furniture[placing.furnitureId]; if (!f) return null;
  const it: LayoutItem = { id: '__preview', furnitureId: f.id, x: room.skeleton.dimensions.l / 2, z: room.skeleton.dimensions.w / 2, rotation: 0, locked: false };
  return <Item item={it} f={f} selected={false} level={null} shake={false} bounce={false} ghost units={units} interactive={false} showPill={false} />;
}

export function RoomScene({ interactive = true, ghostLayout = null, className, itemsOverride = null, hideOverlays = false }: { interactive?: boolean; ghostLayout?: Layout | null; className?: string; itemsOverride?: LayoutItem[] | null; hideOverlays?: boolean }) {
  const room = useEditor((s) => s.room); const orbit = useEditor((s) => s.orbit); const viewMode = useEditor((s) => s.viewMode);
  const wallColor = useEditor((s) => s.wallColor); const floorStyle = useEditor((s) => s.floorStyle); const floorColor = useEditor((s) => s.floorColor); const night = useEditor((s) => s.night); const theme = useEditor((s) => s.theme);
  const masks = useEditor((s) => s.masks); const overlays = useEditor((s) => s.overlays); const zones = useEditor((s) => s.zones);
  const glRef = useRef<THREE.WebGLRenderer | null>(null);
  const sk = room?.skeleton;
  const hidden = useMemo(() => (sk ? hiddenWalls(sk, orbit, (i) => wallInwardNormal(sk, i)) : new Set<number>()), [sk, orbit]);
  useEffect(() => { (window as unknown as { __arpGl?: () => THREE.WebGLRenderer | null }).__arpGl = () => glRef.current; }, []);
  if (!sk) return null;
  const cx = sk.dimensions.l / 2, cz = sk.dimensions.w / 2;
  return (
    <Canvas className={className} shadows dpr={[1, 2]} gl={{ preserveDrawingBuffer: true, antialias: true, alpha: true }} onCreated={({ gl }) => { glRef.current = gl; gl.toneMapping = THREE.NoToneMapping; }} style={{ touchAction: 'none' }}>
      <OrthographicCamera makeDefault position={[10, 10, 10]} zoom={1} />
      <Rig sk={sk} /><Controls />
      <ambientLight intensity={night ? 0.55 : 1.05} color={night ? '#8fa0c8' : '#fff4e6'} />
      <directionalLight position={[cx - 6, 9, cz + 4]} intensity={night ? 0.5 : 1.35} color={night ? '#9fb2e6' : '#ffe6c2'} castShadow shadow-mapSize={[2048, 2048]} shadow-bias={-0.0005}>
        <orthographicCamera attach="shadow-camera" args={[-8, 8, 8, -8, 0.5, 40]} />
      </directionalLight>
      <directionalLight position={[cx + 5, 6, cz - 6]} intensity={0.35} color="#ffd9b3" />
      <Suspense fallback={null}>
        <RoomMesh sk={sk} hidden={hidden} viewMode={viewMode} wallColor={wallColor} floorStyle={floorStyle} floorColor={floorColor} night={night} theme={theme} />
        {!hideOverlays && <FloorOverlays masks={masks} show={overlays} />}
        {!hideOverlays && <ZoneMarkers zones={zones} />}
        <Items interactive={interactive} override={itemsOverride} />
        <Ghosts layout={ghostLayout} />
        <PlacingPreview />
      </Suspense>
      {interactive && <FloorPlane sk={sk} />}
    </Canvas>
  );
}
