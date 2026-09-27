import { useEffect, useState } from 'react';
import type { ConditionCategory, ConditionObservation, EvidencePhoto } from '@arp/contracts';
import { api } from '../lib/api';

export const conditionLabels: Record<ConditionCategory, string> = { insects: 'Bugs / insects', rodents: 'Rats / rodents', leaks: 'Leaks / water damage', plumbing: 'Plumbing', heat_hot_water: 'Heating / hot water', other: 'Other problem' };
export const newCondition = (category: ConditionCategory): ConditionObservation => ({ category, status: 'ongoing', severity: 'moderate', observedAt: new Date().toISOString().slice(0, 10), source: 'user', scope: 'unit', note: '', photoIds: [] });

function Photo({ photo, onDelete }: { photo: EvidencePhoto; onDelete: () => void }) {
  const [url, setUrl] = useState('');
  useEffect(() => { let active = true; let objectUrl = ''; void api.photoBlob(photo.id).then((blob) => { objectUrl = URL.createObjectURL(blob); if (active) setUrl(objectUrl); else URL.revokeObjectURL(objectUrl); }).catch(() => undefined); return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); }; }, [photo.id]);
  return <figure className="evidence-photo">{url ? <img src={url} alt="User-provided documentation of a housing condition" /> : <span>Photo unavailable</span>}<figcaption>User photo · {new Date(photo.createdAt).toLocaleDateString()}</figcaption><button className="btn" onClick={onDelete}>Delete photo</button></figure>;
}

export function ConditionsPanel({ roomId, value, onChange }: { roomId: string; value: ConditionObservation[]; onChange: (v: ConditionObservation[]) => void }) {
  const [category, setCategory] = useState<ConditionCategory>('rodents'); const [photos, setPhotos] = useState<EvidencePhoto[]>([]); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  useEffect(() => { void api.photos(roomId).then((r) => setPhotos(r.photos)).catch((e: Error) => setError(e.message)); }, [roomId]);
  const change = (i: number, patch: Partial<ConditionObservation>) => onChange(value.map((c, index) => index === i ? { ...c, ...patch } : c));
  const upload = async (i: number, file?: File) => {
    if (!file) return;
    setBusy(true); setError('');
    try { const r = await api.uploadEvidence(roomId, file); setPhotos((p) => [...p, r.photo]); change(i, { photoIds: [...value[i].photoIds, r.photo.id], source: 'photo' }); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <section className="housing-section"><h3>Housing conditions</h3><p>Report what you observed. Photos document your report and are not analyzed by AI. Building records are shown separately.</p>
    <div className="housing-actions"><label>Add a problem<select value={category} onChange={(e) => setCategory(e.target.value as ConditionCategory)}>{Object.entries(conditionLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><button className="btn" disabled={busy} onClick={() => onChange([...value, newCondition(category)])}>Add condition</button></div>
    {value.map((c, i) => <fieldset key={i} disabled={busy}><legend>{conditionLabels[c.category]} · User reported</legend><div className="housing-grid">
      <label>Status<select value={c.status} onChange={(e) => change(i, { status: e.target.value as ConditionObservation['status'] })}><option value="ongoing">Ongoing</option><option value="resolved">Resolved</option><option value="unknown">Unknown</option></select></label>
      <label>Severity<select value={c.severity} onChange={(e) => change(i, { severity: e.target.value as ConditionObservation['severity'] })}><option value="minor">Minor</option><option value="moderate">Moderate</option><option value="severe">Severe</option><option value="unknown">Unknown</option></select></label>
      <label>Observed on<input type="date" max={new Date().toISOString().slice(0, 10)} value={c.observedAt} onChange={(e) => change(i, { observedAt: e.target.value })} /></label>
      <label>Where observed<select value={c.scope} onChange={(e) => change(i, { scope: e.target.value as ConditionObservation['scope'] })}><option value="unit">Inside my unit / room</option><option value="building">Elsewhere in the building</option><option value="area">Surrounding area</option></select></label>
    </div><label>Notes<textarea maxLength={1000} value={c.note} onChange={(e) => change(i, { note: e.target.value })} placeholder="What happened, where, and whether repairs were attempted" /></label>
      <label>Optional photo (JPEG, PNG, WebP; up to 5 MB)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => { void upload(i, e.target.files?.[0]); e.target.value = ''; }} /></label>
      <button className="btn" onClick={() => onChange(value.filter((_, index) => index !== i))}>Remove condition</button>
    </fieldset>)}
    {!!value.length && <p className="notice">A lower rent does not fix a leak or infestation. <a href="https://portal.311.nyc.gov/" target="_blank" rel="noreferrer">NYC 311 repair and reporting resources</a></p>}
    <div className="evidence-photos">{photos.map((p) => <Photo key={p.id} photo={p} onDelete={() => { void api.deletePhoto(p.id).then(() => { setPhotos((all) => all.filter((x) => x.id !== p.id)); onChange(value.map((c) => ({ ...c, photoIds: c.photoIds.filter((id) => id !== p.id) }))); }).catch((e: Error) => setError(e.message)); }} />)}</div>
    {error && <p className="err" role="alert">{error}</p>}
  </section>;
}
