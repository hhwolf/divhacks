"""Render 256x256 transparent PNG thumbnails for every manifest item via the web app's /thumb/:id route.

Usage: .venv/bin/python scripts/render_thumbs.py [--web http://localhost:5173]
"""
from __future__ import annotations
import argparse, json, pathlib, sys, time
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--web", default="http://localhost:5173"); ap.add_argument("--only", default=None)
    a = ap.parse_args()
    manifest = json.loads((ROOT / "assets/furniture/manifest.json").read_text())
    out = ROOT / "assets/furniture/thumbs"; out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 256, "height": 256}, device_scale_factor=1)
        for item in manifest["items"]:
            if a.only and item["id"] != a.only: continue
            pg.goto(f"{a.web}/thumb/{item['id']}", wait_until="networkidle")
            pg.wait_for_selector("canvas", timeout=15000); time.sleep(0.9)
            el = pg.query_selector("canvas"); assert el
            el.screenshot(path=str(out / f"{item['id']}.png"), omit_background=True)
            print("thumb", item["id"])
        b.close()
    return 0

if __name__ == "__main__": sys.exit(main())
