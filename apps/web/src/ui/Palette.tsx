import { useMemo, useState } from 'react';
import type { FurnitureItem } from '@arp/contracts';
import { useEditor } from '../store';
import { I } from './icons';
import { apiBase } from '../lib/api';

const CATS: { key: string; label: string; icon: keyof typeof I }[] = [
  { key: 'All', label: 'All', icon: 'grid' }, { key: 'bed', label: 'Bed', icon: 'bed' }, { key: 'desk', label: 'Desk', icon: 'desk' }, { key: 'seating', label: 'Seating', icon: 'chair' },
  { key: 'storage', label: 'Storage', icon: 'storage' }, { key: 'table', label: 'Table', icon: 'table' }, { key: 'decor', label: 'Decor', icon: 'plant' }, { key: 'imported', label: 'Imported', icon: 'imported' },
];
const COLS = 3, ROWS = 8, PER_PAGE = COLS * ROWS - 1; // first tile is the cursor tool

export function thumbUrl(f: FurnitureItem): string | null {
  if (!f.thumbUrl) return null; return f.thumbUrl.startsWith('http') || f.thumbUrl.startsWith('/assets') ? f.thumbUrl : `${apiBase()}${f.thumbUrl}`;
}
export function Palette() {
  const furniture = useEditor((s) => s.furniture); const placing = useEditor((s) => s.placing); const page = useEditor((s) => s.palettePage); const category = useEditor((s) => s.category); const search = useEditor((s) => s.search);
  const set = useEditor; const [showCats, setShowCats] = useState(false);
  const list = useMemo(() => {
    let items = Object.values(furniture);
    if (category !== 'All') items = items.filter((f) => (category === 'imported' ? f.source !== 'preset' : f.category === category));
    if (search) items = items.filter((f) => f.name.toLowerCase().includes(search.toLowerCase()));
    return items.sort((a, b) => (a.source === 'preset' ? 0 : 1) - (b.source === 'preset' ? 0 : 1) || a.name.localeCompare(b.name));
  }, [furniture, category, search]);
  const pages = Math.max(1, Math.ceil(list.length / PER_PAGE)); const p = Math.min(page, pages - 1); const slice = list.slice(p * PER_PAGE, (p + 1) * PER_PAGE);
  return (
    <div className="palette" data-testid="palette">
      <div className="cat-row">
        <button className={`sq small ${search !== null ? 'active' : ''}`} title="Search" aria-label="Search" onClick={() => { set.getState().setSearch(search === null ? '' : null); }}><I.search /></button>
        <button className={`sq small ${showCats ? 'active' : ''}`} title="Categories" aria-label="Categories" onClick={() => setShowCats((v) => !v)}>{(() => { const Icon = I[CATS.find((c) => c.key === category)?.icon ?? 'grid']; return <Icon />; })()}</button>
        {showCats && (
          <div className="cat-menu">{CATS.map((c) => { const Icon = I[c.icon]; return <button key={c.key} className={`cat ${category === c.key ? 'active' : ''}`} onClick={() => { set.getState().setCategory(c.key); setShowCats(false); }}><Icon /><span>{c.label}</span></button>; })}</div>
        )}
      </div>
      {search !== null && <input className="search" autoFocus placeholder="Search furniture…" value={search} onChange={(e) => set.getState().setSearch(e.target.value)} />}
      <div className="tiles">
        <button className={`tile tool ${!placing ? 'active' : ''}`} title="Select / move" aria-label="Select tool" onClick={() => set.getState().cancelPlacing()}><I.cursor /></button>
        {slice.map((f) => (
          <button key={f.id} className={`tile ${placing?.furnitureId === f.id ? 'active' : ''}`} title={`${f.name}${f.estimated ? ' (estimated)' : ''}`} aria-label={f.name}
            onClick={() => (placing?.furnitureId === f.id ? set.getState().cancelPlacing() : set.getState().startPlacing(f.id))}>
            {thumbUrl(f) ? <img src={thumbUrl(f)!} alt="" draggable={false} onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} /> : <span className="tile-fallback">{f.name.slice(0, 2)}</span>}
            {f.source !== 'preset' && <span className="tile-badge">{f.price ? `$${f.price}` : 'new'}</span>}
          </button>
        ))}
        {Array.from({ length: Math.max(0, PER_PAGE - slice.length) }, (_, k) => <span key={`e${k}`} className="tile empty" />)}
      </div>
      <div className="pager">
        <button className="sq small" aria-label="Previous page" disabled={p === 0} onClick={() => set.getState().setPalettePage(p - 1)}><I.chevL /></button>
        <span className="page-num">{p + 1}</span>
        <button className="sq small" aria-label="Next page" disabled={p >= pages - 1} onClick={() => set.getState().setPalettePage(p + 1)}><I.chevR /></button>
      </div>
    </div>
  );
}
