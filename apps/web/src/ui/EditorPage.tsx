import { useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import type { BridgeMessage } from '@arp/contracts';
import { useEditor } from '../store';
import { RoomScene } from '../scene/Scene';
import { TopLeft } from './TopLeft';
import { TopRight } from './TopRight';
import { Palette } from './Palette';
import { SidePanel } from './SidePanel';
import { BottomCenter } from './BottomCenter';
import { VariantTabs } from './VariantTabs';
import { AnalysisTile } from './AnalysisTile';
import { RoomNeeds } from './RoomNeeds';
import { RequestBar } from './RequestBar';
import { Drawers } from './Drawers';
import { Toasts } from './Toasts';
import { onHostMessage, postToHost } from '../lib/bridge';
import { setApiBase } from '../lib/api';
import { Backdrop } from './Backdrop';

export function EditorPage() {
  const { id, sample } = useParams();
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const s = useEditor;
  const loading = useEditor((x) => x.loading); const room = useEditor((x) => x.room); const theme = useEditor((x) => x.theme); const night = useEditor((x) => x.night);
  const ghostId = useEditor((x) => x.ghostId); const layouts = useEditor((x) => x.layouts); const lastError = useEditor((x) => x.lastError);
  const ui = params.get('ui') !== '0';

  useEffect(() => {
    const units = params.get('units'); const apiUrl = params.get('api');
    if (apiUrl) setApiBase(apiUrl);
    s.getState().init({ units: units === 'metric' || units === 'imperial' ? units : undefined, embedded: params.get('embedded') === '1' || undefined });
    if (sample) void s.getState().loadFixture(sample); else if (id) void s.getState().loadLayout(id);
  }, [id, sample, params, s]);

  // bridge: host → editor
  useEffect(() => {
    postToHost('editor:ready', { route: location.pathname });
    return onHostMessage((m: BridgeMessage) => {
      const p = (m.payload ?? {}) as Record<string, unknown>;
      if (m.type === 'host:hello') { if (typeof p.units === 'string') s.getState().setUnits(p.units as 'imperial' | 'metric'); if (typeof p.apiUrl === 'string') setApiBase(p.apiUrl); s.getState().init({ embedded: true }); }
      if (m.type === 'host:units' && typeof p.units === 'string') s.getState().setUnits(p.units as 'imperial' | 'metric');
      if (m.type === 'host:openLayout' && typeof p.layoutId === 'string' && p.layoutId !== s.getState().activeId) void s.getState().switchLayout(p.layoutId);
      if (m.type === 'host:request' && typeof p.text === 'string') void s.getState().askAgent(p.text, typeof p.furnitureId === 'string' ? p.furnitureId : undefined);
    });
  }, [s]);

  // keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const st = s.getState(); const tag = (e.target as HTMLElement)?.tagName; if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); if (e.shiftKey) st.redo(); else st.undo(); return; }
      if (e.key === 'Escape') { st.cancelPlacing(); st.select(null); st.setDrawer(null); return; }
      if (!st.selectedId) return;
      if (e.key === 'r' || e.key === 'R') st.rotateItem(st.selectedId);
      if (e.key === 'l' || e.key === 'L') st.toggleLock(st.selectedId);
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); st.removeItem(st.selectedId); }
      if (e.key === 'd' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); st.duplicateItem(st.selectedId); }
    };
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey);
  }, [s]);

  const ghost = ghostId ? layouts.find((l) => l.id === ghostId) ?? null : null;
  return (
    <div className={`editor theme-${theme} ${night ? 'night' : ''} ${ui ? '' : 'no-ui'}`}>
      <Backdrop />
      {room && <RoomScene ghostLayout={ghost} className="canvas" />}
      {loading && <div className="loading"><div className="spinner" />Loading room…</div>}
      {!loading && !room && lastError && <div className="loading error">Couldn’t load this layout.<br /><small>{lastError}</small></div>}
      {ui && room && (
        <>
          <TopLeft /><TopRight /><VariantTabs /><AnalysisTile /><RoomNeeds /><Palette /><SidePanel /><BottomCenter /><RequestBar /><Drawers />
        </>
      )}
      <Toasts />
    </div>
  );
}
