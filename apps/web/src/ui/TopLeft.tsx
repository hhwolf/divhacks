import { useEditor } from '../store';
import { I } from './icons';
import { postToHost } from '../lib/bridge';

export function snapshotCanvas(): string | null {
  const gl = (window as unknown as { __arpGl?: () => { domElement: HTMLCanvasElement } | null }).__arpGl?.();
  return gl ? gl.domElement.toDataURL('image/png') : null;
}
/** Home: inside the phone app the host owns navigation, so ask it instead of loading the web home into the WebView. */
export function goHome(route = '/') {
  if (useEditor.getState().embedded) postToHost('editor:navigate', { route }); else location.assign('/');
}
export function TopLeft() {
  const drawer = useEditor((s) => s.drawer); const set = useEditor;
  const snap = () => {
    const url = snapshotCanvas(); if (!url) return;
    postToHost('editor:snapshot', { dataUrl: url });
    if (!set.getState().embedded) { const a = document.createElement('a'); a.href = url; a.download = `room-${Date.now()}.png`; a.click(); }
    set.getState().toast('Snapshot saved');
  };
  // Just Menu (Switch room) and Snapshot: the phone app has its own Back, and undo/redo stay on ⌘Z / ⇧⌘Z.
  return (
    <div className="cluster top-left" data-testid="top-left">
      <button className={`sq ${drawer === 'menu' ? 'active' : ''}`} title="Menu" aria-label="Menu" onClick={() => set.getState().setDrawer(drawer === 'menu' ? null : 'menu')}><I.menu /></button>
      <button className="sq" title="Snapshot" aria-label="Snapshot" onClick={snap}><I.camera /></button>
    </div>
  );
}
