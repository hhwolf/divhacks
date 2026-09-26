"""Real-pointer end-to-end checks for the editor (A3/A7 evidence): tap a palette tile and drop it, mouse-drag an item on the
floor with 10 cm snap, R rotates, L locks, collision turns red and blocks save, Delete removes, ⌘Z undoes.

Usage: .venv/bin/python scripts/e2e_editor.py [--web http://localhost:5173] [--api http://localhost:8000]
"""
from __future__ import annotations
import argparse, json, sys, time, urllib.request
from playwright.sync_api import sync_playwright

GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

def api(base: str, method: str, path: str, body=None):
    req = urllib.request.Request(f"{base}{path}", method=method, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--web", default="http://localhost:5173"); ap.add_argument("--api", default="http://localhost:8000"); a = ap.parse_args()
    r = api(a.api, "POST", "/rooms", {"sample": "nyc-bedroom"}); cur = r.get("currentLayout") or next(l for l in r["layouts"] if l["isCurrent"])
    results: list[tuple[str, bool, str]] = []
    def check(name: str, ok: bool, info: str = "") -> None: results.append((name, ok, info)); print(("  ✓ " if ok else "  ✗ ") + name, info)
    with sync_playwright() as p:
        b = p.chromium.launch(args=GL); pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.goto(f"{a.web}/layout/{cur['id']}", wait_until="networkidle"); pg.wait_for_function("() => window.__arpStore && window.__arpStore.getState().items.length > 0 && window.__arpProject", timeout=30000); time.sleep(1.2)
        state = lambda: pg.evaluate("() => { const s = window.__arpStore.getState(); return { items: s.items, sel: s.selectedId, v: s.validation, save: s.saveState, placing: s.placing, hist: s.history.length }; }")
        proj = lambda x, z, y=0: pg.evaluate(f"() => window.__arpProject({x}, {z}, {y})")
        n0 = len(state()["items"])
        # 1. palette tap → placing → drop on the floor at (2.5, 0.35)
        pg.click("[data-testid=palette] .tile[aria-label='Desk']"); time.sleep(0.2)
        check("palette tap enters placing state", state()["placing"] is not None)
        pt = proj(1.2, 2.2); pg.mouse.move(pt["x"], pt["y"]); pg.mouse.down(); pg.mouse.up(); time.sleep(0.6)
        st = state(); desk = next((i for i in st["items"] if i["furnitureId"] == "desk"), None)
        check("tap on floor drops the desk", desk is not None and len(st["items"]) == n0 + 1, f"at {desk and (desk['x'], desk['z'])}")
        check("drop snaps to 10 cm grid", desk is not None and abs(desk["x"] * 10 - round(desk["x"] * 10)) < 1e-6 and abs(desk["z"] * 10 - round(desk["z"] * 10)) < 1e-6)
        check("dropped item is selected (side panel visible)", st["sel"] == desk["id"] and pg.is_visible("[data-testid=side-panel]"))
        # 2. mouse drag the desk along the floor toward the middle
        p0 = proj(desk["x"], desk["z"], 0.72); p1 = proj(1.6, 2.3, 0.72)
        pg.mouse.move(p0["x"], p0["y"]); pg.mouse.down(); 
        for k in range(1, 13): pg.mouse.move(p0["x"] + (p1["x"] - p0["x"]) * k / 12, p0["y"] + (p1["y"] - p0["y"]) * k / 12); time.sleep(0.03)
        pg.mouse.up(); time.sleep(0.6)
        d2 = next(i for i in state()["items"] if i["id"] == desk["id"])
        check("mouse drag moves the desk on the floor plane", abs(d2["x"] - 1.6) < 0.25 and abs(d2["z"] - 2.3) < 0.25, f"→ ({d2['x']}, {d2['z']})")
        # 3. R rotates, L locks / unlocks
        pg.keyboard.press("r"); time.sleep(0.2); check("R rotates 90°", next(i for i in state()["items"] if i["id"] == desk["id"])["rotation"] == 90)
        pg.keyboard.press("l"); time.sleep(0.2); check("L locks (badge)", next(i for i in state()["items"] if i["id"] == desk["id"])["locked"] is True and pg.locator(".lock-badge").count() >= 2)
        pg.keyboard.press("l"); time.sleep(0.2)
        # 4. drag onto the bookshelf / plant → red overlap → blocked save toast (re-read position: R may have wall-snapped it)
        d2 = next(i for i in state()["items"] if i["id"] == desk["id"])
        p0 = proj(d2["x"], d2["z"], 0.72); p1 = proj(0.5, 2.6, 0.72)  # onto the low bookshelf / plant
        pg.mouse.move(p0["x"], p0["y"]); pg.mouse.down()
        for k in range(1, 13): pg.mouse.move(p0["x"] + (p1["x"] - p0["x"]) * k / 12, p0["y"] + (p1["y"] - p0["y"]) * k / 12); time.sleep(0.03)
        pg.mouse.up(); time.sleep(0.9)
        st = state(); v = st["v"]
        check("collision flagged as overlap naming both items", any(x["rule"] == "overlap" and desk["id"] in x["items"] and len(x["items"]) == 2 for x in v["violations"]), "; ".join(x["message"] for x in v["violations"] if x["rule"] == "overlap"))
        check("red state blocks save", v["blocked"] and st["save"] == "blocked" and pg.is_visible("[data-testid=blocked]"))
        check("analysis tile shows the conflict count", pg.inner_text("[data-testid=analysis]").find(str(v["metrics"]["conflicts"])) >= 0)
        # 5. ⌘Z undo restores the previous position; Delete removes
        pg.keyboard.press("Meta+z"); time.sleep(0.4)
        d3 = next(i for i in state()["items"] if i["id"] == desk["id"]); check("⌘Z undoes the last move", abs(d3["x"] - d2["x"]) < 1e-6 and abs(d3["z"] - d2["z"]) < 1e-6)
        pg.evaluate(f"() => window.__arpStore.getState().select('{desk['id']}')"); pg.keyboard.press("Delete"); time.sleep(0.3)
        check("Delete removes the selected item", all(i["id"] != desk["id"] for i in state()["items"]))
        pg.wait_for_function("() => window.__arpStore.getState().saveState === 'saved'", timeout=10000)
        saved = api(a.api, "GET", f"/layouts/{cur['id']}")["layout"]
        check("layout persisted to the API after edits", len(saved["items"]) == n0)
        # 6. variant tab + creates a fork; reload keeps both
        pg.click(".tab.plus"); pg.wait_for_function("() => window.__arpStore.getState().layouts.length >= 2", timeout=10000); time.sleep(0.5)
        pg.reload(wait_until="networkidle"); pg.wait_for_function("() => window.__arpStore.getState().layouts.length >= 2", timeout=30000)
        check("new variant survives reload", True)
        b.close()
    bad = [r for r in results if not r[1]]
    print(f"E2E: {len(results) - len(bad)}/{len(results)} passed"); return 1 if bad else 0

if __name__ == "__main__": sys.exit(main())
