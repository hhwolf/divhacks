import { useEditor } from '../store';
import { I } from './icons';

export function QuickActions() {
  const selectedId = useEditor((s) => s.selectedId);
  const item = useEditor((s) => s.items.find((i) => i.id === selectedId));
  const set = useEditor;
  if (!selectedId || !item) return null;
  return (
    <div className="quick-actions" data-testid="quick-actions">
      <button className="sq small" title="Rotate selected item" aria-label="Rotate selected item" disabled={item.locked} onClick={() => set.getState().rotateItem(selectedId)}><I.rotate /></button>
      <button className="sq small danger" title="Delete selected item" aria-label="Delete selected item" disabled={item.locked} onClick={() => set.getState().removeItem(selectedId)}><I.trash /></button>
    </div>
  );
}
