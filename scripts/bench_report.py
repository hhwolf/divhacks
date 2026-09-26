"""Collects perf evidence into .data/bench.json and prints a table (used by `make bench` and BENCHMARK.md)."""
from __future__ import annotations
import json, pathlib, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]

def timed(fn):
    t = time.perf_counter(); r = fn(); return r, round((time.perf_counter() - t) * 1000)

def api(base: str, method: str, path: str, body=None):
    req = urllib.request.Request(f"{base}{path}", method=method, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read())

def main() -> int:
    base = "http://localhost:8000"; report: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    v = ROOT / ".data/bench-validation.json"
    report["validation"] = json.loads(v.read_text()) if v.exists() else None
    try:
        api(base, "GET", "/health")
        r, ms = timed(lambda: api(base, "POST", "/rooms", {"sample": "nyc-bedroom"})); report["roomCreateMs"] = ms
        cur = r.get("currentLayout") or next(l for l in r["layouts"] if l["isCurrent"])
        d, ms = timed(lambda: api(base, "POST", "/furniture/from-link", {"url": f"{base}/fixtures/listings/desk"})); report["importLinkMs"] = ms
        did = (d.get("item") or d)["id"]
        _, ms = timed(lambda: api(base, "POST", "/agent/request", {"text": "Will this fit beside my window without moving my bed?", "roomId": r["room"]["id"], "baseLayoutId": cur["id"], "furnitureId": did, "channel": "app"})); report["agentRoundTripMs"] = ms
    except Exception as e:  # noqa: BLE001
        report["apiError"] = repr(e)
    (ROOT / ".data/bench.json").write_text(json.dumps(report, indent=1))
    for k, val in report.items(): print(f"{k:20s} {val}")
    return 0

if __name__ == "__main__": sys.exit(main())
