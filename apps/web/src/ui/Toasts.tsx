import { useEditor } from '../store';
export function Toasts() {
  const toasts = useEditor((s) => s.toasts); const saveState = useEditor((s) => s.saveState); const validation = useEditor((s) => s.validation);
  return (
    <div className="toasts">
      {saveState === 'blocked' && <div className="toast error" data-testid="blocked">Can’t save: {validation?.violations.filter((v) => v.rule === 'bounds' || v.rule === 'overlap')[0]?.message ?? 'fix the red items first'}</div>}
      {saveState === 'error' && <div className="toast error">Save failed — retrying on next change</div>}
      {toasts.map((t) => <div key={t.id} className={`toast ${t.kind} ${t.action ? 'has-action' : ''}`}>{t.text}{t.action && <button onClick={() => { t.action?.run(); useEditor.getState().dismissToast(t.id); }}>{t.action.label}</button>}</div>)}
    </div>
  );
}
