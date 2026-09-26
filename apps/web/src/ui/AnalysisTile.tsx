import { formatArea } from '@arp/geometry';
import { useEditor } from '../store';
export function AnalysisTile() {
  const v = useEditor((s) => s.validation); const open = useEditor((s) => s.analysisOpen); const units = useEditor((s) => s.units); const set = useEditor;
  if (!v) return null; const m = v.metrics;
  return (
    <button className={`analysis ${open ? 'open' : ''} ${m.conflicts ? 'has-conflicts' : ''}`} data-testid="analysis" onClick={() => set.getState().setAnalysisOpen(!open)}>
      <div className="an-row"><span>Open floor</span><b>{m.openFloor}%</b></div>
      <div className="an-row"><span>Conflicts</span><b className={m.conflicts ? 'bad' : ''}>{m.conflicts}</b></div>
      <div className="an-row"><span>Walkability</span><b className={m.walkability === 'Blocked' ? 'bad' : m.walkability === 'Tight' ? 'warn' : ''}>{m.walkability}</b></div>
      <div className="an-row"><span>Free area</span><b>{m.largestFreeRect ? formatArea(m.largestFreeRect.areaM2, units) : '–'}</b></div>
      {m.largestFreeRect && <div className="an-fits">fits {m.largestFreeRect.fits}</div>}
      {open && (
        <div className="an-list">
          <div className="an-row"><span>Reachable storage</span><b>{m.reachableStorage}%</b></div>
          {v.violations.length === 0 ? <div className="an-ok">No conflicts. Everything fits.</div> : v.violations.map((x, k) => <div key={k} className={`an-v ${x.severity}`}>{x.message}</div>)}
        </div>
      )}
    </button>
  );
}
