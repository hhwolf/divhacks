"""`make demo`: the full 3-minute script, headless, via Playwright + API. Exits non-zero on any failure.

Steps: load sample → Current Room from fixture → lock bed → simulated Photon message with the listing → Marketplace Desk
variant → drag desk into the door swing → red → drag back → compare. Writes docs/demo/demo-run.json with timings.
"""
from __future__ import annotations
import argparse, json, pathlib, sys, time, urllib.request
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

def api(base: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{base}{path}", method=method, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read())

def step(log: list, name: str, fn):
    t = time.perf_counter(); res = fn(); dt = time.perf_counter() - t
    log.append({"step": name, "ms": round(dt * 1000)}); print(f"  ✓ {name} ({dt*1000:.0f} ms)"); return res

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--web", default="http://localhost:5173"); ap.add_argument("--api", default="http://localhost:8000"); ap.add_argument("--shots", action="store_true")
    a = ap.parse_args(); log: list = []; out = ROOT / "docs/demo"; out.mkdir(parents=True, exist_ok=True)
    health = step(log, "API health", lambda: api(a.api, "GET", "/health")); print("   mode:", health.get("mode"), health.get("integrations"))
    r = step(log, "Load sample room", lambda: api(a.api, "POST", "/rooms", {"sample": "nyc-bedroom"}))
    room = r["room"]; cur = r.get("currentLayout") or next(l for l in r["layouts"] if l["isCurrent"])
    assert any(i["furnitureId"] == "bed_double" and i["locked"] for i in cur["items"]), "bed must be seeded locked"
    # Photon round trip with the listing link + question
    payload = json.loads((ROOT / "fixtures/photon/text-question.json").read_text())
    payload["message"]["text"] = payload["message"]["text"].replace("http://localhost:8000", a.api)
    ph = step(log, "Simulated Photon message → variant", lambda: api(a.api, "POST", "/webhooks/photon", payload))
    assert ph.get("layoutId"), f"webhook did not create a variant: {ph}"
    variant = step(log, "Fetch Marketplace Desk variant", lambda: api(a.api, "GET", f"/layouts/{ph['layoutId']}"))
    lay = variant["layout"]; assert lay["name"].startswith("Marketplace Desk"), lay["name"]; assert not lay["isCurrent"]
    bed = next(i for i in lay["items"] if i["furnitureId"] == "bed_double"); bed0 = next(i for i in cur["items"] if i["furnitureId"] == "bed_double")
    assert (bed["x"], bed["z"], bed["rotation"]) == (bed0["x"], bed0["z"], bed0["rotation"]), "bed moved!"
    desk = next((i for i in lay["items"] if i["furnitureId"] not in {x["furnitureId"] for x in cur["items"]}), None); assert desk, "no desk added"
    print("   reply:", ph.get("reply"))
    with sync_playwright() as p:
        b = p.chromium.launch(args=GL); pg = b.new_page(viewport={"width": 1920, "height": 1080})
        step(log, "Open variant in editor", lambda: (pg.goto(f"{a.web}/layout/{lay['id']}", wait_until="networkidle"), pg.wait_for_selector("canvas", timeout=30000), pg.wait_for_function("() => window.__arpStore && window.__arpStore.getState().items.length > 0", timeout=30000)))
        time.sleep(1.0)
        if a.shots: pg.screenshot(path=str(out / "01-variant.png"))
        def drag_into_door():
            pg.evaluate(f"() => {{ const s = window.__arpStore.getState(); s.select('{desk['id']}'); s.setDragging('{desk['id']}'); s.moveItem('{desk['id']}', 2.6, 2.4, {{}}); s.setDragging(null); s.moveItem('{desk['id']}', 2.6, 2.4, {{commit: true}}); }}")
            time.sleep(0.8)
            v = pg.evaluate("() => window.__arpStore.getState().validation")
            assert any(x["rule"] == "door_clearance" and desk["id"] in x["items"] for x in v["violations"]), f"expected red door-swing conflict, got {v['violations']}"
            return v
        step(log, "Drag desk into door swing → red", drag_into_door)
        if a.shots: pg.screenshot(path=str(out / "02-red.png"))
        def drag_back():
            pg.evaluate(f"() => {{ const s = window.__arpStore.getState(); s.moveItem('{desk['id']}', {desk['x']}, {desk['z']}, {{commit: true}}); }}"); time.sleep(0.9)
            v = pg.evaluate("() => window.__arpStore.getState().validation"); assert v["metrics"]["conflicts"] == 0, v["violations"]; return v
        step(log, "Drag back → clean", drag_back)
        pg.wait_for_function("() => window.__arpStore.getState().saveState === 'saved'", timeout=15000)
        step(log, "Compare view", lambda: (pg.goto(f"{a.web}/compare/{cur['id']}/{lay['id']}", wait_until="networkidle"), pg.wait_for_selector(".compare-metrics", timeout=30000), time.sleep(1.5)))
        if a.shots: pg.screenshot(path=str(out / "03-compare.png"))
        b.close()
    cmp = step(log, "Compare API", lambda: api(a.api, "GET", f"/layouts/{cur['id']}/compare/{lay['id']}")); assert cmp["added"], "compare should list the added desk"
    total = sum(x["ms"] for x in log)
    (out / "demo-run.json").write_text(json.dumps({"ok": True, "totalMs": total, "steps": log, "mode": health.get("mode"), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1))
    print(f"DEMO OK in {total/1000:.1f}s → docs/demo/demo-run.json"); return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print("DEMO FAILED:", repr(e)); sys.exit(1)
