import { formatDims, formatLength, gapToNearestWall, itemRect, roomBounds } from '@arp/geometry';
import { useEditor, violationLevel } from '../store';
import { externalUrl } from '../lib/auth';
import { I } from './icons';

// Real-world finishes, not a candy palette: whites/greiges/greys and fabrics, then woods, muted accents and metals.
export const SWATCHES = [
  '#F4F2EE', '#E7E2D8', '#D8D0C4', '#C9BDA9', '#B7AC9C', '#A39A8E', '#8C8984', '#6F6C68', '#55565A', '#3A3B3D', '#2A2A2B',
  '#848A92', '#6F7884', '#8A8C80', '#6F7D68', '#B2A286', '#A8927A', '#9C8A86', '#B8A99A',
  '#D2BC98', '#C2A887', '#A98459', '#9A7148', '#7C5A3E', '#5E4333', '#3F2E25', '#8E8173', '#2F2A27',
  '#7C4D31', '#A06E55', '#B09A8A', '#5E6B52', '#7A8584', '#566273', '#A8844F', '#A7ABAE', '#4A4D52', '#E3E0DA',
];

/** Details + finishes for the selected piece, in the right rail (desktop). Actions live in the bottom selection bar. */
export function SidePanel() {
  const selectedId = useEditor((s) => s.selectedId); const items = useEditor((s) => s.items); const furniture = useEditor((s) => s.furniture); const room = useEditor((s) => s.room);
  const units = useEditor((s) => s.units); const validation = useEditor((s) => s.validation); const set = useEditor;
  const item = items.find((i) => i.id === selectedId); const f = item && furniture[item.furnitureId];
  if (!item || !f || !room) return null;
  const gap = gapToNearestWall(itemRect(item, f.dims), roomBounds(room.skeleton));
  const level = violationLevel(validation, item.id); const problems = validation?.violations.filter((v) => v.items.includes(item.id)) ?? [];
  return (
    <aside className={`side-panel panel ${level ?? ''}`} data-testid="side-panel">
      <div className="card-head">
        <div className="details-name">{f.name}{f.estimated && <span className="badge">estimated</span>}{item.locked && <span className="badge lock"><I.lock />locked</span>}</div>
        <button className="icon-btn" aria-label="Close" onClick={() => set.getState().select(null)}><I.close /></button>
      </div>
      <dl className="details">
        <div><dt>Size</dt><dd>{formatDims(f.dims, units)}</dd></div>
        <div><dt>Gap to wall</dt><dd>{formatLength(gap, units)}</dd></div>
        <div><dt>Rotation</dt><dd>{item.rotation}°</dd></div>
        {f.price != null && <div><dt>Price</dt><dd>${f.price}{f.deliveryCost ? ` + $${f.deliveryCost} delivery` : ''}</dd></div>}
      </dl>
      {problems.map((v, k) => <div key={k} className={`problem ${v.severity}`}>{v.message}</div>)}
      {externalUrl(f.sourceUrl) && <div className="details-note"><a href={externalUrl(f.sourceUrl)} target="_blank" rel="noreferrer">Open original listing</a> · seller checkout; this app does not process the purchase.</div>}
      <div className="card-label">Finish</div>
      <div className="finish-grid">
        {SWATCHES.map((c) => <button key={c} className={`swatch-chip ${item.color === c ? 'on' : ''}`} style={{ background: c }} aria-label={`Color ${c}`} onClick={() => set.getState().recolor(item.id, item.color === c ? null : c)} />)}
      </div>
    </aside>
  );
}
