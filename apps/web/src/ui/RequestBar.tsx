import { useEffect, useMemo, useRef, useState } from 'react';
import { useEditor } from '../store';
import { I } from './icons';

type AssistMode = 'plan' | 'add' | 'clear' | 'protect' | 'compare';

const PROMPTS: Record<AssistMode, { label: string; placeholder: string; questions: string[] }> = {
  plan: {
    label: 'Plan',
    placeholder: 'Where should my desk go if the bed stays put?',
    questions: ['Can you suggest a new design for a cozy study?', 'Where should my desk go if the bed stays put?', 'What would make this room feel bigger?'],
  },
  add: {
    label: 'Add',
    placeholder: 'Can you add a small desk where it fits best?',
    questions: ['Can you add a small desk where it fits best?', 'Can you add a rug and a floor lamp?', 'Can you add a sofa?'],
  },
  clear: {
    label: 'Clear',
    placeholder: 'Can you make space for yoga without moving my dresser?',
    questions: ['Can you make space for yoga without moving my dresser?', 'Can you remove the plant?', 'Can you remove everything except the bed?'],
  },
  protect: {
    label: 'Protect',
    placeholder: "Can you rearrange this without moving my bed?",
    questions: ["Can you rearrange this without moving my bed?", 'Can you keep the dresser where it is?', 'Can you keep the window area clear?'],
  },
  compare: {
    label: 'Compare',
    placeholder: 'Can you make a second option with more open floor?',
    questions: ['Can you make a second option with more open floor?', 'Can you try a layout for guests?', 'Can you compare a study setup with a lounge setup?'],
  },
};

export function RequestBar() {
  const open = useEditor((s) => s.requestOpen); const busy = useEditor((s) => s.agentBusy); const reply = useEditor((s) => s.agentReply); const set = useEditor;
  const furnishing = useEditor((s) => s.furnishing);
  const room = useEditor((s) => s.room); const threadRoom = useEditor((s) => s.threadRoomId); const all = useEditor((s) => s.agentThread);
  const activeId = useEditor((s) => s.activeId);
  const thread = threadRoom === room?.id ? all : [];
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [thread.length, busy, furnishing]);
  const [text, setText] = useState('');
  const [mode, setMode] = useState<AssistMode>('plan');
  const cfg = useMemo(() => PROMPTS[mode], [mode]);
  const send = async () => { if (!text.trim() || busy) return; await set.getState().askAgent(text.trim()); setText(''); };
  if (!open) return <button className="sq request-fab" data-testid="request-fab" title="Ask the room" aria-label="Ask" onClick={() => set.getState().setRequestOpen(true)}><I.chat /></button>;
  return (
    <div className="request-bar" data-testid="request-bar">
      <div className="request-head"><span>Your designer</span><button className="sq small" aria-label="Close" onClick={() => set.getState().setRequestOpen(false)}><I.close /></button></div>
      <div className="assist-modes">{(Object.keys(PROMPTS) as AssistMode[]).map((m) => <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{PROMPTS[m].label}</button>)}</div>
      {(thread.length > 0 || busy || furnishing) && (
        <div className="chat" data-testid="agent-thread">
          {thread.map((t, i) => (
            <div key={i} className={`chat-turn ${t.role}`} data-testid={t.role === 'designer' && i === thread.length - 1 && !busy && !furnishing ? 'agent-reply' : undefined}>
              <div className="chat-text">{t.text}</div>
              {t.options && t.options.length > 0 && (
                <div className="chat-options">{t.options.map((o) => (
                  <button key={o.layoutId} className={`suggestion ${activeId === o.layoutId ? 'on' : ''}`} title={o.tradeoff} onClick={() => void set.getState().switchLayout(o.layoutId)}>{o.name}</button>
                ))}</div>
              )}
            </div>
          ))}
          {(busy || furnishing) && <div className="chat-turn designer pending">{busy ? 'Thinking about your room…' : 'Furnishing your room…'}</div>}
          <div ref={end} />
        </div>
      )}
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={cfg.placeholder} rows={2} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }} />
      <div className="request-hint">Send furniture links or photos over iMessage; use this assistant for layout changes.</div>
      <div className="request-actions">
        <button className="btn dark small" disabled={busy || furnishing || !text.trim()} onClick={() => { void set.getState().furnish(text.trim(), { restyle: true }); setText(''); }}>Restyle</button>
        <div className="suggestions">{cfg.questions.map((s) => <button key={s} className="suggestion" onClick={() => setText(s)}>{s}</button>)}</div>
        <button className="btn primary small" disabled={busy || !text.trim()} onClick={() => void send()}>{busy ? <span className="spinner small" /> : <I.send />} Send</button>
      </div>
      {reply && thread.length === 0 && !busy && !furnishing && <div className="reply" data-testid="agent-reply">{reply}</div>}
    </div>
  );
}
