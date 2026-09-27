import { useEffect, useState } from 'react';
import { useEditor } from '../store';
import { I } from './icons';
import { SelectionBar } from './SelectionBar';

export function BottomCenter() {
  const overlays = useEditor((s) => s.overlays); const overlaysOpen = useEditor((s) => s.overlaysOpen); const ghostOpen = useEditor((s) => s.ghostOpen); const ghostId = useEditor((s) => s.ghostId);
  const night = useEditor((s) => s.night); const layouts = useEditor((s) => s.layouts); const activeId = useEditor((s) => s.activeId); const selectedId = useEditor((s) => s.selectedId);
  const items = useEditor((s) => s.items); const set = useEditor;
  const [roomOpen, setRoomOpen] = useState(false); const [confirmClear, setConfirmClear] = useState(false);
  useEffect(() => { if (overlaysOpen || ghostOpen) setRoomOpen(false); }, [overlaysOpen, ghostOpen]);
  useEffect(() => { if (!roomOpen) setConfirmClear(false); }, [roomOpen]);
  if (selectedId) return <div className="bottom-center" data-testid="bottom-center"><SelectionBar /></div>;
  const anyOverlay = overlays.walkable || overlays.keepClear || overlays.lowClearance;
  const locked = items.filter((i) => i.locked).length; const removable = items.length - locked;
  const openRoom = () => { set.getState().setOverlaysOpen(false); set.getState().setGhostOpen(false); setRoomOpen(!roomOpen); };
  return (
    <div className="bottom-center" data-testid="bottom-center">
      {overlaysOpen && (
        <div className="popover" data-testid="overlay-popover">
          <div className="popover-title">Show on floor</div>
          <label><input type="checkbox" checked={overlays.walkable} onChange={() => set.getState().toggleOverlay('walkable')} /><span className="swatch-dot green" />Walkable</label>
          <label><input type="checkbox" checked={overlays.keepClear} onChange={() => set.getState().toggleOverlay('keepClear')} /><span className="swatch-dot red" />Keep clear (door)</label>
          <label><input type="checkbox" checked={overlays.lowClearance} onChange={() => set.getState().toggleOverlay('lowClearance')} /><span className="swatch-dot yellow" />Low clearance</label>
        </div>
      )}
      {ghostOpen && (
        <div className="popover" data-testid="ghost-popover">
          <div className="popover-title">Ghost another variant</div>
          <label><input type="radio" checked={ghostId === null} onChange={() => set.getState().setGhost(null)} />None</label>
          {layouts.filter((l) => l.id !== activeId).map((l) => <label key={l.id}><input type="radio" checked={ghostId === l.id} onChange={() => set.getState().setGhost(l.id)} />{l.name}</label>)}
          {layouts.length > 1 && activeId && <a className="btn dark small" href={`/compare/${layouts.find((l) => l.isCurrent)?.id ?? activeId}/${activeId}`}>Open compare view</a>}
        </div>
      )}
      {roomOpen && (
        <div className="popover room-menu" data-testid="room-popover">
          <div className="popover-title">Room</div>
          <button className="menu-row" disabled={!locked} onClick={() => set.getState().unlockAll()}><I.unlock /><span>Unlock all</span><small>{locked ? `${locked} locked` : 'none locked'}</small></button>
          <button className="menu-row" disabled={!removable} onClick={() => set.getState().lockAll()}><I.lock /><span>Lock all</span></button>
          <button className={`menu-row danger ${confirmClear ? 'confirm' : ''}`} disabled={!removable} data-testid="clear-room"
            onClick={() => { if (!confirmClear) { setConfirmClear(true); return; } set.getState().clearRoom(); setRoomOpen(false); }}>
            <I.trash /><span>{confirmClear ? `Remove ${removable} item${removable === 1 ? '' : 's'}?` : 'Remove all items'}</span><small>{confirmClear ? 'tap to confirm' : locked ? 'keeps locked' : ''}</small>
          </button>
        </div>
      )}
      <div className="cluster toolbar">
        <button className={`sq ${anyOverlay || overlaysOpen ? 'active' : ''}`} title="Floor overlays" aria-label="Overlays" onClick={() => set.getState().setOverlaysOpen(!overlaysOpen)}><I.layers /></button>
        <button className={`sq ${ghostId || ghostOpen ? 'active' : ''}`} title="Compare with another variant" aria-label="Ghost compare" onClick={() => set.getState().setGhostOpen(!ghostOpen)}><I.compare /></button>
        <button className={`sq ${night ? 'active' : ''}`} title="Day / night" aria-label="Day night" onClick={() => set.getState().toggleNight()}><I.moon /></button>
        <button className={`sq ${roomOpen ? 'active' : ''}`} title="Room: unlock all, remove all" aria-label="Room actions" aria-expanded={roomOpen} onClick={openRoom}><I.sliders /></button>
      </div>
    </div>
  );
}
