import { useState } from 'react';
import type { RoomElement } from '@arp/contracts';
import { useEditor } from '../store';
import { I } from './icons';
import { useCompactEditor } from '../lib/useCompactEditor';

const TYPE_LABELS: Record<string, string> = {
  bedroom: 'Bedroom',
  study: 'Study',
  living: 'Living room',
  workout: 'Workout',
  creative: 'Creative studio',
  shared: 'Shared room',
};

/** Room type + goals from setup: a goal counts as done when one of its catalog items is placed. */
export function RoomNeeds() {
  const room = useEditor((s) => s.room); const items = useEditor((s) => s.items); const furniture = useEditor((s) => s.furniture); const set = useEditor;
  const compact = useCompactEditor();
  const [open, setOpen] = useState(!compact);
  const elements: RoomElement[] = room?.elements ?? [];
  const types = room?.spaceTypes ?? [];
  if (!elements.length && !types.length) return null;
  const placed = new Set(items.map((i) => i.furnitureId));
  const done = (e: RoomElement) => (e.furnitureIds ?? []).some((id) => placed.has(id));
  const n = elements.filter(done).length;
  return (
    <div className={`needs ${open ? 'open' : ''}`} data-testid="room-needs">
      <button className="needs-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>Room goals</span><b>{elements.length ? `${n}/${elements.length}` : types.length}</b>
      </button>
      {open && (
        <>
          {types.length ? <div className="type-tags">{types.map((t) => <span key={t}>{TYPE_LABELS[t] ?? t}</span>)}</div> : null}
          {elements.length ? (
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
          ) : null}
        </>
      )}
    </div>
  );
}
