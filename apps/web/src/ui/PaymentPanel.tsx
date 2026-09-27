import { useEffect, useState } from 'react';
import type { PaymentPurpose, PaymentQuote, PaymentRecord, Tenancy } from '@arp/contracts';
import { api } from '../lib/api';

export const dollars = (cents: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);

export function PaymentPanel({ roomId }: { roomId: string }) {
  const [tenancy, setTenancy] = useState<Tenancy | null>(null); const [quote, setQuote] = useState<PaymentQuote | null>(null);
  const [purpose, setPurpose] = useState<PaymentPurpose>('deposit'); const [amount, setAmount] = useState('500'); const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [records, setRecords] = useState<PaymentRecord[]>([]); const [confirmed, setConfirmed] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { void api.payments(roomId).then((r) => setRecords(r.payments)).catch((e: Error) => setError(e.message)); }, [roomId]);
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(''); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const invalidate = () => { setQuote(null); setConfirmed(false); };
  return <section className="housing-section" aria-label="Payments">
    <h3>Review payment</h3>
    <p className="notice">Test payments only. Live charges are disabled. Passing these checks does not guarantee a legitimate recipient.</p>
    {!tenancy ? <><p>Start with a fictional $1,600 tenancy and an $18 documented screening cost. This does not verify your actual lease or landlord.</p><button className="btn" disabled={busy} onClick={() => void run(async () => setTenancy((await api.seedTenancy(roomId)).tenancy))}>Load test tenancy</button></> : <>
      <div className="housing-summary"><b>{tenancy.recipientName}</b><span>{tenancy.mode === 'demo' ? 'Offline demo · no Stripe transaction' : 'Stripe test mode'}</span><span>Documented fixture rent: {dollars(tenancy.monthlyRentCents)}/month</span></div>
      <form onSubmit={(e) => { e.preventDefault(); invalidate(); void run(async () => setQuote((await api.paymentQuote({ tenancyId: tenancy.id, purpose, amountCents: Math.round(Number(amount) * 100), rentalPeriod: period })).quote)); }}>
        <div className="housing-grid">
          <label>Payment purpose<select value={purpose} onChange={(e) => { setPurpose(e.target.value as PaymentPurpose); invalidate(); }}><option value="deposit">Security deposit</option><option value="rent_payment">Rent</option><option value="screening_fee">Documented screening reimbursement</option><option value="application_fee">Application processing fee</option><option value="broker_fee">Broker fee</option><option value="other">Other charge</option></select></label>
          <label>Amount (USD)<input type="number" min="0.01" max="1000000" step="0.01" required value={amount} onChange={(e) => { setAmount(e.target.value); invalidate(); }} /></label>
          <label>Rental period<input type="month" required value={period} onChange={(e) => { setPeriod(e.target.value); invalidate(); }} /></label>
        </div>
        <button className="btn" disabled={busy}>Review payment</button>
      </form>
    </>}
    {quote && <article className={`housing-quote ${quote.decision}`} aria-label="Payment quote">
      <span className="eyebrow">{quote.mode === 'demo' ? 'Demo quote' : 'Test payment quote'} · {quote.decision.replace('_', ' ')}</span>
      <h3>{dollars(quote.amountCents)} to {quote.recipientName}</h3>
      <p>{quote.purpose.replaceAll('_', ' ')} · {quote.rentalPeriod} · USD · platform fee $0.00</p>
      <ul>{quote.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      <p>{quote.contact}<br />{quote.refundPolicy}</p>
      <small>Expires {new Date(quote.expiresAt).toLocaleString()} · Rules {quote.ruleVersion}</small>
      <div className="source-links">{quote.ruleSources.map((url, i) => <a key={url} href={url} target="_blank" rel="noreferrer">{['NY tenant guidance', 'Screening fee law', 'NYC broker rules'][i]}</a>)}</div>
      {quote.decision === 'ready' && <><label className="check"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I reviewed the recipient, purpose, amount and test-only terms.</label>
        <button className="btn primary" disabled={!confirmed || busy} onClick={() => void run(async () => {
          const result = await api.paymentCheckout(quote.id);
          if (result.url) location.assign(result.url); else location.assign(`/payment/${result.payment.id}`);
        })}>{quote.mode === 'demo' ? 'Continue to demo checkout' : 'Continue to Stripe test checkout'}</button></>}
    </article>}
    {error && <p className="err" role="alert">{error}</p>}
    <h3>Payment history</h3>
    {records.length ? records.map((p) => <a className="housing-record" href={`/payment/${p.id}`} key={p.id}><b>{dollars(p.amountCents)} · {p.purpose.replaceAll('_', ' ')}</b><span>{p.mode === 'demo' ? 'Demo' : 'Test payment'} · {p.status} · {p.rentalPeriod}</span></a>) : <p>No payments in this room.</p>}
  </section>;
}
