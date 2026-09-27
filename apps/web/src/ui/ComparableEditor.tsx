import { useState } from 'react';
import type { HousingProfile, RentalComparable } from '@arp/contracts';
import { api } from '../lib/api';
import { nycDate } from '../lib/dates';
import { externalUrl, randomId } from '../lib/auth';

const blank = (p: HousingProfile): RentalComparable => ({ id: randomId(), unitKey: '', sourceUrl: '', observedAt: nycDate(), occupancyType: p.occupancyType, rentCents: 0, areaSqFt: p.confirmedAreaSqFt ?? 0, areaConfirmed: false, latitude: 0, longitude: 0, bedrooms: p.bedrooms ?? null, bathrooms: p.bathrooms ?? null, leaseMonths: p.leaseMonths, furnished: p.furnished, utilitiesIncluded: p.utilitiesIncluded, sharedAmenities: '', conditionsDocumented: false, conditions: [], provenance: 'user' });

export function ComparableEditor({ profile, onChange }: { profile: HousingProfile; onChange: (values: RentalComparable[]) => void }) {
  const [entry, setEntry] = useState(() => blank(profile)); const [editing, setEditing] = useState(false); const [candidates, setCandidates] = useState<RentalComparable[]>([]);
  const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false); const [sameConditions, setSameConditions] = useState(false);
  const [locationConfirmed, setLocationConfirmed] = useState(false);
  const patch = (p: Partial<RentalComparable>) => setEntry((c) => ({ ...c, ...p }));
  const search = async () => { setBusy(true); try { const r = await api.searchComparables(profile); setCandidates(r.comparables); setMessage(`${r.source.status}: ${r.source.note}`); } catch (e) { setMessage((e as Error).message); } finally { setBusy(false); } };
  return <section className="housing-section"><h3>Comparable listings</h3><p>Use separate units with matching occupancy and rental terms. Confirm each listing’s details; missing terms are not assumed.</p>
    <div className="housing-actions"><button className="btn" onClick={() => { setEntry(blank(profile)); setLocationConfirmed(false); setSameConditions(false); setEditing(true); }}>Add a comparable</button><button className="btn" disabled={busy} onClick={() => void search()}>Find listing candidates</button></div>
    {message && <p role="status">{message}</p>}
    {candidates.length > 0 && <details><summary>{candidates.length} candidates to review</summary>{candidates.map((c) => <div className="housing-record" key={c.id}><span>{c.unitKey} · ${c.rentCents / 100} · {c.areaSqFt} sq ft</span><button className="btn" onClick={() => { setEntry(c); setLocationConfirmed(false); setSameConditions(false); setEditing(true); }}>Review this listing</button></div>)}</details>}
    {editing && <form onSubmit={(e) => {
      e.preventDefault();
      if (!locationConfirmed || !entry.areaConfirmed || !externalUrl(entry.sourceUrl)) { setMessage('Confirm the area and listing coordinates, and provide a public source URL.'); return; }
      const record = { ...entry, conditionsDocumented: entry.conditionsDocumented && sameConditions, conditions: sameConditions ? profile.conditions.filter((c) => c.scope === 'unit' && c.status === 'ongoing').map((c) => ({ ...c, source: 'user' as const, photoIds: [], observedAt: entry.observedAt })) : [] };
      onChange([...profile.comparables.filter((c) => c.id !== record.id), record]); setEditing(false);
    }}><fieldset><legend>Confirm listing details</legend><div className="housing-grid">
      <label>Unit address / distinct room identifier<input required value={entry.unitKey} onChange={(e) => patch({ unitKey: e.target.value })} /></label>
      <label>Source listing URL<input required type="url" value={entry.sourceUrl} onChange={(e) => patch({ sourceUrl: e.target.value })} /></label>
      <label>Monthly asking rent (USD)<input required type="number" min="1" step="0.01" value={entry.rentCents / 100 || ''} onChange={(e) => patch({ rentCents: Math.round(Number(e.target.value) * 100) })} /></label>
      <label>Floor area (sq ft)<input required type="number" min="1" value={entry.areaSqFt || ''} onChange={(e) => patch({ areaSqFt: Number(e.target.value) })} /></label>
      <label>Observed date<input required type="date" max={nycDate()} value={entry.observedAt} onChange={(e) => patch({ observedAt: e.target.value })} /></label>
      <label>Occupancy<select value={entry.occupancyType} onChange={(e) => patch({ occupancyType: e.target.value as RentalComparable['occupancyType'] })}><option value="private_room">Private room</option><option value="shared_room">Shared room</option><option value="studio">Studio</option><option value="whole_apartment">Whole apartment</option></select></label>
      <label>Latitude<input required type="number" min="-90" max="90" step="any" value={entry.latitude} onChange={(e) => patch({ latitude: Number(e.target.value) })} /></label>
      <label>Longitude<input required type="number" min="-180" max="180" step="any" value={entry.longitude} onChange={(e) => patch({ longitude: Number(e.target.value) })} /></label>
      <label>Lease (months)<input required type="number" min="1" value={entry.leaseMonths ?? ''} onChange={(e) => patch({ leaseMonths: Number(e.target.value) })} /></label>
      <label>Bedrooms<input type="number" min="0" value={entry.bedrooms ?? ''} onChange={(e) => patch({ bedrooms: e.target.value === '' ? null : Number(e.target.value) })} /></label>
      <label>Bathrooms<input type="number" min="0" step="0.5" value={entry.bathrooms ?? ''} onChange={(e) => patch({ bathrooms: e.target.value === '' ? null : Number(e.target.value) })} /></label>
      <label>Furnished<select required value={entry.furnished == null ? '' : String(entry.furnished)} onChange={(e) => patch({ furnished: e.target.value === '' ? null : e.target.value === 'true' })}><option value="">Unknown</option><option value="true">Yes</option><option value="false">No</option></select></label>
      <label>Utilities included<select required value={entry.utilitiesIncluded == null ? '' : String(entry.utilitiesIncluded)} onChange={(e) => patch({ utilitiesIncluded: e.target.value === '' ? null : e.target.value === 'true' })}><option value="">Unknown</option><option value="true">Yes</option><option value="false">No</option></select></label>
    </div><label>Shared amenities<input value={entry.sharedAmenities} onChange={(e) => patch({ sharedAmenities: e.target.value })} placeholder="Shared kitchen, bathroom, laundry…" /></label>
    <label className="check"><input type="checkbox" checked={locationConfirmed} onChange={(e) => setLocationConfirmed(e.target.checked)} />I confirmed these coordinates identify the listing’s location.</label>
    <label className="check"><input type="checkbox" checked={entry.areaConfirmed} onChange={(e) => patch({ areaConfirmed: e.target.checked })} />I confirmed this listing’s floor area.</label>
    <label className="check"><input type="checkbox" checked={entry.conditionsDocumented} onChange={(e) => { patch({ conditionsDocumented: e.target.checked }); if (!e.target.checked) setSameConditions(false); }} />I have documentation of this listing’s housing problems.</label>
    {entry.conditionsDocumented && <label className="check"><input type="checkbox" checked={sameConditions} onChange={(e) => setSameConditions(e.target.checked)} />Its documentation reports the same ongoing unit-level problems and severity as my room.</label>}
    <button className="btn primary">Save comparable</button> <button type="button" className="btn" onClick={() => setEditing(false)}>Cancel</button>
    </fieldset></form>}
    {profile.comparables.map((c) => <div className="housing-record" key={c.id}><a href={externalUrl(c.sourceUrl)} target="_blank" rel="noreferrer">{c.unitKey} · ${c.rentCents / 100}/month</a><span>{c.provenance === 'fixture' ? 'Demo data' : 'User-confirmed details'} · {c.observedAt}</span><button className="btn" onClick={() => onChange(profile.comparables.filter((x) => x.id !== c.id))}>Remove</button></div>)}
  </section>;
}
