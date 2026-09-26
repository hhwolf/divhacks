import { formatArea } from '@arp/geometry';
import { useState } from 'react';
import type { PaymentPurpose, PaymentQuote, RentAssessment } from '@arp/contracts';
import { useEditor } from '../store';
import { api } from '../lib/api';

export function AnalysisTile() {
  const v = useEditor((s) => s.validation); const open = useEditor((s) => s.analysisOpen); const units = useEditor((s) => s.units); const room = useEditor((s) => s.room); const activeId = useEditor((s) => s.activeId); const set = useEditor;
  const [tab, setTab] = useState<'fit' | 'space' | 'rent'>('fit');
  const [rent, setRent] = useState('1600'); const [zip, setZip] = useState('10027'); const [issues, setIssues] = useState('');
  const [assessment, setAssessment] = useState<RentAssessment | null>(null); const [quote, setQuote] = useState<PaymentQuote | null>(null);
  const [payAmount, setPayAmount] = useState('500'); const [purpose, setPurpose] = useState<PaymentPurpose>('deposit'); const [busy, setBusy] = useState(false);
  if (!v) return null; const m = v.metrics;
  const assess = async () => {
    if (!room) return; setBusy(true); setQuote(null);
    try {
      const res = await api.assessRent({
        roomId: room.id, layoutId: activeId, zip, askingRent: Number(rent), occupancyType: 'private_room',
        declaredIssues: issues.split(',').map((x) => x.trim()).filter(Boolean),
      });
      setAssessment(res.assessment);
    } catch (e) { set.getState().toast(`Rent check failed: ${(e as Error).message}`, 'error'); } finally { setBusy(false); }
  };
  const checkPayment = async () => {
    if (!room) return; setBusy(true);
    try {
      const res = await api.paymentQuote({ purpose, amount: Number(payAmount), rentAmount: assessment?.askingRent ?? Number(rent), roomId: room.id, assessmentId: assessment?.id });
      setQuote(res.quote);
    } catch (e) { set.getState().toast(`Payment check failed: ${(e as Error).message}`, 'error'); } finally { setBusy(false); }
  };
  return (
    <div className={`analysis ${open ? 'open' : ''} ${m.conflicts ? 'has-conflicts' : ''}`} data-testid="analysis">
      <div className="an-tabs">
        {(['fit', 'space', 'rent'] as const).map((x) => <button key={x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{x}</button>)}
        <button className="an-more" onClick={() => set.getState().setAnalysisOpen(!open)}>{open ? '-' : '+'}</button>
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
      {tab === 'rent' && (
        <div className="rent-mini">
          <div className="rent-grid">
            <label>ZIP<input value={zip} inputMode="numeric" onChange={(e) => setZip(e.target.value)} /></label>
            <label>Rent<input value={rent} inputMode="numeric" onChange={(e) => setRent(e.target.value)} /></label>
          </div>
          <input className="rent-wide" value={issues} onChange={(e) => setIssues(e.target.value)} placeholder="issues: rats, leak, bad faucet" />
          <button className="btn primary small" disabled={busy || !room || !Number(rent)} onClick={() => void assess()}>{busy ? 'Checking...' : 'Rent check'}</button>
          {assessment && (
            <div className={`rent-result ${assessment.legalFlags.length ? 'warn' : ''}`}>
              <div className="an-row"><span>Scanned</span><b>{assessment.spaceQuality.floorAreaSqFt} sq ft</b></div>
              <div className="an-row"><span>Fair range</span><b>${assessment.estimatedFairRange.low}-${assessment.estimatedFairRange.high}</b></div>
              <div className="an-row"><span>Vs midpoint</span><b className={assessment.deltaVsMid > 0 ? 'bad' : ''}>{assessment.deltaVsMid > 0 ? '+' : ''}${Math.round(assessment.deltaVsMid)}</b></div>
              <div className="an-fits">{assessment.confidence} confidence · condition {assessment.spaceQuality.conditionScore}/100</div>
              {open && assessment.explanation.slice(0, 3).map((x) => <div className="an-v" key={x}>{x}</div>)}
              {assessment.legalFlags.map((x) => <div className="an-v warning" key={x}>{x}</div>)}
            </div>
          )}
          <div className="rent-grid pay">
            <select value={purpose} onChange={(e) => setPurpose(e.target.value as PaymentPurpose)}><option value="deposit">deposit</option><option value="application_fee">app fee</option><option value="rent_payment">rent</option><option value="furniture_purchase">furniture</option></select>
            <input value={payAmount} inputMode="numeric" onChange={(e) => setPayAmount(e.target.value)} />
          </div>
          <button className="btn dark small" disabled={busy || !Number(payAmount)} onClick={() => void checkPayment()}>Safe payment check</button>
          {quote && <div className={`reply pay ${quote.status === 'blocked' ? 'blocked' : ''}`}>{quote.status.toUpperCase()}: {quote.guardrails[quote.guardrails.length - 1]}</div>}
        </div>
      )}
    </div>
  );
}
