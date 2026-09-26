"""C5 evidence: frames per second while dragging in the editor, measured with requestAnimationFrame in a *headed* Chromium
(real GPU) at the iPhone Pro landscape viewport. Writes .data/fps.json. Usage: .venv/bin/python scripts/measure_fps.py
"""
from __future__ import annotations
import json, pathlib, sys, time, urllib.request
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]

def api(base, method, path, body=None):
    req = urllib.request.Request(f"{base}{path}", method=method, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read())

def main() -> int:
    web, base = "http://localhost:5173", "http://localhost:8000"
    r = api(base, "POST", "/rooms", {"sample": "nyc-bedroom"}); cur = r.get("currentLayout") or next(l for l in r["layouts"] if l["isCurrent"])
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False, args=["--window-size=1300,650"])
        pg = b.new_page(viewport={"width": 1278, "height": 590}, device_scale_factor=2)
        pg.goto(f"{web}/layout/{cur['id']}?embedded=1", wait_until="networkidle"); pg.wait_for_function("() => window.__arpStore && window.__arpStore.getState().items.length > 0", timeout=60000); time.sleep(2)
        res = pg.evaluate("""async () => {
          const s = window.__arpStore.getState(); const d = s.items.find(i => i.furnitureId === 'dresser'); s.select(d.id); s.setDragging(d.id);
          let frames = 0; const t0 = performance.now(); let k = 0;
          await new Promise(res => { const tick = () => { frames++; k++; const t = (k % 120) / 120; s.moveItem(d.id, 3.15 - 1.4 * Math.abs(Math.sin(t * Math.PI)), 1.3 + 0.9 * Math.abs(Math.sin(t * Math.PI)), { free: true }); if (performance.now() - t0 < 4000) requestAnimationFrame(tick); else res(); }; requestAnimationFrame(tick); });
          s.setDragging(null); s.moveItem(d.id, 3.15, 1.3, { commit: true });
          return { fps: Math.round(frames / ((performance.now() - t0) / 1000)), frames };
        }""")
        b.close()
    out = {"viewport": "1278x590@2x (iPhone Pro landscape CSS px)", "browser": "Chromium headed (Mac GPU)", **res, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (ROOT / ".data/fps.json").write_text(json.dumps(out, indent=1)); print(out); return 0

if __name__ == "__main__": sys.exit(main())
