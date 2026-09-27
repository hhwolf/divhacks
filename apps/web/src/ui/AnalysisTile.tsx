import { formatArea } from '@arp/geometry';
import { useState } from 'react';
import { useEditor } from '../store';
import { useCompactEditor } from '../lib/useCompactEditor';


export function AnalysisTile() {
  const compact = useCompactEditor();
  const v = useEditor((s) => s.validation); const open = useEditor((s) => s.analysisOpen); const units = useEditor((s) => s.units); const set = useEditor;
  const [tab, setTab] = useState<'fit' | 'space'>('fit');
  if (!v) return null; const m = v.metrics;
  return (
    <div className={`analysis ${open ? 'open' : ''} ${m.conflicts ? 'has-conflicts' : ''}`} data-testid="analysis">
      <div className="an-tabs">
        {(['fit', 'space'] as const).map((x) => <button key={x} className={tab === x ? 'on' : ''} onClick={() => { setTab(x); if (compact) set.getState().setAnalysisOpen(!open || tab !== x); }}>{x}</button>)}
        <button className="an-more" aria-label={open ? "Collapse room analysis" : "Expand room analysis"} onClick={() => set.getState().setAnalysisOpen(!open)}>{open ? '-' : '+'}</button>
      </div>
      {tab === 'fit' && <>
        <div className="an-row"><span>Open floor</span><b>{m.openFloor}%</b></div>
        <div className="an-row"><span>Conflicts</span><b className={m.conflicts ? 'bad' : ''}>{m.conflicts}</b></div>
        <div className="an-row"><span>Walkability</span><b className={m.walkability === 'Blocked' ? 'bad' : m.walkability === 'Tight' ? 'warn' : ''}>{m.walkability}</b></div>
        <div className="an-row"><span>Free area</span><b>{m.largestFreeRect ? formatArea(m.largestFreeRect.areaM2, units) : '-'}</b></div>
        {m.largestFreeRect && <div className="an-fits">fits {m.largestFreeRect.fits}</div>}
        {open && (
          <div className="an-list">
            <div className="an-row"><span>Reachable storage</span><b>{m.reachableStorage}%</b></div>
            {v.violations.length === 0 ? <div className="an-ok">No conflicts. Everything fits.</div> : v.violations.map((x, k) => <div key={k} className={`an-v ${x.severity}`}>{x.message}</div>)}
          </div>
        )}
      </>}
      {tab === 'space' && <>
        <div className="an-row"><span>Open floor</span><b>{m.openFloor}%</b></div>
        <div className="an-row"><span>Largest clear</span><b>{m.largestFreeRect ? formatArea(m.largestFreeRect.areaM2, units) : '-'}</b></div>
        <div className="an-row"><span>Storage reach</span><b>{m.reachableStorage}%</b></div>
        <div className="an-fits">Room area is measured from the scan for rent checks.</div>
      </>}
    </div>
  );
}
