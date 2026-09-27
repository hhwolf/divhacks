import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Room } from '@arp/contracts';
import { api } from '../lib/api';
import { Account } from './Account';
import { Backdrop } from './Backdrop';
import { I } from './icons';
import { useEditor } from '../store';

export function Home() {
  const theme = useEditor((s) => s.theme);
  const nav = useNavigate(); const [rooms, setRooms] = useState<Room[]>([]); const [health, setHealth] = useState<string>('checking'); const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  const [dims, setDims] = useState({ l: '11', w: '10', h: '9' }); const [showDims, setShowDims] = useState(false);
  useEffect(() => { api.rooms().then(setRooms).catch(() => undefined); api.health().then(() => setHealth('on')).catch(() => setHealth('offline')); }, []);
  const create = async (body: unknown) => {
    setBusy(true); setErr(null);
    try { const r = await api.createRoom(body); const cur = r.currentLayout ?? r.layouts.find((l) => l.isCurrent) ?? r.layouts[0]; nav(`/layout/${cur.id}`); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const ft = (v: string) => (parseFloat(v) || 0) * 0.3048;
  return (
    <div className={`home landing theme-${theme}`}>
      <Backdrop />
      <main className="landing-shell">
        <section className="landing-hero">
          <div className="landing-copy">
            <div className="landing-brand"><span className="landing-mark"><I.plant /></span><b>FitCheck</b><span className={`chip ${health === 'on' ? 'live' : health}`}>API: {health}</span></div>
            <h1>Small NYC room? Check what fits before you buy.</h1>
            <p>FitCheck maps your space, tests furniture against real dimensions, and shows layout options before a desk, divider, or bed eats the room.</p>
            <div className="landing-actions" aria-label="Start options">
              <button className="landing-action primary" onClick={() => alert('Scanning needs the iPhone app with LiDAR. Use a sample room here or open the mobile preview.')}><span><I.camera /></span><b>Scan room</b><small>Capture tight corners with LiDAR</small><I.chevR /></button>
              <button className="landing-action" disabled={busy} onClick={() => create({ sample: 'nyc-bedroom' })}><span><I.bed /></span><b>Load sample room</b><small>See a compact NYC bedroom</small><I.chevR /></button>
              <button className="landing-action" disabled={busy} onClick={() => setShowDims((v) => !v)}><span><I.grid /></span><b>Enter dimensions</b><small>Check fit without scanning</small><I.chevR /></button>
            </div>
            <div className="landing-links">
              <button className="link" disabled={busy} onClick={() => create({ sample: 'studio' })}>Try a studio layout</button>
              <a className="link" href="/device">Preview the mobile app in a phone frame -&gt;</a>
            </div>
          </div>
          <LandingPreview />
        </section>
        <Account />
        {showDims && (
          <form className="dims landing-dims" onSubmit={(e) => { e.preventDefault(); void create({ name: 'My room', dimensions: { l: ft(dims.l), w: ft(dims.w), h: ft(dims.h) }, doors: [{ wall: 2, offset: 0.3, width: 0.9, swing: 'in', hinge: 'right' }], windows: [{ wall: 0, offset: 1.0, width: 1.2, sillHeight: 0.9, height: 1.3 }] }); }}>
            <label>Length (ft)<input value={dims.l} onChange={(e) => setDims({ ...dims, l: e.target.value })} /></label>
            <label>Width (ft)<input value={dims.w} onChange={(e) => setDims({ ...dims, w: e.target.value })} /></label>
            <label>Height (ft)<input value={dims.h} onChange={(e) => setDims({ ...dims, h: e.target.value })} /></label>
            <button className="btn" disabled={busy}>Create room</button>
          </form>
        )}
        {err && <p className="err">{err}</p>}
        {rooms.length > 0 && (
          <section className="recent"><h2>Recent rooms</h2>
            {rooms.slice().reverse().slice(0, 6).map((r) => <button key={r.id} className="recent-row" onClick={async () => { const rr = await api.room(r.id); const cur = rr.layouts.find((l) => l.isCurrent) ?? rr.layouts[0]; if (cur) nav(`/layout/${cur.id}`); }}><b>{r.name}</b><span>{r.skeleton.dimensions.l.toFixed(1)} x {r.skeleton.dimensions.w.toFixed(1)} m</span></button>)}
          </section>
        )}
      </main>
    </div>
  );
}

function LandingPreview() {
  return (
    <div className="landing-preview" aria-hidden>
      <div className="preview-card preview-scan">
        <PreviewHead icon={<I.camera />} title="Measure the room" sub="Walls, doors, windows" />
        <PreviewRow icon={<I.grid />} label="Walls" tag="4" on />
        <PreviewRow icon={<I.chevR />} label="Door" tag="1" on />
        <PreviewRow icon={<I.eye />} label="Window" tag="1" on />
        <div className="preview-progress"><span /></div>
      </div>
      <div className="preview-card preview-room">
        <PreviewHead icon={<I.lock />} title="Protect what stays" sub="Do not move the bed" />
        <PreviewRow icon={<I.bed />} label="Double bed" tag="Locked" on />
        <PreviewRow icon={<I.desk />} label="Oak desk" tag="Placed" />
        <PreviewRow icon={<I.storage />} label="Dresser" tag="Placed" />
      </div>
      <div className="preview-card preview-ask">
        <PreviewHead icon={<I.chat />} title="Ask before buying" sub="New variant - 2 in to spare" />
        <div className="preview-bubble">Will this desk fit without blocking the closet?</div>
        <div className="preview-chips"><span>Current room</span><b>Desk fits</b></div>
      </div>
    </div>
  );
}

function PreviewHead({ icon, title, sub }: { icon: ReactNode; title: string; sub: string }) {
  return <div className="preview-head"><span>{icon}</span><div><b>{title}</b><small>{sub}</small></div></div>;
}

function PreviewRow({ icon, label, tag, on }: { icon: ReactNode; label: string; tag: string; on?: boolean }) {
  return <div className="preview-row"><span>{icon}</span><b>{label}</b><em className={on ? 'on' : ''}>{tag}</em></div>;
}
