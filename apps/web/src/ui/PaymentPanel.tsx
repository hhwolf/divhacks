import { useEffect, useState } from 'react';
import type { PaymentPurpose, PaymentQuote, PaymentRecord, Tenancy } from '@arp/contracts';
import { api } from '../lib/api';
import { nycDate } from '../lib/dates';

export const dollars = (cents: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);

export function PaymentPanel({ roomId }: { roomId: string }) {
  const [tenancy, setTenancy] = useState<Tenancy | null>(null); const [quote, setQuote] = useState<PaymentQuote | null>(null);
  const [purpose, setPurpose] = useState<PaymentPurpose>('deposit'); const [amount, setAmount] = useState('500'); const [period] = useState(nycDate().slice(0, 7));
  const [records, setRecords] = useState<PaymentRecord[]>([]); const [confirmed, setConfirmed] = useState(false); const [busy, setBusy] = useState(true); const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError('');
    void Promise.all([api.payments(roomId), api.seedTenancy(roomId)])
      .then(([history, seeded]) => { if (active) { setRecords(history.payments); setTenancy(seeded.tenancy); } })
      .catch((e: Error) => { if (active) setError(e.message); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [roomId]);
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(''); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const invalidate = () => { setQuote(null); setConfirmed(false); };
  return <section className="housing-section" aria-label="Payments">
    <h3>Test payment</h3>
    <p className="notice">Demo/test only. This does not verify a real landlord or authorize a real charge.</p>
    {!tenancy ? <p>{busy ? 'Preparing payment review...' : 'Payment review is unavailable.'}</p> : <>
      <div className="housing-summary"><b>{tenancy.recipientName}</b><span>{tenancy.mode === 'demo' ? 'Offline demo' : 'Stripe test mode'}</span><span>Fixture rent: {dollars(tenancy.monthlyRentCents)}/month</span></div>
      <form onSubmit={(e) => { e.preventDefault(); invalidate(); void run(async () => setQuote((await api.paymentQuote({ tenancyId: tenancy.id, purpose, amountCents: Math.round(Number(amount) * 100), rentalPeriod: period })).quote)); }}>
        <div className="housing-grid">
          <label>Purpose<select value={purpose} onChange={(e) => { setPurpose(e.target.value as PaymentPurpose); invalidate(); }}><option value="deposit">Security deposit</option><option value="rent_payment">Rent</option><option value="screening_fee">Screening reimbursement</option><option value="application_fee">Application fee</option><option value="broker_fee">Broker fee</option><option value="other">Other charge</option></select></label>
          <label>Amount (USD)<input type="number" min="0.01" max="1000000" step="0.01" required value={amount} onChange={(e) => { setAmount(e.target.value); invalidate(); }} /></label>
        </div>
        <button className="btn" disabled={busy}>Review payment</button>
      </form>
    </>}
    {quote && <article className={`housing-quote ${quote.decision}`} aria-label="Payment quote">
      <span className="eyebrow">{quote.mode === 'demo' ? 'Demo quote' : 'Test payment quote'} · {quote.decision.replace('_', ' ')}</span>
      <h3>{dollars(quote.amountCents)} to {quote.recipientName}</h3>
      <p>{quote.purpose.replaceAll('_', ' ')} · {quote.rentalPeriod} · USD · platform fee $0.00</p>
      <ul>{quote.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      {quote.decision === 'ready' && <><label className="check"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I reviewed the recipient, purpose, amount and test-only terms.</label>
        <button className="btn primary" disabled={!confirmed || busy} onClick={() => void run(async () => {
          const result = await api.paymentCheckout(quote.id);
          if (result.url) location.assign(result.url); else location.assign(`/payment/${result.payment.id}`);
        })}>{quote.mode === 'demo' ? 'Continue to demo checkout' : 'Continue to Stripe test checkout'}</button></>}
    </article>}
    {error && <p className="err" role="alert">{error}</p>}
    {records.length ? <details><summary>Payment history</summary>{records.map((p) => <a className="housing-record" href={`/payment/${p.id}`} key={p.id}><b>{dollars(p.amountCents)} · {p.purpose.replaceAll('_', ' ')}</b><span>{p.mode === 'demo' ? 'Demo' : 'Test payment'} · {p.status} · {p.rentalPeriod}</span></a>)}</details> : null}
  </section>;
}
