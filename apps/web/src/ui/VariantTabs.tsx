import { useEffect, useRef, useState } from 'react';
import { useEditor } from '../store';
import { I } from './icons';

export function VariantTabs() {
  const layouts = useEditor((s) => s.layouts); const activeId = useEditor((s) => s.activeId); const saveState = useEditor((s) => s.saveState); const set = useEditor;
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null); const [renaming, setRenaming] = useState<string | null>(null); const [name, setName] = useState('');
  const seen = useRef<Set<string>>(new Set()); const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    const now = new Set(fresh); let changed = false;
    for (const l of layouts) if (!seen.current.has(l.id)) { seen.current.add(l.id); if (seen.current.size > 1 && l.createdBy === 'agent') { now.add(l.id); changed = true; setTimeout(() => setFresh((f) => { const n = new Set(f); n.delete(l.id); return n; }), 1200); } }
    if (changed) setFresh(now);
  }, [layouts]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const close = () => setMenu(null); window.addEventListener('pointerdown', close); return () => window.removeEventListener('pointerdown', close); }, []);
  const sorted = [...layouts].sort((a, b) => (a.isCurrent ? -1 : b.isCurrent ? 1 : 0));
  let pressTimer: ReturnType<typeof setTimeout> | null = null;
  return (
    <div className="variant-tabs" data-testid="variant-tabs">
      {sorted.map((l) => (
        renaming === l.id ? (
          <form key={l.id} className="tab renaming" onSubmit={(e) => { e.preventDefault(); void set.getState().renameVariant(l.id, name.trim() || l.name); setRenaming(null); }}>
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)} onBlur={() => setRenaming(null)} maxLength={40} />
          </form>
        ) : (
          <button key={l.id} className={`tab ${l.id === activeId ? 'active' : ''} ${fresh.has(l.id) ? 'fresh' : ''}`} data-testid={`tab-${l.isCurrent ? 'current' : l.id}`}
            onClick={() => void set.getState().switchLayout(l.id)}
            onContextMenu={(e) => { e.preventDefault(); if (!l.isCurrent) setMenu({ id: l.id, x: e.clientX, y: e.clientY }); }}
            onPointerDown={(e) => { if (l.isCurrent) return; const { clientX: x, clientY: y } = e; pressTimer = setTimeout(() => setMenu({ id: l.id, x, y }), 550); }}
            onPointerUp={() => { if (pressTimer) clearTimeout(pressTimer); }} onPointerLeave={() => { if (pressTimer) clearTimeout(pressTimer); }}>
            {(l.isCurrent || l.kind === 'base') && <span className="tab-lock"><I.lock /></span>}{l.name}
            {l.id === activeId && saveState !== 'saved' && saveState !== 'readonly' && <span className={`save-dot ${saveState}`} title={saveState} />}
          </button>
        )
      ))}
      <button className="tab plus" aria-label="New variant" title="New variant from this layout" onClick={() => void set.getState().createVariant()}><I.plus /></button>
      {menu && (
        <div className="context-menu" style={{ left: menu.x, top: menu.y }} onPointerDown={(e) => e.stopPropagation()}>
          <button onClick={() => { const l = layouts.find((x) => x.id === menu.id); setName(l?.name ?? ''); setRenaming(menu.id); setMenu(null); }}>Rename</button>
          <button onClick={() => { void set.getState().createVariant(`${layouts.find((x) => x.id === menu.id)?.name} copy`, menu.id); setMenu(null); }}>Duplicate</button>
          <button onClick={() => { const cur = layouts.find((x) => x.isCurrent); if (cur) location.assign(`/compare/${cur.id}/${menu.id}`); }}>Compare with Current</button>
          <button className="danger" onClick={() => { void set.getState().deleteVariant(menu.id); setMenu(null); }}>Delete</button>
        </div>
      )}
    </div>
  );
}
