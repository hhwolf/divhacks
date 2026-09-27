import { useEffect, useLayoutEffect, useRef, useState } from 'react';

/**
 * /device — testing aid: shows the Expo mobile app (its web build, `expo start --web`, default :8081) inside a phone
 * frame at the device's real CSS size, so layouts can be checked from a desktop browser. Presets, rotate, route
 * shortcuts and reload; the app URL can be changed (?app=…) and is remembered.
 */
// Safe-area insets (top,right,bottom,left in pt) per orientation, passed to the app as ?insets= (apps/mobile/src/webInsets.ts).
const DEVICES = [
  { id: 'iphone15pro', label: 'iPhone 15 Pro', w: 393, h: 852, r: 55, island: true, insets: '59,0,34,0', insetsLand: '0,59,21,59' },
  { id: 'iphonese', label: 'iPhone SE', w: 375, h: 667, r: 30, island: false, insets: '20,0,0,0', insetsLand: '0,0,0,0' },
  { id: 'pixel8', label: 'Pixel 8', w: 412, h: 915, r: 44, island: false, insets: '24,0,16,0', insetsLand: '0,24,16,0' },
] as const;
const ROUTES: [string, string][] = [['Welcome', '/welcome'], ['Home', '/'], ['Scan', '/scan'], ['Settings', '/settings']];
const BEZEL = 12;
const ls = (k: string, d: string) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
const lsSet = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } };

export function DevicePreview() {
  const params = new URLSearchParams(location.search);
  const [base, setBase] = useState(params.get('app') ?? ls('arp.device.app', `${location.protocol}//${location.hostname}:8081`));
  const [draft, setDraft] = useState(base);
  const [deviceId, setDeviceId] = useState(ls('arp.device.model', 'iphone15pro'));
  const [landscape, setLandscape] = useState(params.get('landscape') === '1');
  const [route, setRoute] = useState(params.get('route') ?? '/');
  const [nonce, setNonce] = useState(0);
  const [scale, setScale] = useState(1);
  const stage = useRef<HTMLDivElement>(null);
  const d = DEVICES.find((x) => x.id === deviceId) ?? DEVICES[0];
  const w = landscape ? d.h : d.w, h = landscape ? d.w : d.h;

  useLayoutEffect(() => {
    const fit = () => { const el = stage.current; if (!el) return; setScale(Math.min(1, (el.clientHeight - 40) / (h + 2 * BEZEL), (el.clientWidth - 40) / (w + 2 * BEZEL))); };
    fit(); window.addEventListener('resize', fit); return () => window.removeEventListener('resize', fit);
  }, [w, h]);
  useEffect(() => { lsSet('arp.device.model', deviceId); }, [deviceId]);

  const src = `${base.replace(/\/+$/, '')}${route}${route.includes('?') ? '&' : '?'}insets=${landscape ? d.insetsLand : d.insets}`;
  const open = (r: string) => { setRoute(r); setNonce((n) => n + 1); };
  const applyBase = () => { const v = draft.trim().replace(/\/+$/, ''); if (!v) return; setBase(v); lsSet('arp.device.app', v); setNonce((n) => n + 1); };

  return (
    <div className="device-page">
      <header className="device-bar">
        <div className="device-brand"><b>Mobile preview</b><span>{d.label} · {w}×{h}{landscape ? ' · landscape' : ''} · {Math.round(scale * 100)}%</span></div>
        <div className="device-controls">
          <div className="seg">{DEVICES.map((x) => <button key={x.id} className={x.id === d.id ? 'on' : ''} onClick={() => setDeviceId(x.id)}>{x.label}</button>)}</div>
          <button className="btn small" onClick={() => setLandscape((v) => !v)} title="Rotate">⟳ Rotate</button>
          <button className="btn small" onClick={() => setNonce((n) => n + 1)} title="Reload">↻ Reload</button>
          <a className="btn small" href={src} target="_blank" rel="noreferrer">Open ↗</a>
        </div>
        <div className="device-controls">
          <div className="seg">{ROUTES.map(([label, r]) => <button key={r} className={route === r ? 'on' : ''} onClick={() => open(r)}>{label}</button>)}</div>
          <form onSubmit={(e) => { e.preventDefault(); applyBase(); }} className="device-url">
            <input value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Mobile app URL" spellCheck={false} />
            <button className="btn small" type="submit">Load</button>
          </form>
        </div>
      </header>
      <div className="device-stage" ref={stage}>
        <div className="device-frame" style={{ width: w + 2 * BEZEL, height: h + 2 * BEZEL, borderRadius: d.r + BEZEL, transform: `scale(${scale})` }}>
          <div className="device-screen" style={{ width: w, height: h, borderRadius: d.r }}>
            <iframe key={`${nonce}-${src}`} src={src} title="Mobile app" width={w} height={h} />
            {d.island && <span className={`device-island ${landscape ? 'side' : ''}`} />}
            {!landscape && (
              <div className={`device-status ${d.island ? 'island' : ''}`} aria-hidden>
                <span>9:41</span>
                <span className="device-status-icons"><i className="sig" /><i className="wifi" /><i className="batt" /></span>
              </div>
            )}
            {d.id !== 'iphonese' && <span className={`device-home ${landscape ? 'land' : ''}`} aria-hidden />}
          </div>
        </div>
        <p className="device-hint">Needs the Expo web server: <code>cd apps/mobile &amp;&amp; npx expo start --web</code> (plus <code>make api</code> / <code>make web</code>). Native-only features (RoomPlan, landscape lock) are stubbed on web.</p>
      </div>
    </div>
  );
}
