import { formatDims, formatLength, gapToNearestWall, itemRect, roomBounds } from '@arp/geometry';
import { useEditor, violationLevel } from '../store';
import { I } from './icons';

const SWATCHES = ['#5CB78E', '#9679D3', '#6F7BE0', '#F08CB4', '#7ED0E8', '#9FD3F0', '#E85A4F', '#4FC2B8', '#F2925E', '#F4C542', '#F7B531', '#8BC34A', '#B9E08C', '#F6E6A2', '#C9A6E8', '#F2C7C0', '#F9D0E4', '#EAD6C8', '#6CD6C8', '#FFFFFF', '#B6B8C8', '#6B6E80', '#4B4E5E', '#2B2B33'];
const PER_PAGE = 24;
export function SidePanel() {
  const selectedId = useEditor((s) => s.selectedId); const items = useEditor((s) => s.items); const furniture = useEditor((s) => s.furniture); const room = useEditor((s) => s.room);
  const units = useEditor((s) => s.units); const validation = useEditor((s) => s.validation); const page = useEditor((s) => s.sidePage); const set = useEditor;
  const item = items.find((i) => i.id === selectedId); const f = item && furniture[item.furnitureId];
  if (!item || !f || !room) return null;
  const gap = gapToNearestWall(itemRect(item, f.dims), roomBounds(room.skeleton));
  const level = violationLevel(validation, item.id); const problems = validation?.violations.filter((v) => v.items.includes(item.id)) ?? [];
  const pages = Math.ceil(SWATCHES.length / PER_PAGE); const p = Math.min(page, pages - 1);
  return (
    <aside className="side-panel" data-testid="side-panel">
      <button className="sq small close" aria-label="Close" onClick={() => set.getState().select(null)}><I.close /></button>
      <div className="swatch-grid">
        <button className="tile action" title="Rotate (R)" aria-label="Rotate" disabled={item.locked} onClick={() => set.getState().rotateItem(item.id)}><I.rotate /></button>
        <button className={`tile action ${item.locked ? 'on' : ''}`} title="Lock (L)" aria-label="Lock" onClick={() => set.getState().toggleLock(item.id)}>{item.locked ? <I.lock /> : <I.unlock />}</button>
        <button className="tile action" title="Duplicate (⌘D)" aria-label="Duplicate" onClick={() => set.getState().duplicateItem(item.id)}><I.copy /></button>
        {SWATCHES.slice(p * PER_PAGE, (p + 1) * PER_PAGE).map((c) => (
          <button key={c} className={`tile swatch ${item.color === c ? 'on' : ''}`} style={{ background: c }} aria-label={`Color ${c}`} onClick={() => set.getState().recolor(item.id, item.color === c ? null : c)} />
        ))}
        <button className="tile action danger" title="Remove (Del)" aria-label="Remove" disabled={item.locked} onClick={() => set.getState().removeItem(item.id)}><I.trash /></button>
      </div>
      <div className="pager">
        <button className="sq small" aria-label="Previous" disabled={p === 0} onClick={() => set.getState().setSidePage(p - 1)}><I.chevL /></button>
        <span className="page-num">{p + 1}</span>
        <button className="sq small" aria-label="Next" disabled={p >= pages - 1} onClick={() => set.getState().setSidePage(p + 1)}><I.chevR /></button>
      </div>
      <div className={`details ${level ?? ''}`}>
        <div className="details-name">{f.name} {f.estimated && <span className="badge">estimated</span>}{item.locked && <span className="badge lock">locked</span>}</div>
        <div className="details-row">{formatDims(f.dims, units)}</div>
        <div className="details-row">Gap to wall: <b>{formatLength(gap, units)}</b></div>
        {(f.price != null || f.sourceUrl) && <div className="details-row">{f.price != null && <b>${f.price}</b>} {f.sourceUrl && <a href={f.sourceUrl} target="_blank" rel="noreferrer">source</a>}</div>}
        {problems.map((v, k) => <div key={k} className={`details-row problem ${v.severity}`}>{v.message}</div>)}
      </div>
    </aside>
  );
}
