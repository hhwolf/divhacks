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
  return range ? <><strong className="range-value">{dollars(range.low * 100)}–{dollars(range.high * 100)}</strong><p>Median asking rent: <b>{dollars(range.mid * 100)}/month</b></p></> : <strong>Insufficient comparable data</strong>;
}

export function RentPanel({ onClose }: { onClose: () => void }) {
  const room = useEditor((s) => s.room)!; const activeId = useEditor((s) => s.activeId); const furniture = useEditor((s) => s.furniture); const items = useEditor((s) => s.items);
  const poly = room.skeleton.floorPolygon; const scanned = Math.round(Math.abs(poly.reduce((sum, [x, z], i) => sum + x * poly[(i + 1) % poly.length][1] - poly[(i + 1) % poly.length][0] * z, 0)) / 2 * 10.7639104167 * 10) / 10;
  const [profile, setProfile] = useState<HousingProfile>({ roomId: room.id, askingRent: 1600, occupancyType: 'private_room', scanCoverage: 'room', measurementConfirmed: false, confirmedAreaSqFt: scanned, leaseMonths: 12, utilitiesIncluded: false, furnished: false, conditions: [], comparables: [], dataMode: room.source === 'sample' ? 'demo' : 'real', zip: '10027' });
  const [assessment, setAssessment] = useState<RentAssessment | null>(null); const [dirty, setDirty] = useState(false); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const [candidates, setCandidates] = useState<AddressCandidate[]>([]); const [tab, setTab] = useState('space'); const [utilities, setUtilities] = useState('0'); const [deposit, setDeposit] = useState('1600'); const [moving, setMoving] = useState('0');
  const [benchmarks, setBenchmarks] = useState<{ source: string; value: number; label: string; observedAt: string; sourceUrl: string }[]>([]);
  useEffect(() => { let active = true; void Promise.all([api.housingProfile(room.id), api.latestAssessment(room.id).catch(() => null)]).then(([p, a]) => { if (active) { if (p.profile) setProfile(p.profile); if (a?.assessment) setAssessment(a.assessment); } }).catch((e: Error) => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [room.id]);
  useEffect(() => { document.querySelector('dialog')?.scrollTo({ top: 0 }); }, [tab]);
  const change = (patch: Partial<HousingProfile>) => { setProfile((p) => ({ ...p, ...patch })); setDirty(true); setMessage(''); };
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(''); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const furnishing = items.reduce((sum, i) => sum + (furniture[i.furnitureId]?.price ?? 0) + (furniture[i.furnitureId]?.deliveryCost ?? 0), 0);
  const unpriced = items.filter((i) => furniture[i.furnitureId]?.price == null).length;
  return <Modal title="Your space & rent" onClose={onClose}>
    <div className="housing-tabs" role="tablist" aria-label="Rent sections">{[['space', 'Space & conditions'], ['compare', 'Rent comparisons'], ['budget', 'Budget & payments']].map(([id, label]) => <button role="tab" aria-selected={tab === id} className={tab === id ? 'on' : ''} key={id} onClick={() => setTab(id)}>{label}</button>)}</div>
    <p className="notice">{profile.dataMode === 'demo' ? 'Demo data · synthetic listings and building records. Not evidence about any real address.' : 'Real data · unavailable sources stay unavailable. Your entries are labeled as user reported.'}</p>
    {profile.conditions.some((c) => c.status === 'ongoing') && <p className="notice">Reported housing problems still need attention, regardless of price. <a href="https://portal.311.nyc.gov/" target="_blank" rel="noreferrer">NYC 311 repair resources</a></p>}
    {loading ? <p>Loading rental details…</p> : <>
      {tab === 'space' && <>
        <section className="housing-section"><h3>Review measurements & rental details</h3><p>Physical floor area from this {room.source === 'scan' ? 'scan' : 'room polygon'}: <b>{scanned} sq ft</b>. Moving furniture changes free space, not your rent comparison. A replacement scan creates a separate room.</p>
          <div className="housing-grid">
            <label>Data source<select value={profile.dataMode} onChange={(e) => { change({ dataMode: e.target.value as HousingProfile['dataMode'], address: '', bbl: null, bin: null, latitude: null, longitude: null, comparables: [] }); setCandidates([]); }}><option value="demo">Demo data (synthetic)</option><option value="real">Real records / my listings</option></select></label>
            <label>What are you renting?<select value={profile.occupancyType} onChange={(e) => change({ occupancyType: e.target.value as HousingProfile['occupancyType'], measurementConfirmed: false })}><option value="private_room">Private room</option><option value="shared_room">Shared room</option><option value="studio">Studio apartment</option><option value="whole_apartment">Whole apartment</option></select></label>
            <label>Measurement covers<select value={profile.scanCoverage} onChange={(e) => change({ scanCoverage: e.target.value as HousingProfile['scanCoverage'], measurementConfirmed: false })}><option value="room">This room only</option><option value="whole_apartment">Entire apartment</option></select></label>
            <label>Confirmed physical area (sq ft)<input type="number" min="1" max="100000" step="0.1" value={profile.confirmedAreaSqFt ?? scanned} onChange={(e) => change({ confirmedAreaSqFt: Number(e.target.value), measurementConfirmed: false })} /></label>
            <label>Monthly asking rent (USD)<input type="number" min="1" value={profile.askingRent} onChange={(e) => change({ askingRent: Number(e.target.value) })} /></label>
            <label>Lease length (months)<input type="number" min="1" max="120" value={profile.leaseMonths} onChange={(e) => change({ leaseMonths: Number(e.target.value) })} /></label>
            {['studio', 'whole_apartment'].includes(profile.occupancyType) && <><label>Bedrooms<input type="number" min="0" value={profile.bedrooms ?? ''} onChange={(e) => change({ bedrooms: Number(e.target.value) })} /></label><label>Bathrooms<input type="number" min="0" step="0.5" value={profile.bathrooms ?? ''} onChange={(e) => change({ bathrooms: Number(e.target.value) })} /></label></>}
            <label>ZIP<input inputMode="numeric" maxLength={5} value={profile.zip ?? ''} onChange={(e) => change({ zip: e.target.value || null })} /></label><label>Apartment / unit (optional)<input value={profile.apartment ?? ''} onChange={(e) => change({ apartment: e.target.value })} /></label>
          </div>
          <div className="housing-actions"><label className="check"><input type="checkbox" checked={profile.utilitiesIncluded} onChange={(e) => change({ utilitiesIncluded: e.target.checked })} />Utilities included</label><label className="check"><input type="checkbox" checked={profile.furnished} onChange={(e) => change({ furnished: e.target.checked })} />Furnished</label></div>
          <label>Street address (required for property-specific real records)<input value={profile.address ?? ''} onChange={(e) => { change({ address: e.target.value, latitude: null, longitude: null, bbl: null, bin: null }); setCandidates([]); }} placeholder="Enter an NYC street address" /></label>
          <button className="btn" disabled={busy || (profile.address ?? '').length < 3} onClick={() => void run(async () => { const result = await api.addresses(profile.address!, profile.dataMode); setCandidates(result.candidates); setMessage(result.source.note); })}>Find address</button>
          {candidates.length > 0 && <fieldset><legend>Choose the matching property</legend>{candidates.map((c, i) => <button className="housing-record" key={i} onClick={() => { change({ address: c.label, bbl: c.bbl, bin: c.bin, latitude: c.latitude, longitude: c.longitude }); setCandidates([]); }}>{c.label}</button>)}</fieldset>}
          {profile.latitude != null && <p>Selected property: {profile.address || 'Synthetic demo location'}{profile.bbl ? ` · BBL ${profile.bbl}` : ' · no property identifier available'}</p>}
          <label className="check"><input type="checkbox" checked={profile.measurementConfirmed} onChange={(e) => change({ measurementConfirmed: e.target.checked })} />I reviewed the physical area and what the measurement covers.</label>
        </section>
        <ConditionsPanel roomId={room.id} value={profile.conditions} onChange={(conditions) => change({ conditions })} />
        <div className="housing-actions"><button className="btn" disabled={busy} onClick={() => void run(async () => { await api.saveHousingProfile(profile); setMessage('Rental details saved.'); })}>Save details</button><button className="btn primary" disabled={busy || !profile.measurementConfirmed} onClick={() => void run(async () => { await api.saveHousingProfile(profile); const r = await api.assessRent({ ...profile, layoutId: activeId }); setAssessment(r.assessment); setBenchmarks(r.benchmarks); setDirty(false); setTab('compare'); })}>Compare asking rents</button></div>
      </>}
      {tab === 'compare' && <>
        {dirty && <p className="notice">Details changed. Update the comparison to use your latest entries.</p>}
        <button className="btn" disabled={busy || !profile.measurementConfirmed} onClick={() => void run(async () => { await api.saveHousingProfile(profile); const r = await api.assessRent({ ...profile, layoutId: activeId }); setAssessment(r.assessment); setBenchmarks(r.benchmarks); setDirty(false); })}>Update comparison</button>
        {!profile.measurementConfirmed && <p>First confirm measurements in Space & conditions.</p>}
        {assessment && <section className="housing-section" aria-label="Rent results"><span className="eyebrow">{assessment.status === 'demo' ? 'Demo data' : 'Comparable asking rents'} · {new Date(assessment.createdAt).toLocaleDateString()}</span><h3>Comparable asking-rent range</h3><p>The middle half of qualifying listings; not a confidence interval or appraisal.</p>
          <div className="housing-grid"><article className="housing-result"><h4>Location-and-size comparison</h4><Range range={assessment.estimatedFairRange} /><p>{assessment.comparables.length} qualifying listings</p></article><article className="housing-result"><h4>Condition-matched comparison</h4><Range range={assessment.conditionMatchedRange} /><p>{assessment.conditionComparableIds.length} listings with similar documented problems</p></article></div>
          {assessment.conditionDifference != null && <p><b>Observed comparison difference: {dollars(assessment.conditionDifference * 100)}/month</b>. This does not establish a causal discount.</p>}
          {assessment.notices.map((n) => <p className="notice" key={n}>{n}</p>)}{assessment.explanation.map((n) => <p key={n}>{n}</p>)}
          <h3>Source listings</h3><div className="comparable-list">{assessment.comparables.map((c) => <article className="housing-record" key={c.id}><b>{dollars(c.rentCents)}/month · {c.areaSqFt} sq ft</b><span>{c.provenance === 'fixture' ? 'Demo data' : c.provenance === 'user' ? 'User reported' : 'RentCast; details reviewed by user'} · observed {c.observedAt}</span><span>{c.sharedAmenities}</span>{c.provenance !== 'fixture' && <a href={externalUrl(c.sourceUrl)} target="_blank" rel="noreferrer">Source listing</a>}</article>)}</div>
          <h3>Property records</h3><p>Building findings do not establish problems inside your unit. Complaints are reports; violations and inspections have separate statuses. Missing records do not prove a problem-free home.</p>
          {assessment.buildingRecords.length ? assessment.buildingRecords.map((r) => <article className="housing-record" key={r.id}><b>{r.demo ? 'Demo data' : 'Public record'} · {r.scope} · {r.kind}</b><span>{r.summary}</span><span>{r.observedAt} · {r.status}</span><a href={externalUrl(r.sourceUrl)} target="_blank" rel="noreferrer">Official source</a></article>) : <p>No property records returned; see source availability below.</p>}
          <p><a href="https://portal.311.nyc.gov/" target="_blank" rel="noreferrer">NYC 311 housing repair resources</a> · <a href="https://hcr.ny.gov/rent-increases-and-rent-overcharge" target="_blank" rel="noreferrer">HCR rent history and regulated rent guidance</a></p><p>Market comparisons do not determine legally regulated rent.</p>
          <details><summary>Method & source availability</summary><p>Calculation: {assessment.methodVersion}</p>{assessment.sources.map((s, i) => <article className="housing-record" key={i}><b>{s.source} · {s.status}</b><span>{s.note}</span><small>Retrieved {s.retrievedAt}{s.observedAt && ` · Observed ${s.observedAt}`} · {s.permittedUse}</small><a href={externalUrl(s.url)} target="_blank" rel="noreferrer">Source documentation</a></article>)}</details>
        </section>}
        <ComparableEditor profile={profile} onChange={(comparables) => change({ comparables })} />
        <section className="housing-section"><h3>Neighborhood & housing-program context</h3><p>StreetEasy neighborhood statistics and HUD Small Area Fair Market Rents are separate context. Neither values a private bedroom.</p>{benchmarks.length ? benchmarks.map((b, i) => <p key={i}>{b.source}: {b.label} · {dollars(b.value * 100)} · {b.observedAt} <a href={externalUrl(b.sourceUrl)}>Source</a></p>) : <p>No authorized benchmark data has been imported for this ZIP.</p>}</section>
      </>}
      {tab === 'budget' && <><section className="housing-section"><h3>Plan your costs</h3><p>Planning totals are not a lease quote or approval to collect a charge.</p><div className="housing-grid"><label>Monthly utilities outside rent (USD)<input type="number" min="0" value={utilities} onChange={(e) => setUtilities(e.target.value)} /></label><label>Planned deposit (USD)<input type="number" min="0" value={deposit} onChange={(e) => setDeposit(e.target.value)} /></label><label>Moving costs (USD)<input type="number" min="0" value={moving} onChange={(e) => setMoving(e.target.value)} /></label></div><p>Monthly: <b>{dollars((profile.askingRent + Number(utilities)) * 100)}</b> · Move-in including first rent, planned deposit, moving and priced furniture: <b>{dollars((profile.askingRent + Number(deposit) + Number(moving) + furnishing) * 100)}</b></p><p>Furniture in this variant: {dollars(furnishing * 100)} including entered delivery costs. {unpriced > 0 && `${unpriced} items have no price and are excluded.`} Use Import furniture to preview purchases.</p></section><PaymentPanel roomId={room.id} /></>}
    </>}
    {message && <p role="status">{message}</p>}{error && <p className="err" role="alert">{error}</p>}{busy && <p role="status">Working…</p>}
  </Modal>;
}
