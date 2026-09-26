import { useEditor } from '../store';
import { I } from './icons';
import { postToHost } from '../lib/bridge';

export function snapshotCanvas(): string | null {
  const gl = (window as unknown as { __arpGl?: () => { domElement: HTMLCanvasElement } | null }).__arpGl?.();
  return gl ? gl.domElement.toDataURL('image/png') : null;
}
export function TopLeft() {
  const history = useEditor((s) => s.history); const drawer = useEditor((s) => s.drawer); const set = useEditor;
  const snap = () => {
    const url = snapshotCanvas(); if (!url) return;
    postToHost('editor:snapshot', { dataUrl: url });
    if (!set.getState().embedded) { const a = document.createElement('a'); a.href = url; a.download = `room-${Date.now()}.png`; a.click(); }
    set.getState().toast('Snapshot saved');
  };
  return (
    <div className="cluster top-left" data-testid="top-left">
      <button className={`sq ${drawer === 'menu' ? 'active' : ''}`} title="Menu" aria-label="Menu" onClick={() => set.getState().setDrawer(drawer === 'menu' ? null : 'menu')}><I.menu /></button>
      <button className="sq" title="Snapshot" aria-label="Snapshot" onClick={snap}><I.camera /></button>
      <button className="sq" title="Undo (⌘Z)" aria-label="Undo" disabled={history.length === 0} onClick={() => set.getState().undo()}><I.undo /></button>
    </div>
  );
}
