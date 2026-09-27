import { useEditor } from '../store';
import { I } from './icons';
export function TopRight() {
  const drawer = useEditor((s) => s.drawer); const viewMode = useEditor((s) => s.viewMode); const set = useEditor;
  const viewLabel = viewMode === 'cutaway' ? 'Full walls' : viewMode === 'half' ? 'Half walls' : 'Floor plan';
  return (
    <div className="cluster top-right" data-testid="top-right">
      <button className="sq" title="Turn room left" aria-label="Rotate room left" onClick={() => set.getState().orbitBy(-1)}><I.rotate /></button>
      <button className={`sq ${viewMode !== 'cutaway' ? 'active' : ''}`} title={`View: ${viewLabel} (tap to change)`} aria-label="Cycle view" onClick={() => set.getState().cycleView()}><I.eye /></button>
      <button className="sq flip" title="Turn room right" aria-label="Rotate room right" onClick={() => set.getState().orbitBy(1)}><I.rotate /></button>
      <button className={`sq ${drawer === 'paint' ? 'active' : ''}`} title="Walls & floor" aria-label="Paint" onClick={() => set.getState().setDrawer(drawer === 'paint' ? null : 'paint')}><I.bucket /></button>
    </div>
  );
}
