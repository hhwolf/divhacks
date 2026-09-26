import { useState } from 'react';
import { useEditor } from '../store';
import { I } from './icons';

export function RequestBar() {
  const open = useEditor((s) => s.requestOpen); const busy = useEditor((s) => s.agentBusy); const reply = useEditor((s) => s.agentReply); const set = useEditor;
  const [text, setText] = useState('');
  const send = async () => { if (!text.trim() || busy) return; await set.getState().askAgent(text.trim()); setText(''); };
  const suggestions = ['make space for yoga, keep my dresser', 'create a reading corner near the window', "place the desk near the window", "don't move my bed"];
  if (!open) return <button className="sq request-fab" data-testid="request-fab" title="Ask the room" aria-label="Ask" onClick={() => set.getState().setRequestOpen(true)}><I.chat /></button>;
  return (
    <div className="request-bar" data-testid="request-bar">
      <div className="request-head"><span>Arrange the room</span><button className="sq small" aria-label="Close" onClick={() => set.getState().setRequestOpen(false)}><I.close /></button></div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="make space for yoga, keep my dresser" rows={2} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }} />
      <div className="request-hint">Send furniture links or photos over iMessage; use this assistant for layout changes.</div>
      <div className="request-actions">
        <div className="suggestions">{suggestions.map((s) => <button key={s} className="suggestion" onClick={() => setText(s)}>{s}</button>)}</div>
        <button className="btn primary small" disabled={busy || !text.trim()} onClick={() => void send()}>{busy ? <span className="spinner small" /> : <I.send />} Send</button>
      </div>
      {(reply || busy) && <div className="reply" data-testid="agent-reply">{busy ? 'Thinking about your room…' : reply}</div>}
    </div>
  );
}
