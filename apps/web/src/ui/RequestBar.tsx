import { useRef, useState } from 'react';
import { useEditor } from '../store';
import { I } from './icons';
import { api, unwrapItem } from '../lib/api';

export function RequestBar() {
  const open = useEditor((s) => s.requestOpen); const busy = useEditor((s) => s.agentBusy); const reply = useEditor((s) => s.agentReply); const furnishing = useEditor((s) => s.furnishing); const set = useEditor;
  const [text, setText] = useState(''); const [furnitureId, setFurnitureId] = useState<string | undefined>(); const [attached, setAttached] = useState<string | null>(null); const [importing, setImporting] = useState(false); const file = useRef<HTMLInputElement>(null);
  const send = async () => { if (!text.trim() || busy) return; await set.getState().askAgent(text.trim(), furnitureId); setText(''); setFurnitureId(undefined); setAttached(null); };
  const pasteLink = async () => {
    const url = window.prompt('Paste a listing link', 'http://localhost:8000/fixtures/listings/desk'); if (!url) return;
    setImporting(true);
    try { const f = unwrapItem(await api.fromLink(url)); set.getState().addFurniture(f); setFurnitureId(f.id); setAttached(`${f.name}${f.price ? ` · $${f.price}` : ''}`); set.getState().toast(`Imported ${f.name}`); }
    catch (e) { set.getState().toast(`Import failed: ${(e as Error).message}`, 'error'); } finally { setImporting(false); }
  };
  const photo = async (fl: File | undefined) => {
    if (!fl) return; setImporting(true);
    try { const f = unwrapItem(await api.fromPhoto(fl)); set.getState().addFurniture(f); setFurnitureId(f.id); setAttached(`${f.name} (estimated)`); }
    catch (e) { set.getState().toast(`Photo import failed: ${(e as Error).message}`, 'error'); } finally { setImporting(false); }
  };
  if (!open) return <button className="sq request-fab" data-testid="request-fab" title="Ask the room" aria-label="Ask" onClick={() => set.getState().setRequestOpen(true)}><I.chat /></button>;
  return (
    <div className="request-bar" data-testid="request-bar">
      <div className="request-head"><span>Ask the room</span><button className="sq small" aria-label="Close" onClick={() => set.getState().setRequestOpen(false)}><I.close /></button></div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Will this fit beside my window without moving my bed?" rows={2} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }} />
      <div className="request-actions">
        <button className="btn dark small" disabled={importing} onClick={pasteLink}><I.link /> Paste link</button>
        <button className="btn dark small" disabled={importing} onClick={() => file.current?.click()}><I.photo /> Photo</button>
        <input ref={file} type="file" accept="image/*" hidden onChange={(e) => void photo(e.target.files?.[0])} />
        <button className="btn dark small" disabled={busy || furnishing || !text.trim()} title="Furnish as a new variant in this style" onClick={() => { void set.getState().furnish(text.trim(), { restyle: true }); setText(''); }}>{furnishing ? <span className="spinner small" /> : '✦'} Restyle</button>
        <span className="attached">{importing ? 'Importing…' : attached}</span>
        <button className="btn primary small" disabled={busy || !text.trim()} onClick={() => void send()}>{busy ? <span className="spinner small" /> : <I.send />} Send</button>
      </div>
      {(reply || busy || furnishing) && <div className="reply" data-testid="agent-reply">{busy ? 'Thinking about your room…' : furnishing ? 'Furnishing your room…' : reply}</div>}
    </div>
  );
}
