import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { FurnitureItem, Layout, Room } from '@arp/contracts';
import { formatArea, formatLength } from '@arp/geometry';
import { api, type CompareResponse } from '../lib/api';
import { useEditor } from '../store';
import { RoomScene } from '../scene/Scene';
import { Backdrop } from './Backdrop';

/** Two rooms side by side + metric deltas + what moved. Each side is its own store snapshot rendered read-only. */
export function ComparePage() {
  const { a, b } = useParams(); const [data, setData] = useState<CompareResponse | null>(null); const [room, setRoom] = useState<Room | null>(null); const [fur, setFur] = useState<Record<string, FurnitureItem>>({}); const [err, setErr] = useState<string | null>(null);
  const units = useEditor((s) => s.units); const theme = useEditor((s) => s.theme);
  useEffect(() => {
    if (!a || !b) return;
    Promise.all([api.compare(a, b), api.layout(a), api.layout(b)]).then(([c, la, lb]) => { setData(c); setFur({ ...(la.furniture ?? {}), ...(lb.furniture ?? {}) }); return api.room(la.layout.roomId); }).then((r) => setRoom(r.room)).catch((e) => setErr((e as Error).message));
  }, [a, b]);
  if (err) return <div className="compare theme-peach"><Backdrop /><p className="err">{err}</p></div>;
  if (!data || !room) return <div className="compare theme-peach"><Backdrop /><div className="loading"><div className="spinner" />Comparing…</div></div>;
  const d = data.deltas; const sign = (v: number, suffix = '') => `${v > 0 ? '+' : ''}${Math.round(v * 10) / 10}${suffix}`;
  return (
    <div className={`compare theme-${theme}`}>
      <Backdrop />
      <header className="compare-head"><Link to={`/layout/${a}`} className="btn dark">‹ Back to editor</Link><h1>{data.a.name} <span>vs</span> {data.b.name}</h1></header>
      <div className="compare-grid">
        <Side layout={data.a} room={room} fur={fur} /><Side layout={data.b} room={room} fur={fur} />
      </div>
      <div className="compare-metrics">
        <Metric label="Open floor" a={`${data.a.metrics?.openFloor ?? 0}%`} b={`${data.b.metrics?.openFloor ?? 0}%`} delta={sign(d.openFloor, ' pts')} good={d.openFloor >= 0} />
        <Metric label="Conflicts" a={`${data.a.metrics?.conflicts ?? 0}`} b={`${data.b.metrics?.conflicts ?? 0}`} delta={sign(d.conflicts)} good={d.conflicts <= 0} />
        <Metric label="Walkability" a={data.a.metrics?.walkability ?? '–'} b={data.b.metrics?.walkability ?? '–'} delta="" good />
        <Metric label="Reachable storage" a={`${data.a.metrics?.reachableStorage ?? 0}%`} b={`${data.b.metrics?.reachableStorage ?? 0}%`} delta={sign(d.reachableStorage, ' pts')} good={d.reachableStorage >= 0} />
        <Metric label="Largest free area" a={formatArea(data.a.metrics?.largestFreeRect?.areaM2 ?? 0, units)} b={formatArea(data.b.metrics?.largestFreeRect?.areaM2 ?? 0, units)} delta={sign(d.largestFreeRectArea * (units === 'metric' ? 1 : 10.7639), units === 'metric' ? ' m²' : ' sq ft')} good={d.largestFreeRectArea >= 0} />
      </div>
      <div className="compare-moved">
        <h2>What changed</h2>
        {data.moved.length + data.added.length + data.removed.length === 0 && <p>Nothing moved.</p>}
        <ul>
          {data.added.map((x) => <li key={`a${x.id}`}><b>Added</b> {x.name}</li>)}
          {data.removed.map((x) => <li key={`r${x.id}`}><b>Removed</b> {x.name}</li>)}
          {data.moved.map((m) => <li key={m.id}><b>Moved</b> {m.name}: {formatLength(Math.hypot(m.to.x - m.from.x, m.to.z - m.from.z), units)}{m.to.rotation !== m.from.rotation ? `, rotated ${((m.to.rotation - m.from.rotation + 360) % 360)}°` : ''}</li>)}
        </ul>
      </div>
    </div>
  );
}
function Metric({ label, a, b, delta, good }: { label: string; a: string; b: string; delta: string; good: boolean }) {
  return <div className="metric"><span className="metric-label">{label}</span><span className="metric-vals">{a} <i>→</i> {b}</span>{delta && <span className={`delta ${good ? 'good' : 'bad'}`}>{delta}</span>}</div>;
}
/** Read-only scene: shares the room + furniture from the store, renders this layout's items via itemsOverride. */
function Side({ layout, room, fur }: { layout: Layout; room: Room; fur: Record<string, FurnitureItem> }) {
  const [ready, setReady] = useState(false);
  useEffect(() => { useEditor.setState({ room, furniture: { ...useEditor.getState().furniture, ...fur }, items: [], zones: [], selectedId: null }); setReady(true); }, [room, fur]);
  if (!ready) return null;
  return <div className="side"><div className="side-title">{layout.name}{layout.isCurrent ? ' 🔒' : ''}</div><RoomScene interactive={false} className="canvas side-canvas" itemsOverride={layout.items} hideOverlays /></div>;
}
