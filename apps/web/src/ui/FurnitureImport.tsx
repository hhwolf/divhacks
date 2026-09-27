import { useState } from 'react';
import type { FurnitureCategory, FurnitureItem } from '@arp/contracts';
import { api, unwrapItem } from '../lib/api';
import { externalUrl } from '../lib/auth';
import { useEditor } from '../store';
import { Modal } from './Modal';

export function FurnitureImport({ onClose, existing }: { onClose: () => void; existing?: FurnitureItem }) {
  const [item, setItem] = useState<FurnitureItem | null>(existing ?? null); const [url, setUrl] = useState(existing?.sourceUrl ?? ''); const [name, setName] = useState(existing?.name ?? 'My room divider'); const [category, setCategory] = useState<FurnitureCategory>(existing?.category ?? 'divider');
  const [dims, setDims] = useState(existing?.dims ?? { w: 1.5, d: 0.35, h: 1.8 }); const [price, setPrice] = useState(existing?.price?.toString() ?? ''); const [delivery, setDelivery] = useState(existing?.deliveryCost?.toString() ?? '0'); const [confirmed, setConfirmed] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(''); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const imported = (f: FurnitureItem) => { setItem(f); setName(f.name); setCategory(f.category); setDims(f.dims); setPrice(f.price?.toString() ?? ''); setConfirmed(false); };
  return <Modal title="Preview furniture" onClose={onClose}><p>Import a listing or furniture screenshot, or enter dimensions yourself. Confirm measurements before checking fit.</p>
    <label>Original listing URL<input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></label>
    <div className="housing-actions"><button className="btn" disabled={!externalUrl(url) || busy} onClick={() => void run(async () => imported(unwrapItem(await api.fromLink(url))))}>Import listing</button><label>Furniture screenshot (up to 5 MB)<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void run(async () => imported(unwrapItem(await api.fromPhoto(file)))); e.target.value = ''; }} /></label></div>
    <p>For Facebook Marketplace, use a screenshot or manual details and keep the listing URL. Furniture screenshots may use the existing AI import service; housing-condition photos never do.</p>
    <form onSubmit={(e) => { e.preventDefault(); void run(async () => { const body = { name, category, dims, price: price === '' ? null : Number(price), deliveryCost: Number(delivery), sourceUrl: url || null }; const f = item ? await api.confirmFurniture(item.id, { ...body, dimensionsConfirmed: true }) : await api.manualFurniture(body); useEditor.getState().addFurniture(f); useEditor.getState().startPlacing(f.id); onClose(); }); }}>
      <div className="housing-grid"><label>Name<input required value={name} maxLength={200} onChange={(e) => setName(e.target.value)} /></label><label>Category<select value={category} onChange={(e) => setCategory(e.target.value as FurnitureCategory)}>{['divider', 'decor', 'bed', 'desk', 'seating', 'storage', 'table', 'imported'].map((c) => <option key={c}>{c}</option>)}</select></label>
        {(['w', 'd', 'h'] as const).map((key) => <label key={key}>{({ w: 'Width', d: 'Depth', h: 'Height' })[key]} (meters)<input type="number" required step="0.01" min="0.01" max="20" value={dims[key]} onChange={(e) => { setDims({ ...dims, [key]: Number(e.target.value) }); setConfirmed(false); }} /></label>)}
        <label>Item price (USD; optional)<input type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} /></label><label>Delivery (USD)<input type="number" min="0" step="0.01" required value={delivery} onChange={(e) => setDelivery(e.target.value)} /></label>
      </div>
      <label className="check"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I confirmed these dimensions from the seller or measurements.</label>
      <button className="btn primary" disabled={busy || !confirmed}>Preview in room</button>
    </form>
    <p>Placement checks include collisions, door clearance and walking paths. A divider does not establish a legally compliant bedroom.</p>
    {externalUrl(url) && <a className="btn" href={externalUrl(url)} target="_blank" rel="noreferrer">Open original listing</a>}<p>Purchases happen on the seller’s site. This app does not process or protect that transaction.</p>
    {error && <p className="err" role="alert">{error}</p>}
  </Modal>;
}
