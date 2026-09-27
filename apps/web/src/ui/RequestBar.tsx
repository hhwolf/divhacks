import { useMemo, useState } from 'react';
import { useEditor } from '../store';
import { I } from './icons';

type AssistMode = 'plan' | 'add' | 'clear' | 'protect' | 'compare';

const PROMPTS: Record<AssistMode, { label: string; placeholder: string; questions: string[] }> = {
  plan: {
    label: 'Plan',
    placeholder: 'Where should my desk go if the bed stays put?',
    questions: ['Where should my desk go if the bed stays put?', 'Can you create a reading corner near the window?', 'Can you make this room feel more open?'],
  },
  add: {
    label: 'Add',
    placeholder: 'Can you add a small desk where it fits best?',
    questions: ['Can you add a small desk where it fits best?', 'Can you add a floor lamp for a reading corner?', 'Can you add a plant without blocking the door?'],
  },
  clear: {
    label: 'Clear',
    placeholder: 'Can you make space for yoga without moving my dresser?',
    questions: ['Can you make space for yoga without moving my dresser?', 'Can you clear a path from the door to the desk?', 'Can you open up the center of the room?'],
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
  const [text, setText] = useState('');
  const [mode, setMode] = useState<AssistMode>('plan');
  const cfg = useMemo(() => PROMPTS[mode], [mode]);
  const send = async () => { if (!text.trim() || busy) return; await set.getState().askAgent(text.trim()); setText(''); };
  if (!open) return <button className="sq request-fab" data-testid="request-fab" title="Ask the room" aria-label="Ask" onClick={() => set.getState().setRequestOpen(true)}><I.chat /></button>;
  return (
    <div className="request-bar" data-testid="request-bar">
      <div className="request-head"><span>Arrange the room</span><button className="sq small" aria-label="Close" onClick={() => set.getState().setRequestOpen(false)}><I.close /></button></div>
      <div className="assist-modes">{(Object.keys(PROMPTS) as AssistMode[]).map((m) => <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{PROMPTS[m].label}</button>)}</div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={cfg.placeholder} rows={2} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }} />
      <div className="request-hint">Send furniture links or photos over iMessage; use this assistant for layout changes.</div>
      <div className="request-actions">
        <div className="suggestions">{cfg.questions.map((s) => <button key={s} className="suggestion" onClick={() => setText(s)}>{s}</button>)}</div>
        <button className="btn primary small" disabled={busy || !text.trim()} onClick={() => void send()}>{busy ? <span className="spinner small" /> : <I.send />} Send</button>
      </div>
      {(reply || busy) && <div className="reply" data-testid="agent-reply">{busy ? 'Thinking about your room…' : reply}</div>}
    </div>
  );
}
