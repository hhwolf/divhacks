"""Record the demo script as a video at the iPhone Pro landscape viewport (2556×1179 CSS px scaled 0.5 for size) with
Playwright's recorder, then convert to docs/demo/run.mp4 with ffmpeg. This is a browser recording of the web editor at
phone proportions — the on-device recording is a separate deliverable.
"""
from __future__ import annotations
import argparse, json, pathlib, shutil, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

def api(base, method, path, body=None):
    req = urllib.request.Request(f"{base}{path}", method=method, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read())

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--web", default="http://localhost:5173"); ap.add_argument("--api", default="http://localhost:8000"); a = ap.parse_args()
    out = ROOT / "docs/demo"; out.mkdir(exist_ok=True); tmp = out / "_rec"; shutil.rmtree(tmp, ignore_errors=True)
    r = api(a.api, "POST", "/rooms", {"sample": "nyc-bedroom"}); cur = r.get("currentLayout") or next(l for l in r["layouts"] if l["isCurrent"])
    with sync_playwright() as p:
        b = p.chromium.launch(args=GL)
        ctx = b.new_context(viewport={"width": 1278, "height": 590}, record_video_dir=str(tmp), record_video_size={"width": 1278, "height": 590})
        pg = ctx.new_page()
        pg.goto(f"{a.web}/layout/{cur['id']}?embedded=1", wait_until="networkidle"); pg.wait_for_function("() => window.__arpStore && window.__arpStore.getState().items.length > 0", timeout=60000); time.sleep(2.5)
        S = "window.__arpStore.getState()"
        # 0:50 play: select + rotate the dresser, lock the bed
        pg.evaluate(f"() => {{ const s = {S}; const d = s.items.find(i => i.furnitureId==='dresser'); s.select(d.id); }}"); time.sleep(1.2)
        pg.evaluate(f"() => {{ const s = {S}; s.rotateItem(s.selectedId); }}"); time.sleep(1.0); pg.evaluate(f"() => {{ const s = {S}; s.rotateItem(s.selectedId); s.rotateItem(s.selectedId); s.rotateItem(s.selectedId); }}"); time.sleep(0.8)
        # 1:05 drag the dresser into the door swing → red → back
        pg.evaluate(f"() => {{ const s = {S}; const d = s.items.find(i => i.furnitureId==='dresser'); s.setDragging(d.id); }}")
        for k in range(1, 16): pg.evaluate(f"() => {{ const s = {S}; const d = s.items.find(i => i.furnitureId==='dresser'); s.moveItem(d.id, 3.15 + (2.7-3.15)*{k}/15, 1.3 + (2.4-1.3)*{k}/15, {{free:true}}); }}"); time.sleep(0.06)
        pg.evaluate(f"() => {{ const s = {S}; const d = s.items.find(i => i.furnitureId==='dresser'); s.setDragging(null); s.moveItem(d.id, 2.7, 2.4, {{commit:true}}); s.setOverlaysOpen(true); s.toggleOverlay('keepClear'); }}"); time.sleep(2.0)
        pg.evaluate(f"() => {{ const s = {S}; const d = s.items.find(i => i.furnitureId==='dresser'); s.setOverlaysOpen(false); s.toggleOverlay('keepClear'); s.moveItem(d.id, 3.15, 1.3, {{commit:true}}); s.select(null); }}"); time.sleep(1.2)
        # 1:20 ask the room with the Marketplace link
        pg.evaluate(f"() => {S}.setRequestOpen(true)"); time.sleep(0.6)
        desk = api(a.api, "POST", "/furniture/from-link", {"url": f"{a.api}/fixtures/listings/desk"}); desk_id = (desk.get("item") or desk)["id"]
        pg.evaluate(f"() => {{ const s = {S}; s.addFurniture({json.dumps(desk.get('item') or desk)}); }}")
        pg.fill("[data-testid=request-bar] textarea", "Will this fit beside my window without moving my bed?"); time.sleep(0.8)
        pg.evaluate(f"() => {S}.askAgent('Will this fit beside my window without moving my bed?', '{desk_id}')"); pg.wait_for_selector("[data-testid=agent-reply]", timeout=60000); time.sleep(3.5)
        # 2:05 yoga
        pg.evaluate(f"() => {S}.askAgent('make space for yoga, keep my dresser')"); pg.wait_for_function(f"() => {S}.layouts.length >= 3", timeout=60000); time.sleep(3.0)
        pg.evaluate(f"() => {S}.setRequestOpen(false)")
        # 2:25 ghost compare then compare view
        pg.evaluate(f"() => {{ const s = {S}; const cur = s.layouts.find(l => l.isCurrent); s.setGhost(cur.id); s.setGhostOpen(true); }}"); time.sleep(2.5)
        ids = pg.evaluate(f"() => {{ const s = {S}; return [s.layouts.find(l => l.isCurrent).id, s.layouts.find(l => l.name.startsWith('Marketplace')).id]; }}")
        pg.goto(f"{a.web}/compare/{ids[0]}/{ids[1]}", wait_until="networkidle"); pg.wait_for_selector(".compare-metrics", timeout=60000); time.sleep(4.0)
        ctx.close(); b.close()
    webm = next(tmp.glob("*.webm")); mp4 = out / "run.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-vf", "scale=1278:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
    shutil.rmtree(tmp); print("wrote", mp4, mp4.stat().st_size // 1024, "KB"); return 0

if __name__ == "__main__": sys.exit(main())
