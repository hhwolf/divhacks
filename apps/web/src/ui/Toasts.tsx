import { useEditor } from '../store';
export function Toasts() {
  const toasts = useEditor((s) => s.toasts); const saveState = useEditor((s) => s.saveState); const validation = useEditor((s) => s.validation);
  return (
    <div className="toasts">
      {saveState === 'blocked' && <div className="toast error" data-testid="blocked">Can’t save: {validation?.violations.filter((v) => v.rule === 'bounds' || v.rule === 'overlap')[0]?.message ?? 'fix the red items first'}</div>}
      {saveState === 'error' && <div className="toast error">Save failed — retrying on next change</div>}
      {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>)}
    </div>
  );
}
