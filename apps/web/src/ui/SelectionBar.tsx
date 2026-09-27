import { useEffect, useState } from 'react';
import { formatDims, formatLength, gapToNearestWall, itemRect, roomBounds } from '@arp/geometry';
import { useEditor, violationLevel } from '../store';
import { I } from './icons';
import { SWATCHES } from './SidePanel';

/** Actions for the selected piece, docked bottom-centre in place of the view toolbar. On phones it also carries the details and finishes. */
export function SelectionBar() {
  const selectedId = useEditor((s) => s.selectedId); const items = useEditor((s) => s.items); const furniture = useEditor((s) => s.furniture); const room = useEditor((s) => s.room);
  const units = useEditor((s) => s.units); const validation = useEditor((s) => s.validation); const set = useEditor;
  const [finish, setFinish] = useState(false);
  useEffect(() => { setFinish(false); }, [selectedId]);
  const item = items.find((i) => i.id === selectedId); const f = item && furniture[item.furnitureId];
  if (!item || !f || !room) return null;
  const level = violationLevel(validation, item.id); const problem = validation?.violations.find((v) => v.items.includes(item.id));
  const gap = gapToNearestWall(itemRect(item, f.dims), roomBounds(room.skeleton));
  const st = set.getState();
  return (
    <div className="selection" data-testid="selection-bar">
      {finish && (
        <div className="popover finish-pop" data-testid="finish-popover">
          <div className="popover-title">Finish</div>
          <div className="finish-grid">
            {SWATCHES.map((c) => <button key={c} className={`swatch-chip ${item.color === c ? 'on' : ''}`} style={{ background: c }} aria-label={`Color ${c}`} onClick={() => st.recolor(item.id, item.color === c ? null : c)} />)}
          </div>
        </div>
      )}
      <div className={`sel-head ${level ?? ''}`}>
        <b>{f.name}</b>{item.locked && <span className="sel-tag"><I.lock />Locked</span>}
        <span className="sel-meta">{formatDims(f.dims, units)} · {formatLength(gap, units)} to wall</span>
        {problem && <span className={`sel-problem ${problem.severity}`}>{problem.message}</span>}
      </div>
      <div className="cluster toolbar selection-bar">
        <button className="sq labeled" title="Rotate 90° (R)" aria-label="Rotate" disabled={item.locked} onClick={() => st.rotateItem(item.id)}><I.rotate /><span>Rotate</span></button>
        <button className={`sq labeled ${item.locked ? 'active' : ''}`} title={item.locked ? 'Unlock (L)' : 'Lock in place (L)'} aria-label={item.locked ? 'Unlock' : 'Lock'} onClick={() => st.toggleLock(item.id)}>{item.locked ? <I.lock /> : <I.unlock />}<span>{item.locked ? 'Locked' : 'Lock'}</span></button>
        <button className="sq labeled" title="Duplicate (⌘D)" aria-label="Duplicate" onClick={() => st.duplicateItem(item.id)}><I.copy /><span>Copy</span></button>
        <button className={`sq labeled finish-btn ${finish ? 'active' : ''}`} title="Change finish" aria-label="Finish" onClick={() => setFinish(!finish)}><span className="finish-dot" style={{ background: item.color ?? f.color ?? '#B7AD9E' }} /><span>Finish</span></button>
        <button className="sq labeled danger-glyph" title={item.locked ? 'Unlock to remove' : 'Remove (Del)'} aria-label="Remove" disabled={item.locked} onClick={() => st.removeItem(item.id)}><I.trash /><span>Remove</span></button>
        <span className="divider" />
        <button className="sq labeled" title="Done (Esc)" aria-label="Done" onClick={() => st.select(null)}><I.check /><span>Done</span></button>
      </div>
    </div>
  );
}
