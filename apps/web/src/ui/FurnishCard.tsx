import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useEditor } from '../store';
import { I } from './icons';

const IDEAS: { label: string; icon: ReactNode }[] = [
  { label: 'Cozy Japandi bedroom', icon: <I.bed /> },
  { label: 'Industrial home office', icon: <I.desk /> },
  { label: 'Boho living room with plants', icon: <I.plant /> },
  { label: 'Minimal studio', icon: <I.chair /> },
  { label: 'Yoga & meditation corner', icon: <I.plant /> },
];
const MAX_PHOTOS = 4;

/**
 * Shown over an empty room: describe the room you want and/or add inspiration photos; the server furnishes it as a new variant.
 * Laid out like the app's native home screen (hero mark + title, row card with icon square + chevron, pill CTA) in the editor's palette.
 */
export function FurnishCard() {
  const room = useEditor((s) => s.room); const count = useEditor((s) => s.items.length); const activeId = useEditor((s) => s.activeId);
  const busy = useEditor((s) => s.furnishing); const loading = useEditor((s) => s.loading);
  const [text, setText] = useState(''); const [photos, setPhotos] = useState<File[]>([]); const file = useRef<HTMLInputElement>(null);
  const [previews, setPreviews] = useState<string[]>([]);
  useEffect(() => { const urls = photos.map((p) => URL.createObjectURL(p)); setPreviews(urls); return () => urls.forEach((u) => URL.revokeObjectURL(u)); }, [photos]);
  if (!room || count > 0 || loading || !activeId || activeId === 'fixture') return null;
  const go = (theme: string) => { if ((theme.trim() || photos.length) && !busy) void useEditor.getState().furnish(theme.trim(), { photos }); };
  const add = (list: FileList | null) => {
    // copy first: FileList is live and clearing the input (so the same photo can be re-picked) empties it before the updater runs
    const picked = Array.from(list ?? []).filter((f) => f.type.startsWith('image/'));
    if (file.current) file.current.value = '';
    setPhotos((p) => [...p, ...picked].slice(0, MAX_PHOTOS));
  };
  const cta = busy ? 'Furnishing…' : photos.length ? `Furnish from ${photos.length} photo${photos.length > 1 ? 's' : ''}` : 'Furnish my room';
  return (
    <div className="furnish-card" data-testid="furnish-card">
      <div className="furnish-hero">
        <div className="furnish-mark"><I.grid /></div>
        <div>
          <div className="furnish-eyebrow">Empty room</div>
          <div className="furnish-title">What should this room be?</div>
        </div>
      </div>
      <div className="furnish-sub">Describe it, or add photos of rooms you love. I'll lay out furniture that fits.</div>
      <textarea value={text} rows={2} disabled={busy} placeholder="e.g. cozy Japandi study for two, lots of plants"
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); go(text); } }} />

      <button className="furnish-row" data-testid="furnish-add-photo" disabled={busy || photos.length >= MAX_PHOTOS} onClick={() => file.current?.click()}>
        <span className="furnish-row-icon"><I.photo /></span>
        <span className="furnish-row-text"><b>Inspiration photos</b><small>{photos.length ? `${photos.length} of ${MAX_PHOTOS} added` : `Up to ${MAX_PHOTOS} photos of rooms you like`}</small></span>
        <I.chevR />
      </button>
      <input ref={file} type="file" accept="image/*" multiple hidden data-testid="furnish-photo-input" onChange={(e) => add(e.target.files)} />
      {previews.length > 0 && (
        <div className="furnish-photos">
          {previews.map((u, i) => (
            <div key={u} className="furnish-thumb" style={{ backgroundImage: `url(${u})` }}>
              <button aria-label="Remove photo" disabled={busy} onClick={() => setPhotos((p) => p.filter((_, k) => k !== i))}><I.close /></button>
            </div>
          ))}
        </div>
      )}

      {!photos.length && (
        <>
          <div className="furnish-eyebrow">Or start from an idea</div>
          <div className="furnish-ideas">
            {IDEAS.map((t) => <button key={t.label} className="furnish-idea" disabled={busy} onClick={() => { setText(t.label); go(t.label); }}>{t.icon}{t.label}</button>)}
          </div>
        </>
      )}

      <button className="furnish-cta" data-testid="furnish-go" disabled={busy || (!text.trim() && !photos.length)} onClick={() => go(text)}>
        {busy && <span className="spinner small" />}{cta}{!busy && <I.chevR />}
      </button>
    </div>
  );
}
