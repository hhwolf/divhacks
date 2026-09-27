import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import type { PaymentRecord } from '@arp/contracts';
import { api } from '../lib/api';
import { dollars } from './PaymentPanel';

export function PaymentPage() {
  const { id } = useParams(); const [payment, setPayment] = useState<PaymentRecord | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const refresh = () => { if (id) void api.payment(id).then((r) => { if (active) setPayment(r.payment); }).catch((e: Error) => { if (active) setError(e.message); }); };
    refresh(); const timer = setInterval(refresh, 3000);
    return () => { active = false; clearInterval(timer); };
  }, [id]);
  const simulate = async (outcome: string) => { if (!id) return; setBusy(true); setError(''); try { setPayment((await api.simulatePayment(id, outcome)).payment); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <main className="payment-page"><section className="housing-section">
    <span className="eyebrow">FitCheck</span><h1>Payment status</h1>
    {error && <p className="err" role="alert">{error}</p>}
    {payment && <><p className="notice">{payment.mode === 'demo' ? 'Offline simulation. No Stripe transaction or money transfer occurred.' : 'Stripe test payment. No live charge.'}</p>
      <h2>{dollars(payment.amountCents)} · {payment.status}</h2><p>{payment.purpose.replaceAll('_', ' ')} · {payment.rentalPeriod}</p>
      <p>Reference: {payment.id}<br />Updated: {new Date(payment.updatedAt).toLocaleString()}</p>
      {['created', 'pending'].includes(payment.status) && <p>Payment is not confirmed. Returning from checkout does not establish payment success.</p>}
      {payment.refundedCents > 0 && <p>Refunded: {dollars(payment.refundedCents)}</p>}
      {payment.mode === 'demo' && payment.status === 'pending' && <div className="housing-actions"><button className="btn primary" disabled={busy} onClick={() => void simulate('succeeded')}>Simulate successful payment</button><button className="btn" disabled={busy} onClick={() => void simulate('failed')}>Simulate failure</button><button className="btn" disabled={busy} onClick={() => void simulate('canceled')}>Cancel simulation</button></div>}
      {payment.mode === 'demo' && payment.status === 'succeeded' && <div className="housing-actions"><button className="btn" disabled={busy} onClick={() => void simulate('refunded')}>Simulate refund</button><button className="btn" disabled={busy} onClick={() => void simulate('disputed')}>Simulate dispute</button></div>}
      <button className="btn" onClick={async () => { const r = await api.room(payment.roomId); const layout = r.layouts.find((l) => l.isCurrent); location.assign(layout ? `/layout/${layout.id}` : '/'); }}>Back to room</button>
    </>}
    {!payment && !error && <p>Loading payment…</p>}
  </section></main>;
}
