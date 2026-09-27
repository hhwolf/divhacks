import { useState } from 'react';
import { useEditor } from '../store';
import { I } from './icons';

const SUGGESTIONS = ['Where should a desk go if the bed stays put?', 'Make space for yoga', 'Clear a path from the door'];
const URL_RE = /https?:\/\/\S+/;

export function RequestBar() {
  const open = useEditor((s) => s.requestOpen); const busy = useEditor((s) => s.agentBusy); const reply = useEditor((s) => s.agentReply); const status = useEditor((s) => s.agentStatus); const set = useEditor;
  const furnishing = useEditor((s) => s.furnishing);
  const [text, setText] = useState('');
  const hasLink = URL_RE.test(text);
  const send = async () => { if (!text.trim() || busy) return; await set.getState().askAgent(text.trim()); setText(''); };
  if (!open) return <button className="sq request-fab" data-testid="request-fab" title="Ask the room" aria-label="Ask" onClick={() => set.getState().setRequestOpen(true)}><I.chat /></button>;
  const tone = status === 'ok' ? (reply?.startsWith('No,') ? 'bad' : 'ok') : status === 'rejected' ? 'bad' : 'info';
  return (
    <div className="request-bar panel" data-testid="request-bar">
      <div className="card-head"><b className="request-title">Ask the room</b><button className="icon-btn" aria-label="Close" onClick={() => set.getState().setRequestOpen(false)}><I.close /></button></div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} autoFocus
        placeholder="Paste a listing link to check if it fits, or ask about the layout"
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }} />
      {!text && !reply && !busy && <div className="suggestions">{SUGGESTIONS.map((s) => <button key={s} className="suggestion" onClick={() => setText(s)}>{s}</button>)}</div>}
      <div className="request-actions">
        {!hasLink && <button className="btn ghost small" disabled={busy || furnishing || !text.trim()} title="Refurnish the room in this style" onClick={() => { void set.getState().furnish(text.trim(), { restyle: true }); setText(''); }}>Restyle</button>}
        <button className="btn primary small" disabled={busy || !text.trim()} onClick={() => void send()}>{busy ? <span className="spinner small" /> : <I.send />}{hasLink ? 'Check fit' : 'Send'}</button>
      </div>
      {(reply || busy || furnishing) && <div className={`reply ${busy || furnishing ? 'info' : tone}`} data-testid="agent-reply">{busy ? (hasLink ? 'Reading the listing and checking your room…' : 'Thinking about your room…') : furnishing ? 'Furnishing your room…' : reply}</div>}
    </div>
  );
}
