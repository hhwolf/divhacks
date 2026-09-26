import { useEditor } from '../store';
import { I } from './icons';
export function TopRight() {
  const drawer = useEditor((s) => s.drawer); const viewMode = useEditor((s) => s.viewMode); const set = useEditor;
  return (
    <div className="cluster top-right" data-testid="top-right">
      <button className="sq" title={`View: ${viewMode} (tap to cycle)`} aria-label="Cycle view" onClick={() => set.getState().cycleView()}><I.eye /></button>
      <button className={`sq ${drawer === 'paint' ? 'active' : ''}`} title="Paint walls & floor" aria-label="Paint" onClick={() => set.getState().setDrawer(drawer === 'paint' ? null : 'paint')}><I.bucket /></button>
      <span className="divider" />
      <button className={`sq ${drawer === 'help' ? 'active' : ''}`} title="Help" aria-label="Help" onClick={() => set.getState().setDrawer(drawer === 'help' ? null : 'help')}><I.help /></button>
    </div>
  );
}
