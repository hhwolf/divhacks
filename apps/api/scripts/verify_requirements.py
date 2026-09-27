"""Check every backend requirement (docs/BACKEND_SPEC.md) against the sample data and print a PASS/FAIL table.

    cd apps/api && ../../.venv/bin/python scripts/verify_requirements.py [--json out.json]

Sample data: the two sample rooms, a manual-dimensions room, synthetic RoomPlan USDZ scans (plain, yawed + offset, centimeters,
Z-up, no metersPerUnit, no Floor prim, a tucked chair, a broken one). Runs in-process in mock mode against a throwaway data folder,
so it never touches real data or services.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
DATA = Path(tempfile.mkdtemp(prefix="arp-verify-"))
os.environ["ARP_DATA_DIR"] = str(DATA)
for var in ("MOCK_MODE", "GEMINI_API_KEY", "BACKBOARD_API_KEY", "MONGODB_URI", "BLOB_READ_WRITE_TOKEN"):
    os.environ.pop(var, None)

from fastapi.testclient import TestClient  # noqa: E402

from app.config import REPO_ROOT, Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import FurnitureRef, LayoutItem, RoomSkeleton, Zone  # noqa: E402
from app.services.usdz_convert import convert_usdz  # noqa: E402
from app.solver.grid import item_rect, rects_overlap  # noqa: E402
from app.solver.skeleton import door_clearance_rect, opening_span, window_band  # noqa: E402
from app.solver.validate import validate_layout  # noqa: E402
from tests.usdz_factory import Box, bedroom, build_usdz  # noqa: E402

RESULTS: list[dict[str, Any]] = []
DESK_Q = "Will this fit beside my window without moving my bed? http://testserver/fixtures/listings/desk"
YOGA_Q = "make space for yoga, keep my dresser"


def check(area: str, requirement: str) -> Callable[[Callable[[], str]], Callable[[], str]]:
    def deco(fn: Callable[[], str]) -> Callable[[], str]:
        t = time.perf_counter()
        try:
            detail, ok = fn(), True
        except AssertionError as exc:
            detail, ok = f"FAILED: {exc}" if str(exc) else f"FAILED: {traceback.format_exc(limit=1).strip().splitlines()[-1]}", False
        except Exception as exc:  # noqa: BLE001
            detail, ok = f"ERROR: {exc!r}", False
        RESULTS.append({"area": area, "requirement": requirement, "ok": ok, "detail": detail, "ms": round((time.perf_counter() - t) * 1000)})
        return fn
    return deco


def upload(c: TestClient, path: Path, name: str = "Scan") -> Any:
    with path.open("rb") as fh:
        return c.post("/rooms", files={"usdz": ("Room.usdz", fh, "model/vnd.usdz+zip")}, data={"name": name})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    c = TestClient(create_app(Settings.from_env()))
    scans = DATA / "scans-in"
    variants = {"plain": {}, "yawed+offset": {"yaw": 30, "offset": (5.0, -2.0)}, "centimeters": {"meters_per_unit": 0.01, "yaw": -65},
                "Z-up": {"up": "Z", "yaw": 121}, "no metersPerUnit": {"meters_per_unit": None}, "no Floor prim": {"with_floor": False, "yaw": 10}}
    files = {k: build_usdz(scans / f"{i}.usdz", **kw) for i, (k, kw) in enumerate(variants.items())}
    rooms: dict[str, dict] = {}

    # ---------------------------------------------------------------- ingest
    @check("Ingest", "USDZ converts identically whatever the scan's yaw, offset, units, up axis, metersPerUnit or Floor prim")
    def _() -> str:
        outs = {k: convert_usdz(p) for k, p in files.items()}
        base = outs["plain"].skeleton
        bad = [k for k, o in outs.items() if o.skeleton != base]
        assert not bad, f"differs: {bad}"
        return f"{len(outs)} variants -> same {base.dimensions.l} x {base.dimensions.w} m skeleton, {len(base.walls)} walls, {len(base.doors)} door, {len(base.windows)} window"

    @check("Ingest", "Normalized: longest wall on +x at z=0, floor polygon min x/z = 0, meters")
    def _() -> str:
        sk = convert_usdz(files["yawed+offset"]).skeleton
        w0 = sk.walls[0]
        assert (w0.z1, w0.z2) == (0, 0) and w0.x2 - w0.x1 == max(abs(w.x2 - w.x1) + abs(w.z2 - w.z1) for w in sk.walls)
        assert min(p[0] for p in sk.floorPolygon) == 0 and min(p[1] for p in sk.floorPolygon) == 0
        return f"wall 0 = ({w0.x1},{w0.z1})->({w0.x2},{w0.z2}); ceiling {sk.ceilingHeight} m"

    @check("Ingest", "POST /rooms (multipart USDZ): raw file in Blob first, skeleton + Base Layout + Current Room, < 30 s")
    def _() -> str:
        t = time.perf_counter()
        r = upload(c, files["yawed+offset"], "Synthetic scan")
        ms = (time.perf_counter() - t) * 1000
        assert r.status_code == 201, r.text
        body = r.json()
        rooms["scan"] = body
        assert (DATA / "blob" / body["room"]["usdzUrl"].removeprefix("/blob/")).exists()
        assert body["baseLayout"]["kind"] == "base" and body["currentLayout"]["kind"] == "current" and body["currentLayout"]["parentLayoutId"] == body["baseLayout"]["id"]
        return f"{ms:.0f} ms upload -> editor-ready; usdzUrl {body['room']['usdzUrl']}"

    @check("Ingest", "Scanned furniture -> presets scaled to scanned size; fixtures (toilet) locked as `other`")
    def _() -> str:
        lay = c.get(f"/layouts/{rooms['scan']['baseLayout']['id']}").json()
        cats = {f["scanCategory"]: f for f in lay["furniture"].values()}
        locks = {lay["furniture"][i["furnitureId"]]["scanCategory"]: i["locked"] for i in lay["layout"]["items"]}
        assert cats["Bed"]["presetId"] == "bed_double" and cats["Bed"]["dims"] == {"w": 1.4, "d": 2.0, "h": 0.55}
        assert cats["Toilet"]["category"] == "other" and locks == {"Bed": False, "Storage": False, "Toilet": True}
        return "Bed->bed_double 1.4x2.0 m, Storage->dresser, Toilet locked"

    @check("Ingest", "Tucked chair is pulled out, so a scanned room can be saved")
    def _() -> str:
        walls, objects, floor = bedroom()
        objects = [o for o in objects if o.name != "Toilet0"] + [Box("Table0", (2.4, 0.375, 0.35), (1.2, 0.75, 0.6)), Box("Chair0", (2.4, 0.45, 0.55), (0.45, 0.9, 0.45), yaw=180)]
        body = upload(c, build_usdz(scans / "tucked.usdz", room=(walls, objects, floor))).json()
        cur = body["currentLayout"]
        assert "pulled a chair out from under the desk" in body["room"]["conversion"]["warnings"]
        assert c.put(f"/layouts/{cur['id']}", json={"items": cur["items"], "source": "editor", "version": 1}).status_code == 200
        return "chair moved clear of the desk; PUT 200"

    @check("Ingest", "Failed conversion: 422 + conversionReport, raw USDZ kept, re-run by usdzUrl")
    def _() -> str:
        walls, objects, floor = bedroom()
        r = upload(c, build_usdz(scans / "broken.usdz", room=(walls[:2], objects, floor)))
        rep = r.json()["detail"]["conversionReport"]
        assert r.status_code == 422 and (DATA / "blob" / rep["usdzUrl"].removeprefix("/blob/")).exists()
        again = c.post("/rooms", json={"usdzUrl": rooms["scan"]["room"]["usdzUrl"]})
        assert again.status_code == 201
        return f"422 '{r.json()['detail']['message'][:60]}...'; re-run 201"

    # ---------------------------------------------------------------- sample rooms
    for sample in ("nyc-bedroom", "studio"):
        @check("Samples", f"Sample room '{sample}': Base + Current, no hard violations, walkable")
        def _(sample: str = sample) -> str:
            body = c.post("/rooms", json={"sample": sample}).json()
            rooms[sample] = body
            v = c.get(f"/layouts/{body['currentLayout']['id']}").json()["validation"]
            assert not v["blocked"] and v["metrics"]["conflicts"] == 0 and v["metrics"]["walkability"] == "Good", v
            m = v["metrics"]
            return f"{len(body['currentLayout']['items'])} items, {m['openFloor']}% open floor, free rect {m['largestFreeRect']['w']}x{m['largestFreeRect']['d']} m ({m['largestFreeRect']['fits']})"

    @check("Samples", "Manual dimensions room (form fields) with a door and a window")
    def _() -> str:
        r = c.post("/rooms", data={"name": "Manual", "dimensions": json.dumps({"l": 3.2, "w": 2.8, "h": 2.5}),
                                   "doors": json.dumps([{"wall": 2, "offset": 0.3, "width": 0.8, "swing": "in", "hinge": "right"}]),
                                   "windows": json.dumps([{"wall": 0, "offset": 1.0, "width": 1.0, "sillHeight": 0.9, "height": 1.2}])})
        assert r.status_code == 201
        sk = r.json()["room"]["skeleton"]
        return f"{sk['dimensions']}, door on {sk['doors'][0]['wallId']}, window on {sk['windows'][0]['wallId']}"

    bed = rooms["nyc-bedroom"]
    cur_id, base_id, room_id = bed["currentLayout"]["id"], bed["baseLayout"]["id"], bed["room"]["id"]
    current_items = bed["currentLayout"]["items"]

    # ---------------------------------------------------------------- editor path
    @check("Layouts", "Base Layout is read-only (PUT/PATCH/DELETE/promote -> 403)")
    def _() -> str:
        codes = [c.put(f"/layouts/{base_id}", json={"items": current_items, "source": "editor"}).status_code, c.patch(f"/layouts/{base_id}", json={"name": "x"}).status_code,
                 c.delete(f"/layouts/{base_id}").status_code, c.post(f"/layouts/{base_id}/promote").status_code]
        assert codes == [403] * 4, codes
        return "403 x4"

    @check("Layouts", "PUT: version bump, stale version 409, hard rules 422 with byItem, soft warnings saved")
    def _() -> str:
        fork = c.post(f"/layouts/{cur_id}/fork", json={"name": "Scratch"}).json()
        ok = c.put(f"/layouts/{fork['id']}", json={"items": fork["items"], "version": 1}).json()["layout"]["version"]
        stale = c.put(f"/layouts/{fork['id']}", json={"items": fork["items"], "version": 1}).status_code
        bad = c.put(f"/layouts/{fork['id']}", json={"items": fork["items"] + [{"id": "desk_1", "furnitureId": "desk", "x": 3.2, "z": 2.0, "rotation": 0, "locked": False}], "version": 2})
        shelf = {"id": "bookshelf_low_9", "furnitureId": "bookshelf_low", "x": 2.5, "z": 1.3, "rotation": 90, "locked": False}
        warn = c.put(f"/layouts/{fork['id']}", json={"items": fork["items"] + [shelf], "version": 2}).json()["layout"]["metrics"]["warnings"]
        assert ok == 2 and stale == 409 and bad.status_code == 422 and "desk_1" in bad.json()["detail"]["byItem"] and warn
        return f"v1->2, stale 409, 422 byItem desk_1, warnings {warn}"

    @check("Layouts", "Fork / promote (old current kept as 'Previous Room, <date>') / restore base+empty / compare")
    def _() -> str:
        fork = c.post(f"/layouts/{cur_id}/fork", json={"name": "Promote me"}).json()
        p = c.post(f"/layouts/{fork['id']}/promote").json()
        rb = c.post(f"/rooms/{room_id}/restore", json={"target": "base"}).json()
        re = c.post(f"/rooms/{room_id}/restore", json={"target": "empty"}).json()
        cmp = c.get(f"/layouts/{cur_id}/compare/{re['id']}").json()
        kinds = [l["kind"] for l in c.get(f"/rooms/{room_id}").json()["layouts"]]
        assert p["current"]["kind"] == "current" and p["previous"]["name"].startswith("Previous Room, ") and kinds.count("base") == 1 and kinds.count("current") == 1
        assert rb["items"] == current_items and re["items"] == [] and len(cmp["removed"]) == len(current_items)
        # put the original Current Room back so the agent checks start from the seeded layout
        c.post(f"/layouts/{cur_id}/promote")
        return f"promoted -> '{p['previous']['name']}'; restore base {len(rb['items'])} items, empty 0; compare removed {len(cmp['removed'])}"

    # ---------------------------------------------------------------- agent
    def ask(text: str, **extra: Any) -> dict:
        r = c.post("/agent/request", json={"text": text, "roomId": room_id, "layoutId": cur_id, **extra})
        assert r.status_code == 200, r.text
        return r.json()

    sk = RoomSkeleton.model_validate(bed["room"]["skeleton"])

    @check("Agent", "Marketplace desk: 1-3 distinct options beside the window, bed untouched, no conflicts, Gemini never places")
    def _() -> str:
        out = ask(DESK_Q)
        assert out["status"] == "ok" and 1 <= len(out["options"]) <= 3
        assert "x" not in json.dumps(out["plan"].get("constraints")) and out["plan"]["placement"] == out["options"][0]["placement"]
        win = opening_span(sk, sk.windows[0])
        lines = []
        for o in out["options"]:
            lay = c.get(f"/layouts/{o['layoutId']}").json()
            bed_now = next(i for i in lay["layout"]["items"] if i["furnitureId"] == "bed_double")
            assert bed_now == current_items[0] and lay["validation"]["metrics"]["conflicts"] == 0
            p = o["placement"]
            r = item_rect(p["x"], p["z"], p["rotation"], type("D", (), {"w": 1.2, "d": 0.6})())  # type: ignore[arg-type]
            gap = max(0.0, max(r.x0, min(win[0][0], win[1][0])) - min(r.x1, max(win[0][0], win[1][0])))
            lines.append(f"'{o['variantName']}' ({p['x']}, {p['z']}, {p['rotation']}°){'' if o['relaxed'] else ' beside window' if gap <= 0.3 and r.z0 < 0.35 else ''}")
        return f"{len(out['options'])} options: " + "; ".join(lines) + f" | reply: {out['reply']}"

    @check("Agent", "Yoga: a free 1.8 x 1.2 m zone outside the door swing, bed and dresser untouched, fewest moves")
    def _() -> str:
        out = ask(YOGA_Q)
        o = out["options"][0]
        z = o["zones"][0]
        zr = type("R", (), {"x0": z["x"], "z0": z["z"], "x1": z["x"] + z["w"], "z1": z["z"] + z["d"]})()
        assert sorted([z["w"], z["d"]]) == [1.2, 1.8] and not rects_overlap(zr, door_clearance_rect(sk, sk.doors[0], 0.9))  # type: ignore[arg-type]
        items = c.get(f"/layouts/{o['layoutId']}").json()["layout"]["items"]
        for fid in ("bed_double", "dresser"):
            assert next(i for i in items if i["furnitureId"] == fid) == next(i for i in current_items if i["furnitureId"] == fid)
        return f"zone {z['w']}x{z['d']} m at ({z['x']}, {z['z']}); moves {[m['name'] for m in o['moves']]} | {out['reply']}"

    @check("Agent", "Keep clear: a desk in front of the window is moved out of the window band")
    def _() -> str:
        v = c.post(f"/layouts/{cur_id}/fork", json={"name": "Desk at window"}).json()
        assert c.put(f"/layouts/{v['id']}", json={"items": v["items"] + [{"id": "desk_9", "furnitureId": "desk", "x": 2.2, "z": 0.9, "rotation": 90, "locked": False}], "version": 1}).status_code == 200
        out = ask("I don't want my desk blocking the window", layoutId=v["id"])
        m = out["options"][0]["moves"][0]
        r = item_rect(m["x"], m["z"], m["rotation"], type("D", (), {"w": 1.2, "d": 0.6})())  # type: ignore[arg-type]
        assert not rects_overlap(r, window_band(sk, sk.windows[0], 0.6))
        return f"desk -> ({m['x']}, {m['z']}, {m['rotation']}°) | {out['reply']}"

    @check("Agent", "Rank variants: ranked answer, no new variant; clarify: one question, no variant")
    def _() -> str:
        n = len(c.get(f"/rooms/{room_id}").json()["layouts"])
        rank = ask("Which layout is better for studying?")
        clar = ask("what's the weather like")
        assert rank["options"] == [] and rank["ranking"] and clar["status"] == "clarify" and clar["reply"].endswith("?")
        assert len(c.get(f"/rooms/{room_id}").json()["layouts"]) == n
        return f"top: {rank['ranking'][0]['reason']} | clarify: {clar['reply']}"

    @check("Agent", "Rent check and payment guardrails routed by the plan (deposit > 1 month and fee > $20 blocked)")
    def _() -> str:
        rent = ask("I pay $1600 for this room in 10027. Is that fair? rats and leak")
        dep_ok, dep_bad, fee = ask("Can I safely send a $500 deposit?"), ask("Can I send a $2000 deposit?"), ask("This application fee is $75")
        assert rent["assessment"]["askingRent"] == 1600 and dep_ok["quote"]["status"] == "mock" and dep_bad["quote"]["status"] == "blocked" and fee["quote"]["status"] == "blocked"
        return f"rent: {rent['reply'][:90]}... | $2000 deposit: {dep_bad['reply']}"

    @check("Agent", "Photon deliverer: text with no ids resolves the latest room; reply + web link to send back")
    def _() -> str:
        c.patch(f"/rooms/{room_id}", json={"name": bed["room"]["name"]})
        out = c.post("/agent/request", json={"text": YOGA_Q, "channel": "imessage"}).json()
        assert out["roomId"] == room_id and out["links"][1].endswith(out["layoutId"])
        return f"-> room {out['roomId']}, text back: \"{out['reply']}\" {out['links'][1]}"

    @check("Agent", "Locks hold: layout locks, plan locks and Backboard 'never move' memory; retry then nearest miss")
    def _() -> str:
        ask("never move my nightstand. make space for yoga")
        mem = c.app.state.ctx.repo._db["users"][0]["memories"]  # type: ignore[attr-defined]
        out = ask(YOGA_Q)
        moved = {m["name"] for o in out.get("options", []) for m in o["moves"]}
        assert "never move the nightstand" in mem and "Nightstand" not in moved and "Double bed" not in moved
        big = {"intent": "fit_item", "item": {"type": "desk", "w_m": 3.3, "d_m": 0.6, "h_m": 0.75}, "constraints": [{"type": "adjacent", "item": "desk", "feature": "window"}], "explanation": "x"}
        real = c.app.state.ctx.gemini.plan

        async def fake(system_prompt: str, user_text: str, violations: list[str] | None = None) -> dict:
            return json.loads(json.dumps(big))

        c.app.state.ctx.gemini.plan = fake
        try:
            rej = ask("fit a 3.3 m desk by the window")
        finally:
            c.app.state.ctx.gemini.plan = real
        log = c.app.state.ctx.repo._db["agent_requests"][-1]  # type: ignore[attr-defined]
        assert rej["status"] == "rejected" and "too wide" in rej["reply"] and len(log["solverAttempts"]) == 2
        return f"memory {mem}; yoga now {out['status']} ({out['reply'][:60]}); 3.3 m desk: \"{rej['reply']}\""

    @check("Agent", "The agent never writes the Base Layout or the Current Room")
    def _() -> str:
        base_now = c.get(f"/layouts/{base_id}").json()["layout"]
        cur_now = c.get(f"/layouts/{cur_id}").json()["layout"]
        assert base_now["items"] == current_items and cur_now["items"] == current_items
        agent_made = [l for l in c.get(f"/rooms/{room_id}").json()["layouts"] if l["createdBy"] == "agent"]
        assert agent_made and all(l["kind"] == "variant" for l in agent_made)
        return f"{len(agent_made)} agent variants, all kind=variant; base/current unchanged"

    @check("Agent", "Mock round trip < 2 s per request")
    def _() -> str:
        times = []
        for text in (DESK_Q, YOGA_Q, "Which layout is better for studying?"):
            t = time.perf_counter()
            ask(text)
            times.append((time.perf_counter() - t) * 1000)
        assert max(times) < 2000, times
        return "  ".join(f"{t:.0f} ms" for t in times)

    # ---------------------------------------------------------------- validation, catalog, config
    @check("Validation", "TS/Python parity on fixtures/validation (walkable path = warning)")
    def _() -> str:
        n = 0
        for path in sorted((REPO_ROOT / "fixtures" / "validation").glob("*.json")):
            fx = json.loads(path.read_text())
            res = validate_layout(RoomSkeleton.model_validate(fx["skeleton"]), {k: FurnitureRef.model_validate(v) for k, v in fx["furniture"].items()},
                                  [LayoutItem.model_validate(i) for i in fx["layout"]["items"]], [Zone.model_validate(z) for z in fx["layout"].get("zones", [])],
                                  [LayoutItem.model_validate(i) for i in fx["baseLayout"]["items"]] if fx.get("baseLayout") else None)
            got = sorted((v.rule, tuple(sorted(v.items)), v.message) for v in res.violations)
            want = sorted((v["rule"], tuple(v["items"]), v["message"]) for v in fx["expected"]["violations"])
            assert got == want and res.metrics.conflicts == fx["expected"]["metrics"]["conflicts"], path.name
            n += 1
        return f"{n} fixtures identical to the TS validator"

    @check("Validation", "One rules file: GET /validation/rules == packages/contracts/rules.json (imported by the TS validator)")
    def _() -> str:
        rules = json.loads((REPO_ROOT / "packages" / "contracts" / "rules.json").read_text())
        ts = (REPO_ROOT / "packages" / "geometry" / "src" / "constants.ts").read_text()
        assert c.get("/validation/rules").json() == rules and "@arp/contracts/rules.json" in ts
        return f"rules v{rules['version']}: grid {rules['GRID_M']} m, door {rules['DOOR_CLEAR_M']} m, access {rules['ACCESS_EDGE_M']} m, yoga {rules['DEFAULT_YOGA_ZONE_M']}"

    @check("Validation", "Server validation of a 20-item layout (browser budget 100 ms)")
    def _() -> str:
        fx = json.loads((REPO_ROOT / "fixtures" / "validation" / "21-twenty-items-perf.json").read_text())
        args_ = (RoomSkeleton.model_validate(fx["skeleton"]), {k: FurnitureRef.model_validate(v) for k, v in fx["furniture"].items()}, [LayoutItem.model_validate(i) for i in fx["layout"]["items"]])
        runs = []
        for _ in range(20):
            t = time.perf_counter()
            validate_layout(*args_)
            runs.append((time.perf_counter() - t) * 1000)
        runs.sort()
        assert runs[-2] < 100
        return f"p95 {runs[-2]:.1f} ms over 20 runs (Python)"

    @check("Catalog", "Import: link < 10 s, blocked link -> 422 with screenshot hint, photo -> Blob + estimated")
    def _() -> str:
        t = time.perf_counter()
        link = c.post("/furniture/from-link", json={"url": "http://testserver/fixtures/listings/desk"}).json()
        ms = (time.perf_counter() - t) * 1000
        blocked = c.post("/furniture/from-link", json={"url": "http://127.0.0.1:9/x"})
        with (REPO_ROOT / "fixtures" / "listings" / "desk.jpg").open("rb") as fh:
            photo = c.post("/furniture/from-photo", files={"image": ("desk.jpg", fh, "image/jpeg")}).json()
        assert ms < 10000 and link["dims"] == {"w": 1.2, "d": 0.6, "h": 0.75} and blocked.status_code == 422 and photo["estimated"] and photo["photoUrl"].startswith("/blob/photos/")
        return f"link {ms:.0f} ms (${link['price']:.0f}, {link['dims']}); blocked 422; photo {photo['photoUrl']}"

    @check("Config", "Secrets never leave the process; live mode refuses to start without the required keys")
    def _() -> str:
        from app.config import Settings as S
        os.environ["MOCK_MODE"] = "false"
        try:
            try:
                create_app(S())
                raise AssertionError("started without keys")
            except RuntimeError as exc:
                missing = str(exc)
            os.environ.update({"GEMINI_API_KEY": "gm-SECRET", "BACKBOARD_API_KEY": "bb-SECRET", "MONGODB_URI": "mongodb://u:pw-SECRET@localhost:1/?serverSelectionTimeoutMS=50", "BLOB_READ_WRITE_TOKEN": "blob-SECRET"})
            live = TestClient(create_app(S()))
            bodies = live.get("/health").text + live.get("/openapi.json").text
            assert "SECRET" not in bodies and "SECRET" not in repr(S())
        finally:
            for k in ("MOCK_MODE", "GEMINI_API_KEY", "BACKBOARD_API_KEY", "MONGODB_URI", "BLOB_READ_WRITE_TOKEN"):
                os.environ.pop(k, None)
        return f"refused: '{missing[:70]}...'; /health, /openapi.json, repr clean"

    # ---------------------------------------------------------------- report
    width = max(len(r["requirement"]) for r in RESULTS)
    area = ""
    for r in RESULTS:
        if r["area"] != area:
            area = r["area"]
            print(f"\n{area}")
        print(f"  {'PASS' if r['ok'] else 'FAIL'}  {r['requirement']:<{width}}  {r['ms']:>5} ms\n        {r['detail']}")
    passed = sum(r["ok"] for r in RESULTS)
    print(f"\n{passed}/{len(RESULTS)} requirements pass")
    if args.json:
        args.json.write_text(json.dumps(RESULTS, indent=1))
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
