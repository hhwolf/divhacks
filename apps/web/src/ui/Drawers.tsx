import { useEffect, useState } from 'react';
import { useEditor } from '../store';
import { I } from './icons';
import { api } from '../lib/api';
import { snapshotCanvas } from './TopLeft';
import { postToHost } from '../lib/bridge';

const WALLS = ['#F3EDE4', '#F3DEC2', '#DCE3DA', '#5A845E', '#8FBDB0', '#C9B7E8', '#F2C7C0', '#B8CDE0', '#6B6E80', '#3E4A48'];
const FLOORS: { style: 'brick' | 'herringbone' | 'plank'; color: string; label: string }[] = [
  { style: 'plank', color: '#C9A57C', label: 'Light oak plank' }, { style: 'herringbone', color: '#BA7A57', label: 'Herringbone oak' }, { style: 'plank', color: '#8E5A3C', label: 'Walnut plank' }, { style: 'brick', color: '#B0684C', label: 'Terracotta brick' }, { style: 'brick', color: '#8A8A90', label: 'Concrete' },
];
export function Drawers() {
  const drawer = useEditor((s) => s.drawer); const set = useEditor;
  if (!drawer) return null;
  return (
    <div className="drawer-scrim" onPointerDown={(e) => { if (e.target === e.currentTarget) set.getState().setDrawer(null); }}>
      {drawer === 'menu' && <Menu />}{drawer === 'paint' && <Paint />}{drawer === 'help' && <Help />}
    </div>
  );
}
function Menu() {
  const units = useEditor((s) => s.units); const theme = useEditor((s) => s.theme); const layouts = useEditor((s) => s.layouts); const activeId = useEditor((s) => s.activeId); const room = useEditor((s) => s.room); const set = useEditor;
  const [health, setHealth] = useState<Record<string, string> | null>(null);
  useEffect(() => { api.health().then((h) => setHealth({ mode: h.mode, ...h.integrations })).catch(() => setHealth({ mode: 'offline' })); }, []);
  return (
    <div className="drawer" data-testid="drawer-menu">
      <h3>Rooms</h3>
      <div className="drawer-row"><b>{room?.name}</b><a className="btn dark small" href="/">Switch room</a></div>
      <h3>Variants</h3>
      {layouts.map((l) => <button key={l.id} className={`drawer-item ${l.id === activeId ? 'active' : ''}`} onClick={() => { void set.getState().switchLayout(l.id); set.getState().setDrawer(null); }}>{l.isCurrent && <I.lock />}{l.name}</button>)}
      <h3>Units</h3>
      <div className="seg"><button className={units === 'imperial' ? 'on' : ''} onClick={() => set.getState().setUnits('imperial')}>feet & inches</button><button className={units === 'metric' ? 'on' : ''} onClick={() => set.getState().setUnits('metric')}>metric</button></div>
      <h3>Theme</h3>
      <div className="seg">{(['stone', 'peach', 'teal'] as const).map((t) => <button key={t} className={theme === t ? 'on' : ''} onClick={() => set.getState().setTheme(t)}>{t}</button>)}</div>
      <h3>Designer</h3>
      <button className="drawer-item" onClick={() => set.getState().toggleNight()}>Toggle day / night</button>
      <button className="drawer-item" onClick={() => set.getState().toggleSound()}>Toggle sound</button>
      <button className="drawer-item" onClick={() => set.getState().setDrawer('paint')}>Paint walls &amp; floor</button>
      <button className="drawer-item" onClick={() => { const url = snapshotCanvas(); if (!url) return; postToHost('editor:snapshot', { dataUrl: url }); if (!set.getState().embedded) { const a = document.createElement('a'); a.href = url; a.download = 'room.png'; a.click(); } }}>Save snapshot</button>
      <h3>Help</h3>
      <button className="drawer-item" onClick={() => set.getState().setDrawer('help')}>Gestures & shortcuts</button>
      {health && <div className="health">API {health.mode}{Object.entries(health).filter(([k]) => k !== 'mode').map(([k, v]) => <span key={k} className={`chip ${v}`}>{k}: {v}</span>)}</div>}
    </div>
  );
}
function Paint() {
  const wallColor = useEditor((s) => s.wallColor); const floorStyle = useEditor((s) => s.floorStyle); const floorColor = useEditor((s) => s.floorColor); const set = useEditor;
  return (
    <div className="drawer paint" data-testid="drawer-paint">
      <h3>Wall materials</h3>
      <div className="swatch-row">{WALLS.map((c) => <button key={c} className={`tile swatch ${wallColor === c ? 'on' : ''}`} style={{ background: c }} aria-label={`Wall ${c}`} onClick={() => set.getState().setWallColor(c)} />)}</div>
      <h3>Floor materials</h3>
      {FLOORS.map((f) => <button key={f.label} className={`drawer-item ${floorStyle === f.style && floorColor === f.color ? 'active' : ''}`} onClick={() => set.getState().setFloorStyle(f.style, f.color)}><span className="swatch-dot" style={{ background: f.color }} />{f.label}</button>)}
      <h3>Furniture materials</h3>
      <div className="paint-note">Select an item, then use its swatches to change fabric, wood, paint, or metal color.</div>
    </div>
  );
}
function Help() {
  return (
    <div className="drawer help" data-testid="drawer-help">
      <h3>Gestures</h3>
      <ul>
        <li><b>Drag</b> an item on the floor — snaps to 10 cm and to walls</li>
        <li><b>Shift + drag</b> free move (no snapping)</li>
        <li><b>R</b> rotate 90° · <b>L</b> lock / unlock · <b>Del</b> remove · <b>⌘Z</b> undo · <b>⌘D</b> duplicate</li>
        <li><b>Scroll</b> zoom · <b>right-drag / two fingers</b> orbit in 90° steps</li>
        <li><b>Tap a tile</b> in the palette, then tap the floor to drop it</li>
        <li><b>Red</b> = collision, out of bounds or in the door swing · <b>Yellow</b> = needs 75 cm clearance</li>
        <li><b>Right-click / long-press</b> a variant tab to rename, duplicate, compare or delete</li>
      </ul>
    </div>
  );
}
