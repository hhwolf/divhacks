import { useState } from 'react';
import type { RoomElement } from '@arp/contracts';
import { useEditor } from '../store';
import { I } from './icons';

/** "This room needs" checklist from the setup flow: an element counts as done when one of its catalog items is placed. */
export function RoomNeeds() {
  const room = useEditor((s) => s.room); const items = useEditor((s) => s.items); const furniture = useEditor((s) => s.furniture); const set = useEditor;
  const [open, setOpen] = useState(true);
  const elements: RoomElement[] = room?.elements ?? [];
  if (!elements.length) return null;
  const placed = new Set(items.map((i) => i.furnitureId));
  const done = (e: RoomElement) => (e.furnitureIds ?? []).some((id) => placed.has(id));
  const n = elements.filter(done).length;
  return (
    <div className={`needs ${open ? 'open' : ''}`} data-testid="room-needs">
      <button className="needs-head" onClick={() => setOpen(!open)}>
        <span>This room needs</span><b>{n}/{elements.length}</b>
      </button>
      {open && (
        <ul>
          {elements.map((e) => {
            const first = (e.furnitureIds ?? []).find((id) => furniture[id]);
            return (
              <li key={e.id} className={done(e) ? 'done' : ''}>
                <span className="needs-check">{done(e) ? '✓' : ''}</span>
                <span className="needs-label">{e.label}</span>
                {first && !done(e) && <button className="needs-add" title={`Place ${furniture[first].name}`} onClick={() => set.getState().startPlacing(first)}><I.plus /></button>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
