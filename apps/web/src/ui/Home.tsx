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
  const nav = useNavigate(); const [rooms, setRooms] = useState<Room[]>([]); const [health, setHealth] = useState<string>('...'); const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  const [dims, setDims] = useState({ l: '11', w: '10', h: '9' }); const [showDims, setShowDims] = useState(false);
  useEffect(() => { api.rooms().then(setRooms).catch(() => undefined); api.health().then((h) => setHealth(h.mode)).catch(() => setHealth('offline')); }, []);
  const create = async (body: unknown) => {
    setBusy(true); setErr(null);
    try { const r = await api.createRoom(body); const cur = r.currentLayout ?? r.layouts.find((l) => l.isCurrent) ?? r.layouts[0]; nav(`/layout/${cur.id}`); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const ft = (v: string) => (parseFloat(v) || 0) * 0.3048;
  return (
    <div className={`home theme-${theme}`}>
      <Backdrop />
      <header><h1>Adaptive Room Planner</h1><p>Scan a room, save the Current Room, and test layout ideas as separate variants. <span className={`chip ${health}`}>API: {health}</span></p></header>
      <Account />
      <div className="cards">
        <button className="card" onClick={() => alert('Scanning needs the iPhone app with LiDAR. Use a sample room here or open the mobile preview.')}><span className="card-icon"><I.camera /></span><b>Scan room</b><small>RoomPlan on iPhone Pro</small></button>
        <button className="card" disabled={busy} onClick={() => create({ sample: 'nyc-bedroom' })}><span className="card-icon"><I.bed /></span><b>Load sample room</b><small>3.4 x 3.0 m NYC bedroom</small></button>
        <button className="card" disabled={busy} onClick={() => setShowDims((v) => !v)}><span className="card-icon"><I.grid /></span><b>Enter dimensions</b><small>Length, width, height</small></button>
      </div>
      {showDims && (
        <form className="dims" onSubmit={(e) => { e.preventDefault(); void create({ name: 'My room', dimensions: { l: ft(dims.l), w: ft(dims.w), h: ft(dims.h) }, doors: [{ wall: 2, offset: 0.3, width: 0.9, swing: 'in', hinge: 'right' }], windows: [{ wall: 0, offset: 1.0, width: 1.2, sillHeight: 0.9, height: 1.3 }] }); }}>
          <label>Length (ft)<input value={dims.l} onChange={(e) => setDims({ ...dims, l: e.target.value })} /></label>
          <label>Width (ft)<input value={dims.w} onChange={(e) => setDims({ ...dims, w: e.target.value })} /></label>
          <label>Height (ft)<input value={dims.h} onChange={(e) => setDims({ ...dims, h: e.target.value })} /></label>
          <button className="btn" disabled={busy}>Create room</button>
        </form>
      )}
      <div className="home-links">
        <button className="link" disabled={busy} onClick={() => create({ sample: 'studio' })}>Load the studio sample</button>
        <a className="link" href="/device">Preview the mobile app in a phone frame -&gt;</a>
      </div>
      {err && <p className="err">{err}</p>}
      {rooms.length > 0 && (
        <section className="recent"><h2>Recent rooms</h2>
          {rooms.slice().reverse().slice(0, 6).map((r) => <button key={r.id} className="recent-row" onClick={async () => { const rr = await api.room(r.id); const cur = rr.layouts.find((l) => l.isCurrent) ?? rr.layouts[0]; if (cur) nav(`/layout/${cur.id}`); }}><b>{r.name}</b><span>{r.skeleton.dimensions.l.toFixed(1)} x {r.skeleton.dimensions.w.toFixed(1)} m</span></button>)}
        </section>
      )}
    </div>
  );
}
