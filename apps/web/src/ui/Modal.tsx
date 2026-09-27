import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return createPortal(<dialog ref={ref} className="housing-dialog" aria-label={title} onCancel={(e) => { e.preventDefault(); onClose(); }}>
    <header className="housing-header"><div><span className="eyebrow">FitCheck</span><h2>{title}</h2></div><button className="btn" aria-label={`Close ${title}`} onClick={onClose}>Close ×</button></header>
    {children}
  </dialog>, document.body);
}
