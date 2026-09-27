import type { MouseEvent } from 'react';
import { useEditor } from '../store';
import { postToHost } from '../lib/bridge';

const WALLS = ['#F3EDE4', '#EDE6DA', '#E4E2DC', '#DCE3DA', '#C9D2C4', '#D8D2C8', '#B8C2C8', '#8E9A8C', '#6B6E72', '#3E4A48'];
const FLOORS: { style: 'brick' | 'herringbone' | 'plank'; color: string; label: string }[] = [
  { style: 'plank', color: '#C9A57C', label: 'Light oak plank' }, { style: 'herringbone', color: '#BA7A57', label: 'Herringbone oak' }, { style: 'plank', color: '#8E5A3C', label: 'Walnut plank' }, { style: 'brick', color: '#B0684C', label: 'Terracotta tile' }, { style: 'brick', color: '#8A8A90', label: 'Concrete' },
];
export function Drawers() {
  const drawer = useEditor((s) => s.drawer); const set = useEditor;
  if (!drawer) return null;
  return (
    <div className="drawer-scrim" onPointerDown={(e) => { if (e.target === e.currentTarget) set.getState().setDrawer(null); }}>
      {drawer === 'menu' && <Menu />}{drawer === 'paint' && <Paint />}
    </div>
  );
}
function Menu() {
  const room = useEditor((s) => s.room); const embedded = useEditor((s) => s.embedded);
  // Inside the phone app, "Switch room" returns to the app's room list; standalone it goes to the editor's home.
  const switchRoom = (e: MouseEvent) => { if (!embedded) return; e.preventDefault(); useEditor.getState().setDrawer(null); postToHost('editor:navigate', { route: '/' }); };
  return (
    <div className="drawer menu-compact" data-testid="drawer-menu">
      <div className="drawer-row"><b className="drawer-title">{room?.name}</b><a className="btn ghost small" href="/" onClick={switchRoom}>Switch room</a></div>
    </div>
  );
}
function Paint() {
  const wallColor = useEditor((s) => s.wallColor); const floorStyle = useEditor((s) => s.floorStyle); const floorColor = useEditor((s) => s.floorColor); const set = useEditor;
  return (
    <div className="drawer paint" data-testid="drawer-paint">
      <h3>Walls</h3>
      <div className="finish-grid">{WALLS.map((c) => <button key={c} className={`swatch-chip ${wallColor === c ? 'on' : ''}`} style={{ background: c }} aria-label={`Wall ${c}`} onClick={() => set.getState().setWallColor(c)} />)}</div>
      <h3>Floor</h3>
      {FLOORS.map((f) => <button key={f.label} className={`drawer-item ${floorStyle === f.style && floorColor === f.color ? 'active' : ''}`} onClick={() => set.getState().setFloorStyle(f.style, f.color)}><span className="swatch-dot" style={{ background: f.color }} />{f.label}</button>)}
    </div>
  );
}
