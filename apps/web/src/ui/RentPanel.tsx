import { useEffect, useState } from 'react';
import type { AddressCandidate, HousingProfile, RentAssessment, RentRange } from '@arp/contracts';
import { useEditor } from '../store';
import { api } from '../lib/api';
import { externalUrl } from '../lib/auth';
import { Modal } from './Modal';
import { ConditionsPanel } from './ConditionsPanel';
import { ComparableEditor } from './ComparableEditor';
import { PaymentPanel, dollars } from './PaymentPanel';

function Range({ range }: { range: RentRange | null }) {
  return range ? <><strong className="range-value">{dollars(range.low * 100)}-{dollars(range.high * 100)}</strong><p>Median asking rent: <b>{dollars(range.mid * 100)}/month</b></p></> : <strong>Insufficient comparable data</strong>;
}

export function RentPanel({ onClose }: { onClose: () => void }) {
  const room = useEditor((s) => s.room)!; const activeId = useEditor((s) => s.activeId); const furniture = useEditor((s) => s.furniture); const items = useEditor((s) => s.items);
  const poly = room.skeleton.floorPolygon; const scanned = Math.round(Math.abs(poly.reduce((sum, [x, z], i) => sum + x * poly[(i + 1) % poly.length][1] - poly[(i + 1) % poly.length][0] * z, 0)) / 2 * 10.7639104167 * 10) / 10;
  const [profile, setProfile] = useState<HousingProfile>({ roomId: room.id, askingRent: 1600, occupancyType: 'private_room', scanCoverage: 'room', measurementConfirmed: false, confirmedAreaSqFt: scanned, leaseMonths: 12, utilitiesIncluded: false, furnished: false, conditions: [], comparables: [], dataMode: room.source === 'sample' ? 'demo' : 'real', zip: '10027' });
  const [assessment, setAssessment] = useState<RentAssessment | null>(null); const [dirty, setDirty] = useState(false); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const [candidates, setCandidates] = useState<AddressCandidate[]>([]); const [detailsOpen, setDetailsOpen] = useState(false); const [paymentOpen, setPaymentOpen] = useState(false);
  const [utilities, setUtilities] = useState('0'); const [deposit, setDeposit] = useState('1600'); const [moving, setMoving] = useState('0');
  const [benchmarks, setBenchmarks] = useState<{ source: string; value: number; label: string; observedAt: string; sourceUrl: string }[]>([]);
  useEffect(() => { let active = true; void Promise.all([api.housingProfile(room.id).catch(() => ({ profile: null })), api.latestAssessment(room.id).catch(() => null)]).then(([p, a]) => { if (active) { if (p.profile) setProfile(p.profile); if (a?.assessment) setAssessment(a.assessment); } }).catch((e: Error) => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [room.id]);
  const change = (patch: Partial<HousingProfile>) => { setProfile((p) => ({ ...p, ...patch })); setDirty(true); setMessage(''); };
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(''); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const compare = () => run(async () => { await api.saveHousingProfile(profile); const r = await api.assessRent({ ...profile, layoutId: activeId }); setAssessment(r.assessment); setBenchmarks(r.benchmarks); setDirty(false); setMessage('Comparison updated.'); });
  const furnishing = items.reduce((sum, i) => sum + (furniture[i.furnitureId]?.price ?? 0) + (furniture[i.furnitureId]?.deliveryCost ?? 0), 0);
  const unpriced = items.filter((i) => furniture[i.furnitureId]?.price == null).length;
  return <Modal title="Rent & costs" onClose={onClose}>
    <p className="notice">{profile.dataMode === 'demo' ? 'Demo data. Synthetic listings and building records.' : 'Real records stay labeled by source; unavailable sources stay unavailable.'}</p>
    {loading ? <p>Loading rental details...</p> : <>
      <section className="housing-section">
        <h3>Quick rent check</h3>
        <p>Physical floor area from this {room.source === 'scan' ? 'scan' : 'room polygon'}: <b>{scanned} sq ft</b>. Moving furniture changes usable space, not the measured rent area.</p>
        <div className="housing-grid">
          <label>Monthly rent (USD)<input type="number" min="1" value={profile.askingRent} onChange={(e) => change({ askingRent: Number(e.target.value) })} /></label>
          <label>Confirmed area (sq ft)<input type="number" min="1" max="100000" step="0.1" value={profile.confirmedAreaSqFt ?? scanned} onChange={(e) => change({ confirmedAreaSqFt: Number(e.target.value), measurementConfirmed: false })} /></label>
          <label>ZIP<input inputMode="numeric" maxLength={5} value={profile.zip ?? ''} onChange={(e) => change({ zip: e.target.value || null })} /></label>
          <label>Renting<select value={profile.occupancyType} onChange={(e) => change({ occupancyType: e.target.value as HousingProfile['occupancyType'], measurementConfirmed: false })}><option value="private_room">Private room</option><option value="shared_room">Shared room</option><option value="studio">Studio apartment</option><option value="whole_apartment">Whole apartment</option></select></label>
        </div>
        <label className="check"><input type="checkbox" checked={profile.measurementConfirmed} onChange={(e) => change({ measurementConfirmed: e.target.checked })} />I reviewed the scanned area and what I am renting.</label>
        <div className="housing-actions"><button className="btn" disabled={busy} onClick={() => void run(async () => { await api.saveHousingProfile(profile); setDirty(false); setMessage('Rent details saved.'); })}>Save</button><button className="btn primary" disabled={busy || !profile.measurementConfirmed} onClick={() => void compare()}>Compare rents</button></div>
      </section>
      {assessment && <section className="housing-section" aria-label="Rent results">
        {dirty && <p className="notice">Details changed. Update the comparison to use the latest entries.</p>}
        <span className="eyebrow">{assessment.status === 'demo' ? 'Demo data' : 'Comparable asking rents'} · {new Date(assessment.createdAt).toLocaleDateString()}</span>
        <h3>Comparable asking-rent range</h3>
        <p>The middle half of qualifying listings; not a legal rent determination.</p>
        <div className="housing-grid"><article className="housing-result"><h4>Location and size</h4><Range range={assessment.estimatedFairRange} /><p>{assessment.comparables.length} qualifying listings</p></article><article className="housing-result"><h4>Condition matched</h4><Range range={assessment.conditionMatchedRange} /><p>{assessment.conditionComparableIds.length} similar-condition listings</p></article></div>
        {assessment.notices.map((n) => <p className="notice" key={n}>{n}</p>)}
      </section>}
      <details open={detailsOpen} onToggle={(e) => setDetailsOpen(e.currentTarget.open)}>
        <summary>More details</summary>
        <section className="housing-section">
          <h3>Rental details</h3>
          <div className="housing-grid">
            <label>Data source<select value={profile.dataMode} onChange={(e) => { change({ dataMode: e.target.value as HousingProfile['dataMode'], address: '', bbl: null, bin: null, latitude: null, longitude: null, comparables: [] }); setCandidates([]); }}><option value="demo">Demo data</option><option value="real">Real records / my listings</option></select></label>
            <label>Measurement covers<select value={profile.scanCoverage} onChange={(e) => change({ scanCoverage: e.target.value as HousingProfile['scanCoverage'], measurementConfirmed: false })}><option value="room">This room only</option><option value="whole_apartment">Entire apartment</option></select></label>
            <label>Lease length (months)<input type="number" min="1" max="120" value={profile.leaseMonths} onChange={(e) => change({ leaseMonths: Number(e.target.value) })} /></label>
            <label>Apartment / unit<input value={profile.apartment ?? ''} onChange={(e) => change({ apartment: e.target.value })} /></label>
            {['studio', 'whole_apartment'].includes(profile.occupancyType) && <><label>Bedrooms<input type="number" min="0" value={profile.bedrooms ?? ''} onChange={(e) => change({ bedrooms: e.target.value === '' ? null : Number(e.target.value) })} /></label><label>Bathrooms<input type="number" min="0" step="0.5" value={profile.bathrooms ?? ''} onChange={(e) => change({ bathrooms: e.target.value === '' ? null : Number(e.target.value) })} /></label></>}
          </div>
          <div className="housing-actions"><label className="check"><input type="checkbox" checked={profile.utilitiesIncluded} onChange={(e) => change({ utilitiesIncluded: e.target.checked })} />Utilities included</label><label className="check"><input type="checkbox" checked={profile.furnished} onChange={(e) => change({ furnished: e.target.checked })} />Furnished</label></div>
          <label>Street address<input value={profile.address ?? ''} onChange={(e) => { change({ address: e.target.value, latitude: null, longitude: null, bbl: null, bin: null }); setCandidates([]); }} placeholder="Optional NYC address" /></label>
          <button className="btn" disabled={busy || (profile.address ?? '').length < 3} onClick={() => void run(async () => { const result = await api.addresses(profile.address!, profile.dataMode); setCandidates(result.candidates); setMessage(result.source.note); })}>Find address</button>
          {candidates.length > 0 && <fieldset><legend>Choose the matching property</legend>{candidates.map((c, i) => <button className="housing-record" key={i} onClick={() => { change({ address: c.label, bbl: c.bbl, bin: c.bin, latitude: c.latitude, longitude: c.longitude }); setCandidates([]); }}>{c.label}</button>)}</fieldset>}
        </section>
        <ConditionsPanel roomId={room.id} value={profile.conditions} onChange={(conditions) => change({ conditions })} />
        {assessment && <section className="housing-section">
          <h3>Sources</h3>
          <div className="comparable-list">{assessment.comparables.map((c) => <article className="housing-record" key={c.id}><b>{dollars(c.rentCents)}/month · {c.areaSqFt} sq ft</b><span>{c.provenance === 'fixture' ? 'Demo data' : c.provenance === 'user' ? 'User reported' : 'RentCast; reviewed by user'} · observed {c.observedAt}</span>{c.provenance !== 'fixture' && <a href={externalUrl(c.sourceUrl)} target="_blank" rel="noreferrer">Source listing</a>}</article>)}</div>
          {assessment.buildingRecords.length ? assessment.buildingRecords.map((r) => <article className="housing-record" key={r.id}><b>{r.demo ? 'Demo data' : 'Public record'} · {r.scope} · {r.kind}</b><span>{r.summary}</span><span>{r.observedAt} · {r.status}</span><a href={externalUrl(r.sourceUrl)} target="_blank" rel="noreferrer">Official source</a></article>) : <p>No property records returned.</p>}
          <details><summary>Method & source availability</summary><p>Calculation: {assessment.methodVersion}</p>{assessment.sources.map((s, i) => <article className="housing-record" key={i}><b>{s.source} · {s.status}</b><span>{s.note}</span><small>Retrieved {s.retrievedAt}</small><a href={externalUrl(s.url)} target="_blank" rel="noreferrer">Source documentation</a></article>)}</details>
        </section>}
        <ComparableEditor profile={profile} onChange={(comparables) => change({ comparables })} />
        <section className="housing-section"><h3>Budget notes</h3><div className="housing-grid"><label>Monthly utilities outside rent<input type="number" min="0" value={utilities} onChange={(e) => setUtilities(e.target.value)} /></label><label>Planned deposit<input type="number" min="0" value={deposit} onChange={(e) => setDeposit(e.target.value)} /></label><label>Moving costs<input type="number" min="0" value={moving} onChange={(e) => setMoving(e.target.value)} /></label></div><p>Monthly: <b>{dollars((profile.askingRent + Number(utilities)) * 100)}</b>. Move-in estimate with priced furniture: <b>{dollars((profile.askingRent + Number(deposit) + Number(moving) + furnishing) * 100)}</b>. {unpriced > 0 && `${unpriced} items have no price and are excluded.`}</p>{benchmarks.length ? benchmarks.map((b, i) => <p key={i}>{b.source}: {b.label} · {dollars(b.value * 100)} · {b.observedAt} <a href={externalUrl(b.sourceUrl)}>Source</a></p>) : null}</section>
      </details>
      <section className="housing-section">
        <h3>Payment review</h3>
        <p className="notice">Optional test payments only. Live charges are disabled.</p>
        <button className="btn" onClick={() => setPaymentOpen((v) => !v)}>{paymentOpen ? 'Hide payment review' : 'Review a test payment'}</button>
        {paymentOpen && <PaymentPanel roomId={room.id} />}
      </section>
    </>}
    {message && <p role="status">{message}</p>}{error && <p className="err" role="alert">{error}</p>}{busy && <p role="status">Working...</p>}
  </Modal>;
}
