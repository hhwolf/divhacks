"""Playwright screenshot discipline (EXECUTION_PROMPT §8).

Captures the editor states at 1920x1080 and 2556x1179 (iPhone Pro landscape) into docs/screenshots/iter-N/,
then builds side-by-side crops (reference | ours) for each §7 element.

Usage: .venv/bin/python scripts/screenshots.py --iter 2 [--web http://localhost:5173] [--api http://localhost:8000]
"""
from __future__ import annotations
import argparse, json, pathlib, sys, time, urllib.request
from PIL import Image
from playwright.sync_api import sync_playwright, Page

ROOT = pathlib.Path(__file__).resolve().parents[1]
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]

def api(base: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{base}{path}", method=method, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())

def setup_room(base: str) -> dict:
    """Fresh sample room with three variants: Current Room, Marketplace Desk (agent, mock), Yoga corner (agent, mock)."""
    r = api(base, "POST", "/rooms", {"sample": "nyc-bedroom"})
    cur = r.get("currentLayout") or next(l for l in r["layouts"] if l["isCurrent"])
    desk = api(base, "POST", "/furniture/from-link", {"url": f"{base}/fixtures/listings/desk"})
    desk_id = (desk.get("item") or desk)["id"]
    a1 = api(base, "POST", "/agent/request", {"text": "Will this fit beside my window without moving my bed?", "roomId": r["room"]["id"], "baseLayoutId": cur["id"], "furnitureId": desk_id, "channel": "app"})
    base_for_yoga = (a1.get("layout") or cur)["id"]
    a2 = api(base, "POST", "/agent/request", {"text": "make space for yoga, keep my dresser", "roomId": r["room"]["id"], "baseLayoutId": base_for_yoga, "channel": "app"})
    return {"room": r["room"], "current": cur, "desk": a1.get("layout"), "yoga": a2.get("layout"), "desk_furniture": desk_id}

def settle(pg: Page, ms: int = 1400) -> None:
    pg.wait_for_selector("canvas", timeout=30000); time.sleep(ms / 1000)

def shoot(pg: Page, out: pathlib.Path, name: str) -> None:
    pg.screenshot(path=str(out / f"{name}.png")); print("  shot", name)

def capture(web: str, ctx_size: tuple[int, int], tag: str, ids: dict, out: pathlib.Path, browser) -> None:
    pg = browser.new_page(viewport={"width": ctx_size[0], "height": ctx_size[1]}, device_scale_factor=1)
    pg.goto(f"{web}/layout/{ids['current']['id']}", wait_until="networkidle"); settle(pg)
    shoot(pg, out, f"{tag}-01-empty-room")
    pg.click("[data-testid=palette] .tile.tool"); settle(pg, 300); shoot(pg, out, f"{tag}-02-palette")
    # select the dresser: click its footprint via store (robust to projection) then screenshot side panel
    pg.evaluate("() => { const s = window.__arpStore.getState(); const it = s.items.find(i => i.furnitureId === 'dresser'); s.select(it.id); }"); settle(pg, 500)
    shoot(pg, out, f"{tag}-03-selected-side-panel")
    # collision state: move the dresser onto the bed
    pg.evaluate("() => { const s = window.__arpStore.getState(); const it = s.items.find(i => i.furnitureId === 'dresser'); s.moveItem(it.id, 1.2, 1.0, {commit: true}); }"); settle(pg, 600)
    shoot(pg, out, f"{tag}-04-collision")
    pg.evaluate("() => window.__arpStore.getState().undo()"); settle(pg, 300)
    # overlays on
    pg.evaluate("() => { const s = window.__arpStore.getState(); s.select(null); s.setOverlaysOpen(true); s.toggleOverlay('walkable'); s.toggleOverlay('keepClear'); s.toggleOverlay('lowClearance'); }"); settle(pg, 500)
    shoot(pg, out, f"{tag}-05-overlays")
    pg.evaluate("() => { const s = window.__arpStore.getState(); s.setOverlaysOpen(false); s.toggleOverlay('walkable'); s.toggleOverlay('keepClear'); s.toggleOverlay('lowClearance'); }")
    # variant tabs with 3 variants
    settle(pg, 300); shoot(pg, out, f"{tag}-06-variant-tabs")
    # ghost compare
    if ids.get("desk"):
        pg.evaluate(f"() => {{ const s = window.__arpStore.getState(); s.setGhost('{ids['desk']['id']}'); s.setGhostOpen(true); }}"); settle(pg, 600)
        shoot(pg, out, f"{tag}-07-ghost-compare")
        pg.evaluate("() => { const s = window.__arpStore.getState(); s.setGhost(null); s.setGhostOpen(false); }")
    # request bar with reply
    pg.evaluate("() => { const s = window.__arpStore.getState(); s.setRequestOpen(true); }"); settle(pg, 300)
    pg.fill("[data-testid=request-bar] textarea", "make space for yoga, keep my dresser")
    pg.click("[data-testid=request-bar] .btn.primary"); pg.wait_for_selector("[data-testid=agent-reply]", timeout=30000); settle(pg, 1500)
    shoot(pg, out, f"{tag}-08-request-reply")
    # night + teal theme
    pg.evaluate("() => { const s = window.__arpStore.getState(); s.setRequestOpen(false); s.toggleNight(); }"); settle(pg, 500); shoot(pg, out, f"{tag}-09-night")
    pg.evaluate("() => { const s = window.__arpStore.getState(); s.toggleNight(); s.setTheme('stone'); }"); settle(pg, 500); shoot(pg, out, f"{tag}-10-stone-theme")
    pg.evaluate("() => { const s = window.__arpStore.getState(); s.setTheme('forest'); s.cycleView(); }"); settle(pg, 500); shoot(pg, out, f"{tag}-11-half-walls")
    pg.evaluate("() => { const s = window.__arpStore.getState(); s.cycleView(); }"); settle(pg, 500); shoot(pg, out, f"{tag}-12-plan-view")
    pg.evaluate("() => { const s = window.__arpStore.getState(); s.cycleView(); }")
    if ids.get("desk"):
        pg.goto(f"{web}/compare/{ids['current']['id']}/{ids['desk']['id']}", wait_until="networkidle"); settle(pg, 2000); shoot(pg, out, f"{tag}-13-compare")
    pg.close()

# (element, reference file, reference crop box, our crop box at 1920x1080)
CROPS = [
    ("background-corner", "ref2", (0, 0, 480, 270), (0, 0, 480, 270)),
    ("room-island", "ref2", (300, 30, 1700, 1080), (300, 30, 1700, 1080)),
    ("floor", "ref2", (900, 800, 1400, 1080), (900, 800, 1400, 1080)),
    ("top-left-cluster", "ref2", (60, 60, 280, 140), (60, 60, 280, 140)),
    ("top-right-cluster", "ref2", (1630, 60, 1870, 140), (1630, 60, 1870, 140)),
    ("left-palette", "ref2", (60, 260, 280, 820), (60, 260, 280, 820)),
    ("bottom-center", "ref2", (830, 940, 1090, 1020), (830, 940, 1090, 1020)),
]
CROPS3 = [
    ("right-swatch-panel", "ref3", (1030, 160, 1160, 520), (1640, 250, 1860, 900)),
    ("selection-diamond-pill", "ref3", (560, 430, 760, 510), (1000, 520, 1320, 800)),
    ("category-search", "ref3", (40, 180, 180, 500), (60, 160, 340, 340)),
]

def side_by_side(ref_path: pathlib.Path, ref_box, ours_path: pathlib.Path, ours_box, out_path: pathlib.Path) -> None:
    ref = Image.open(ref_path).convert("RGB").crop(ref_box); ours = Image.open(ours_path).convert("RGB").crop(ours_box)
    h = 360; ref = ref.resize((int(ref.width * h / ref.height), h)); ours = ours.resize((int(ours.width * h / ours.height), h))
    sheet = Image.new("RGB", (ref.width + ours.width + 30, h + 30), (30, 24, 20))
    sheet.paste(ref, (10, 20)); sheet.paste(ours, (ref.width + 20, 20)); sheet.save(out_path)

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--iter", type=int, required=True); ap.add_argument("--web", default="http://localhost:5173"); ap.add_argument("--api", default="http://localhost:8000"); ap.add_argument("--skip-mobile", action="store_true")
    a = ap.parse_args()
    out = ROOT / "docs/screenshots" / f"iter-{a.iter}"; out.mkdir(parents=True, exist_ok=True)
    ids = setup_room(a.api); print("room", ids["room"]["id"], "variants:", [x and x["name"] for x in (ids["current"], ids["desk"], ids["yoga"])])
    with sync_playwright() as p:
        b = p.chromium.launch(args=GL)
        capture(a.web, (1920, 1080), "web", ids, out, b)
        capture(a.web, (2556, 1179), "phone", ids, out, b)
        b.close()
    ref2 = ROOT / "docs/reference/ref2-game-ui-peach.png"; ref3 = ROOT / "docs/reference/ref3-game-ui-teal-swatches.png"
    for name, ref, rb, ob in CROPS:
        side_by_side(ref2, rb, out / "web-01-empty-room.png", ob, out / f"compare-{name}.png")
    for name, ref, rb, ob in CROPS3:
        src = out / ("web-03-selected-side-panel.png" if name != "category-search" else "web-02-palette.png")
        side_by_side(ref3, rb, src, ob, out / f"compare-{name}.png")
    (out / "ids.json").write_text(json.dumps(ids, indent=1))
    print("done →", out)
    return 0

if __name__ == "__main__": sys.exit(main())
