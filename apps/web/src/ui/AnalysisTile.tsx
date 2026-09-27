import { formatArea } from '@arp/geometry';
import { useState } from 'react';
import { RentPanel } from './RentPanel';
import { useEditor } from '../store';
import { useCompactEditor } from '../lib/useCompactEditor';
import { I } from './icons';


export function AnalysisTile() {
  const compact = useCompactEditor();
  const v = useEditor((s) => s.validation); const open = useEditor((s) => s.analysisOpen); const units = useEditor((s) => s.units); const set = useEditor;
  const [tab, setTab] = useState<'fit' | 'space'>('fit');
  const [rentOpen, setRentOpen] = useState(false);
  if (!v) return null; const m = v.metrics;
  const status = m.conflicts ? `${m.conflicts} conflict${m.conflicts === 1 ? '' : 's'}` : 'Everything fits';
  // Phones: one quiet summary line; tap to expand the full card.
  if (compact && !open) return (
    <button className={`panel an-summary ${m.conflicts ? 'has-conflicts' : ''}`} data-testid="analysis" aria-expanded={false} onClick={() => set.getState().setAnalysisOpen(true)}>
      <span className={`status-dot ${m.conflicts ? 'bad' : 'ok'}`} /><span className="an-summary-text"><b>{m.openFloor}% open</b><small>{status}</small></span><I.chevR />
    </button>
  );
  return (
    <><div className={`panel analysis ${open ? 'open' : ''} ${m.conflicts ? 'has-conflicts' : ''}`} data-testid="analysis">
      <div className="card-head">
        <div className="seg an-tabs">{(['fit', 'space'] as const).map((x) => <button key={x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{x === 'fit' ? 'Fit' : 'Space'}</button>)}</div>
        <button className="icon-btn an-more" aria-label={open ? 'Collapse room analysis' : 'Expand room analysis'} onClick={() => set.getState().setAnalysisOpen(!open)}>{open ? <I.close /> : <I.plus />}</button>
      </div>
      {tab === 'fit' && <>
        <div className={`an-status ${m.conflicts ? 'bad' : 'ok'}`}><span className={`status-dot ${m.conflicts ? 'bad' : 'ok'}`} />{status}</div>
        <div className="an-row"><span>Open floor</span><b>{m.openFloor}%</b></div>
        <div className="an-row"><span>Walkability</span><b className={m.walkability === 'Blocked' ? 'bad' : m.walkability === 'Tight' ? 'warn' : ''}>{m.walkability}</b></div>
        <div className="an-row"><span>Largest clear area</span><b>{m.largestFreeRect ? formatArea(m.largestFreeRect.areaM2, units) : '-'}</b></div>
        {m.largestFreeRect && <div className="an-fits">fits {m.largestFreeRect.fits}</div>}
        {open && (
          <div className="an-list">
            <div className="an-row"><span>Reachable storage</span><b>{m.reachableStorage}%</b></div>
            {v.violations.map((x, k) => <div key={k} className={`an-v ${x.severity}`}>{x.message}</div>)}
          </div>
        )}
      </>}
      {tab === 'space' && <>
        <div className="an-row"><span>Open floor</span><b>{m.openFloor}%</b></div>
        <div className="an-row"><span>Largest clear</span><b>{m.largestFreeRect ? formatArea(m.largestFreeRect.areaM2, units) : '-'}</b></div>
        <div className="an-row"><span>Storage reach</span><b>{m.reachableStorage}%</b></div>
        <div className="an-fits">Room area is measured from the scan for rent checks.</div>
      </>}
      <button className="an-link" onClick={() => setRentOpen(true)}><span>Rent &amp; costs</span><I.chevR /></button>
    </div>
    {rentOpen && <RentPanel onClose={() => setRentOpen(false)} />}</>
  );
}
