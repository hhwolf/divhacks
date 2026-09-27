import { formatDims, formatLength, gapToNearestWall, itemRect, roomBounds } from '@arp/geometry';
import { useEditor, violationLevel } from '../store';
import { I } from './icons';

// 8 rows × 3 columns like ref3: row 0 = ✕ (outside the grid) + rotate + lock, row 1 = duplicate + delete + first swatch, then swatches.
// Real-world finishes, not a candy palette: page 1 = whites/greiges/greys and fabrics, page 2 = woods, muted accents, metals.
const SWATCHES = [
  '#F4F2EE', '#E7E2D8', '#D8D0C4', '#C9BDA9', '#B7AC9C', '#A39A8E', '#8C8984', '#6F6C68', '#55565A', '#3A3B3D', '#2A2A2B',
  '#848A92', '#6F7884', '#8A8C80', '#6F7D68', '#B2A286', '#A8927A', '#9C8A86', '#B8A99A',
  '#D2BC98', '#C2A887', '#A98459', '#9A7148', '#7C5A3E', '#5E4333', '#3F2E25', '#8E8173', '#2F2A27',
  '#7C4D31', '#A06E55', '#B09A8A', '#5E6B52', '#7A8584', '#566273', '#A8844F', '#A7ABAE', '#4A4D52', '#E3E0DA',
];
const PER_PAGE = 19;
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
        <button className="tile action danger" title="Remove (Del)" aria-label="Remove" disabled={item.locked} onClick={() => set.getState().removeItem(item.id)}><I.trash /></button>
        {SWATCHES.slice(p * PER_PAGE, (p + 1) * PER_PAGE).map((c) => (
          <button key={c} className={`tile swatch ${item.color === c ? 'on' : ''}`} style={{ background: c }} aria-label={`Color ${c}`} onClick={() => set.getState().recolor(item.id, item.color === c ? null : c)} />
        ))}
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
