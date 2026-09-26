import { useEditor } from '../store';
import { I } from './icons';
export function BottomCenter() {
  const overlays = useEditor((s) => s.overlays); const overlaysOpen = useEditor((s) => s.overlaysOpen); const ghostOpen = useEditor((s) => s.ghostOpen); const ghostId = useEditor((s) => s.ghostId);
  const night = useEditor((s) => s.night); const sound = useEditor((s) => s.sound); const layouts = useEditor((s) => s.layouts); const activeId = useEditor((s) => s.activeId); const set = useEditor;
  const anyOverlay = overlays.walkable || overlays.keepClear || overlays.lowClearance;
  return (
    <div className="bottom-center" data-testid="bottom-center">
      {overlaysOpen && (
        <div className="popover" data-testid="overlay-popover">
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
      <div className="cluster">
        <button className={`sq ${anyOverlay || overlaysOpen ? 'active' : ''}`} title="Overlays" aria-label="Overlays" onClick={() => set.getState().setOverlaysOpen(!overlaysOpen)}><I.palette /></button>
        <button className={`sq ${ghostId || ghostOpen ? 'active' : ''}`} title="Ghost compare" aria-label="Ghost compare" onClick={() => set.getState().setGhostOpen(!ghostOpen)}><I.tree /></button>
        <button className={`sq ${night ? 'active' : ''}`} title="Day / night" aria-label="Day night" onClick={() => set.getState().toggleNight()}><I.moon /></button>
        <button className={`sq ${sound ? '' : 'muted'}`} title="Sound" aria-label="Sound" onClick={() => set.getState().toggleSound()}>{sound ? <I.sound /> : <I.soundOff />}</button>
      </div>
    </div>
  );
}
