"""Merge check: can Gemini, running the interior-designer skill, fully understand the 3D room and follow the skill?

    .venv/bin/python apps/api/scripts/check_designer.py            # all checks; live Gemini quiz only when GEMINI_API_KEY is set
    .venv/bin/python apps/api/scripts/check_designer.py --json out.json
    .venv/bin/python apps/api/scripts/check_designer.py --sync ~/.claude/skills/.../interior-designer   # refresh the verbatim copy + lock

A. Skill fidelity     the copy in app/agent/interior-designer is byte-identical to the lock (and to the installed skill when found),
                      and Gemini's system prompt carries SKILL.md and the references it calls for, unaltered.
B. 3D understanding   the <scene> in the prompt round-trips to exactly what the editor draws (walls, openings, every item's
                      footprint and facing, compared with three.js's rotation), the skill's validate_layout.py agrees with the app's
                      validator on hard rules over sample and random layouts, and every GLB the editor loads measures sane with the
                      skill's inspect_glb.py (seating and beds also have their tall back where the data says the back is).
C. Designer behavior  requests on every sample room come back as 1-3 distinct options, each passing both validators, locks kept,
                      with an explanation, an honest tradeoff and plain words (the skill's banned-word table).
D. Live Gemini        with a key: a comprehension quiz on the real prompt, scored against the geometry, and a live plan request.
Exit code 1 if any check FAILs. SKIP is not a pass.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import re
import shutil
import struct
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import prompts, review, scene, skill  # noqa: E402
from app.catalog import PRESETS  # noqa: E402
from app.config import REPO_ROOT, Settings  # noqa: E402
from app.models import FurnitureItem, Layout, LayoutItem, RoomSkeleton  # noqa: E402
from app.services import SAMPLES, load_sample, seed_items  # noqa: E402
from app.solver.grid import front_dir, item_rect  # noqa: E402
from app.solver.skeleton import opening_span  # noqa: E402
from app.solver.validate import validate_layout  # noqa: E402

ROOMS = {**{k: v.removesuffix(".json") for k, v in SAMPLES.items()}, "roomplan-export": "roomplan-export-sample"}
ASSETS = REPO_ROOT / "assets" / "furniture"
# SKILL.md "How you talk": marketing words and trade words it swaps for everyday ones.
BANNED = ("stunning", "elevate", "oasis", "curated", "circulation", "traffic flow", "clearance", "focal point", "zoning", "negative space",
          "visual weight", "anchor piece", "egress", "task lighting", "ambient lighting", "option 2", "option 3")
# Pieces whose tallest part is their back (headboard, backrest): the back must sit at -z in the model, so +z is the front the data uses.
TALL_BACK = ("bed_double", "bed_single", "chair", "chair_desk", "sofa", "armchair")
RANDOM_LAYOUTS = 150


@dataclass
class Check:
    group: str
    name: str
    status: str = "PASS"  # PASS | FAIL | SKIP
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def _check(group: str, name: str, fn: Callable[[], tuple[bool | None, str, dict[str, Any]]]) -> Check:
    try:
        ok, detail, data = fn()
    except Exception as exc:  # noqa: BLE001 - a crashing check is a failing check, reported with its reason
        return Check(group, name, "FAIL", f"{type(exc).__name__}: {exc}")
    return Check(group, name, "SKIP" if ok is None else "PASS" if ok else "FAIL", detail, data)


def room(name: str) -> tuple[RoomSkeleton, list[LayoutItem], str | None]:
    d = json.loads((REPO_ROOT / "fixtures" / "rooms" / f"{ROOMS[name]}.json").read_text()) if name == "roomplan-export" else load_sample(name)
    return RoomSkeleton.model_validate(d["skeleton"]), seed_items(d["objects"]), ", ".join(d.get("spaceTypes", [])) or None


def layout(items: list[LayoutItem], name: str = "Current Room") -> Layout:
    return Layout(id="check", roomId="check", name=name, isCurrent=True, items=items, createdAt="t", updatedAt="t")


# ---------- A. skill fidelity ----------

def installed_skill() -> Path | None:
    env = os.environ.get("INTERIOR_DESIGNER_SKILL_DIR")
    if env:
        return Path(env).expanduser()
    hits = sorted(Path.home().glob(".claude/skills/**/interior-designer/SKILL.md"))
    return hits[0].parent if hits else None


def a_copy_matches_lock() -> tuple[bool, str, dict[str, Any]]:
    drift = skill.drift()
    n = len(skill.lock()["files"])  # type: ignore[arg-type]
    return not drift, f"{n} files byte-identical to interior-designer.lock.json" if not drift else f"drifted: {', '.join(drift)}", {"files": n}


def a_copy_matches_installed() -> tuple[bool | None, str, dict[str, Any]]:
    src = installed_skill()
    if src is None or not (src / "SKILL.md").exists():
        return None, "installed skill not found (set INTERIOR_DESIGNER_SKILL_DIR)", {}
    theirs, ours = skill.file_hashes(src), skill.file_hashes()
    diff = sorted(k for k in theirs.keys() | ours.keys() if theirs.get(k) != ours.get(k))
    return not diff, f"identical to {src}" if not diff else f"differs from {src}: {', '.join(diff)}", {"source": str(src)}


def a_prompt_carries_skill() -> tuple[bool, str, dict[str, Any]]:
    sk, items, purpose = room("nyc-bedroom")
    base = layout(items)
    plain = prompts.build_system_prompt(sk, base, PRESETS, [], None, purpose, "Will a desk fit beside my window?")
    access = prompts.build_system_prompt(sk, base, PRESETS, ["I use a wheelchair"], None, purpose, "Where should the desk go?")
    styled = prompts.build_system_prompt(sk, base, PRESETS, [], None, purpose, "Make it feel japandi, what colors?")
    furnish = prompts.build_furnish_prompt(sk, layout([]), PRESETS, purpose, "cozy study")
    problems = []
    for label, text in (("request", plain), ("accessibility", access), ("style", styled), ("furnish", furnish)):
        if skill.read("SKILL.md") not in text:
            problems.append(f"{label}: SKILL.md not verbatim")
        for rel in skill.ALWAYS_READ:
            if skill.read(rel) not in text:
                problems.append(f"{label}: {rel} missing")
    if skill.read(skill.ACCESSIBLE_REF) in plain or skill.read(skill.STYLE_REF) in plain:
        problems.append("plain request loaded a read-when-needed reference")
    if skill.read(skill.ACCESSIBLE_REF) not in access:
        problems.append("wheelchair memory didn't load accessible-design.md")
    if skill.read(skill.STYLE_REF) not in styled or skill.read(skill.STYLE_REF) not in furnish:
        problems.append("style request didn't load style-and-color.md")
    return not problems, "; ".join(problems) or "SKILL.md + 3 references verbatim; accessible-design / style-and-color load when the skill says to", {
        "promptChars": len(plain)}


def a_skill_scripts_run_as_documented() -> tuple[bool, str, dict[str, Any]]:
    data = json.loads(skill.read("assets/sample_room.json"))
    mod = skill.script("validate_layout")
    common = {"room": data["room"], "furniture": data["furniture"], "base_items": data["base_items"], "clear_zones": data["clear_zones"]}
    res = {o["name"]: mod.validate(items=o["items"], **common) for o in data["options"]}
    bad = res["Bad: desk by door, bed moved"]
    ok = res["Window Desk"]["ok"] and not bad["ok"] and {v["rule"] for v in bad["violations"]} >= {"locked_moved"}
    return ok, "assets/sample_room.json: " + ", ".join(f"{k} ok={v['ok']}" for k, v in res.items()), {}


# ---------- B. 3D understanding ----------

def three_front(rotation: float) -> tuple[int, int]:
    """Where +z (the model's front) points after three.js rotation.y = rotation (Furniture.tsx): R_y(t)(0,0,1) = (sin t, cos t)."""
    t = math.radians(rotation)
    return round(math.sin(t)), round(math.cos(t))


def b_scene_round_trip() -> tuple[bool, str, dict[str, Any]]:
    problems, counted = [], {"walls": 0, "doors": 0, "windows": 0, "outlets": 0, "items": 0}
    for name in ROOMS:
        sk, items, purpose = room(name)
        prompt = prompts.build_system_prompt(sk, layout(items), PRESETS, [], None, purpose)
        got = prompts.parse_scene(prompt)
        r = got["room"]
        if [tuple(p) for p in r["floor_polygon"]] != [tuple(p) for p in sk.floorPolygon]:
            problems.append(f"{name}: floor polygon")
        for i, w in enumerate(sk.walls):
            gw = r["walls"][i]
            if (gw["a"], gw["b"], gw["height"]) != ([w.x1, w.z1], [w.x2, w.z2], w.height):
                problems.append(f"{name}: wall{i}")
        for key, src in (("doors", sk.doors), ("windows", sk.windows)):
            if len(r[key]) != len(src):
                problems.append(f"{name}: {key} count")
            for g, o in zip(r[key], src, strict=False):
                a, b = opening_span(sk, o)
                if max(abs(g["a"][0] - a[0]), abs(g["a"][1] - a[1]), abs(g["b"][0] - b[0]), abs(g["b"][1] - b[1])) > 1e-3 or g["wall"] != f"wall{o.wall}":
                    problems.append(f"{name}: {g['id']} span")
                if key == "windows" and (g["sill"], g["height"]) != (o.sillHeight, o.height):  # type: ignore[union-attr]
                    problems.append(f"{name}: {g['id']} heights")
                if key == "doors" and (g["swing"], g["hinge"], g["height"]) != (o.swing, o.hinge, o.height):  # type: ignore[union-attr]
                    problems.append(f"{name}: {g['id']} swing/hinge")
        if len(r["outlets"]) != len(sk.outlets):
            problems.append(f"{name}: outlets")
        box = skill.script("validate_layout").Box
        placed = {p["furnitureId"]: p for p in got["base_items"]}  # type: ignore[union-attr]
        for it in items:
            f, p, gf = PRESETS[it.furnitureId], placed.get(it.id), got["furniture"].get(it.id)  # type: ignore[union-attr]
            if p is None or gf is None:
                problems.append(f"{name}: {it.id} missing")
                continue
            if (p["x"], p["z"], p["rotation"], p["locked"]) != (it.x, it.z, it.rotation, it.locked) or (gf["w"], gf["d"], gf["h"]) != (f.dims.w, f.dims.d, f.dims.h):
                problems.append(f"{name}: {it.id} values")
            # footprint the skill computes vs the one the editor draws (Furniture.tsx uses footprint()/item_rect)
            bx = box.from_item(p["x"], p["z"], gf["w"], gf["d"], p["rotation"])
            xs, zs = [c[0] for c in bx.corners()], [c[1] for c in bx.corners()]
            rect = item_rect(it.x, it.z, it.rotation, f.dims)
            if max(abs(min(xs) - rect.x0), abs(max(xs) - rect.x1), abs(min(zs) - rect.z0), abs(max(zs) - rect.z1)) > 1e-6:
                problems.append(f"{name}: {it.id} footprint")
            # front: skill's depth axis, the app's front_dir and three.js's rotated +z must be the same direction
            skill_front = (round(bx.uz[0]), round(bx.uz[1]))
            if not (skill_front == front_dir(it.rotation) == three_front(it.rotation)):
                problems.append(f"{name}: {it.id} front skill={skill_front} app={front_dir(it.rotation)} three={three_front(it.rotation)}")
        for k, v in (("walls", sk.walls), ("doors", sk.doors), ("windows", sk.windows), ("outlets", sk.outlets), ("items", items)):
            counted[k] += len(v)
    # all four rotations, not just the ones the samples happen to use
    for rot in (0, 90, 180, 270):
        bx = skill.script("validate_layout").Box.from_item(0, 0, 1.2, 0.6, rot)
        if (round(bx.uz[0]), round(bx.uz[1])) != front_dir(rot) or front_dir(rot) != three_front(rot):
            problems.append(f"rotation {rot}: front conventions differ")
    return not problems, "; ".join(problems[:6]) or ("every wall, opening, outlet and item round-trips; footprints and fronts match three.js at 0/90/180/270 ("
                                                     + ", ".join(f"{v} {k}" for k, v in counted.items()) + f" across {len(ROOMS)} rooms)"), counted


def _rules(v: dict[str, Any] | Any, *, skill_side: bool) -> dict[str, set[tuple[str, ...]]]:
    out: dict[str, set[tuple[str, ...]]] = {"bounds": set(), "overlap": set(), "door": set(), "locked": set()}
    names = {"room_bounds": "bounds", "bounds": "bounds", "overlap": "overlap", "door_clearance": "door", "locked_moved": "locked", "locked": "locked"}
    for x in (v["violations"] if skill_side else v.violations):
        rule, its = (x["rule"], x["items"]) if skill_side else (x.rule, x.items)
        if rule in names:
            out[names[rule]].add(tuple(sorted(its)))
    return out


def b_rules_agree() -> tuple[bool, str, dict[str, Any]]:
    rng = random.Random(7)
    stats: dict[str, list[int]] = {k: [0, 0] for k in ("bounds", "overlap", "door", "locked")}
    door_app_only = door_skill_only = 0
    examples: list[str] = []
    for name in ROOMS:
        sk, items, _ = room(name)
        xs, zs = [p[0] for p in sk.floorPolygon], [p[1] for p in sk.floorPolygon]
        layouts = [items]
        for _ in range(RANDOM_LAYOUTS):
            trial = []
            for it in items:
                if it.locked and rng.random() > 0.05:
                    trial.append(it)
                    continue
                trial.append(it.model_copy(update={"x": round(rng.uniform(min(xs), max(xs)) / 0.05) * 0.05, "z": round(rng.uniform(min(zs), max(zs)) / 0.05) * 0.05,
                                                   "rotation": rng.choice((0, 90, 180, 270))}))
            layouts.append(trial)
        for trial in layouts:
            app = _rules(validate_layout(sk, PRESETS, trial, [], items), skill_side=False)
            sk_res = _rules(review.skill_validate(sk, PRESETS, trial, items), skill_side=True)
            for rule, counts in stats.items():
                counts[1] += 1
                if app[rule] == sk_res[rule]:
                    counts[0] += 1
                elif len(examples) < 4 and rule != "door":
                    examples.append(f"{name} {rule}: app {sorted(app[rule])} vs skill {sorted(sk_res[rule])}")
            door_app_only += len(app["door"] - sk_res["door"])
            door_skill_only += len(sk_res["door"] - app["door"])
    hard_ok = all(stats[r][0] == stats[r][1] for r in ("bounds", "overlap", "locked"))
    # The app's door rule adds the inward swing arc to the skill's 0.9 m rectangle, so it may only ever be stricter.
    ok = hard_ok and door_skill_only == 0
    rates = ", ".join(f"{r} {a}/{n}" for r, (a, n) in stats.items())
    detail = f"{rates} layouts agree; door: app stricter on {door_app_only} items (swing arc), skill stricter on {door_skill_only}"
    return ok, detail + ("; " + "; ".join(examples) if examples else ""), {"stats": stats, "doorAppOnly": door_app_only, "doorSkillOnly": door_skill_only}


def _glb_points(path: Path) -> list[tuple[float, float, float]]:
    """Every vertex position in world space (stdlib only: GLB JSON + BIN chunk, float32 VEC3 accessors, node transforms)."""
    raw = path.read_bytes()
    jlen = struct.unpack_from("<I", raw, 12)[0]
    gltf = json.loads(raw[20:20 + jlen])
    blen = struct.unpack_from("<I", raw, 20 + jlen)[0]
    binary = raw[28 + jlen:28 + jlen + blen]
    insp = skill.script("inspect_glb")
    pts: list[tuple[float, float, float]] = []
    identity = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    scene_nodes = (gltf.get("scenes") or [{"nodes": list(range(len(gltf["nodes"])))}])[gltf.get("scene", 0)]["nodes"]
    stack = [(n, identity) for n in scene_nodes]
    while stack:
        idx, parent = stack.pop()
        node = gltf["nodes"][idx]
        world = insp.mat_mul(parent, insp.node_matrix(node))
        for prim in gltf["meshes"][node["mesh"]]["primitives"] if "mesh" in node else []:
            acc = gltf["accessors"][prim["attributes"]["POSITION"]]
            view = gltf["bufferViews"][acc["bufferView"]]
            stride = view.get("byteStride", 12)
            base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            for k in range(acc["count"]):
                x, y, z = struct.unpack_from("<fff", binary, base + k * stride)
                pts.append(tuple(sum(world[r][c] * v for c, v in enumerate((x, y, z, 1.0))) for r in range(3)))  # type: ignore[misc]
        stack += [(c, world) for c in node.get("children", [])]
    return pts


def b_glb_models() -> tuple[bool, str, dict[str, Any]]:
    manifest = {i["id"]: i for i in json.loads((ASSETS / "manifest.json").read_text())["items"]}
    insp = skill.script("inspect_glb")
    problems, notes, backs, measured = [], [], {}, 0
    for fid, f in PRESETS.items():
        if not f.glbUrl or not f.glbUrl.startswith("/assets/furniture/"):
            continue
        path = ASSETS / f.glbUrl.rsplit("/", 1)[1]
        m = insp.measure(insp.load_gltf_json(path))
        measured += 1
        if m is None:
            problems.append(f"{fid}: no measurable meshes")
            continue
        if m.get("unit_warning"):
            problems.append(f"{fid}: {m['unit_warning']}")
        # The editor stretches each axis to the catalog size; a model turned 90 degrees would need its aspect inverted to fit.
        native, want = m["w"] / m["d"], f.dims.w / f.dims.d
        if abs(math.log(native / want)) > abs(math.log((1 / native) / want)) + 0.4:
            # the editor stretches it to the catalog footprint either way; only a piece with a front would then face the wrong way
            (notes if f.kind == "floor" else problems).append(f"{fid}: model looks turned 90 degrees (native w/d {native:.2f}, catalog {want:.2f})")
        if fid in TALL_BACK:
            pts = _glb_points(path)
            y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
            z0, z1 = min(p[2] for p in pts), max(p[2] for p in pts)
            top = [p[2] for p in pts if p[1] >= y0 + 0.75 * (y1 - y0)]
            where = (sum(top) / len(top) - (z0 + z1) / 2) / ((z1 - z0) or 1)
            backs[fid] = round(where, 2)
            if where > -0.1:
                problems.append(f"{fid}: tallest part is not at the back (-z) of the model (offset {where:+.2f}), so the rendered front may not face the way the data says")
        if fid in manifest and manifest[fid].get("frontAxis", "+z") != "+z":
            problems.append(f"{fid}: frontAxis {manifest[fid]['frontAxis']} but the editor never rotates for it")
    summary = f"{measured} models measured with inspect_glb.py; tall backs at -z for {', '.join(f'{k} {v:+.2f}' for k, v in backs.items())}"
    note = f". Asset notes (flat pieces, footprint unaffected, render looks stretched): {'; '.join(notes)}" if notes else ""
    return not problems, ("; ".join(problems) or summary) + note, {"backs": backs, "measured": measured, "notes": notes}


def b_facts_cover_scene() -> tuple[bool, str, dict[str, Any]]:
    problems = []
    for name in ROOMS:
        sk, items, purpose = room(name)
        lines = scene.facts(sk, items, PRESETS, purpose)
        text = "\n".join(lines)
        names = scene.wall_names(sk)
        for d in sk.doors:
            if names[d.wall] not in lines[0]:
                problems.append(f"{name}: say-back misses the door wall")
        for w in sk.windows:
            if names[w.wall] not in lines[0]:
                problems.append(f"{name}: say-back misses a window wall")
        for it in items:
            line = next((line for line in lines if line.startswith(f"{it.id} ")), None)
            if line is None:
                problems.append(f"{name}: no fact line for {it.id}")
            elif it.locked and "LOCKED" not in line:
                problems.append(f"{name}: {it.id} lock not stated")
        if len(re.findall(r"^wall\d+ is the ", text, re.MULTILINE)) != len(sk.walls):
            problems.append(f"{name}: wall lines")
    return not problems, "; ".join(problems) or f"say-back names every door and window wall; every item has a fact line with its lock, walls, facing and neighbours ({len(ROOMS)} rooms)", {}


# ---------- C. designer behavior (mock Gemini, real pipeline) ----------

REQUESTS = ("add a desk", "make space for yoga, keep my dresser", "I want a reading corner", "Will a desk fit beside my window?",
            "can you add a rug and a floor lamp", "remove the plant", "can you remove all the furniture", "make it a cozy study",
            "what do you think of my room?")


def _text_problems(text: str) -> list[str]:
    low = text.lower()
    out = [f"says '{w}'" for w in BANNED if w in low]
    if re.search(r"\b\d+(\.\d+)? ?(m|meters?|cm)\b", low) and not re.search(r"\b(ft|feet|in|inches)\b|\d'|\d\"", low):
        out.append("metric-only sizes (skill: feet and inches for US users)")
    return out


def c_designer_behavior() -> tuple[bool, str, dict[str, Any]]:
    """Runs on the offline planner (it's about the pipeline, not the model); the environment is restored afterwards."""
    saved = {k: os.environ.get(k) for k in ("MOCK_MODE", "ARP_DATA_DIR")}
    try:
        return _designer_behavior()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _designer_behavior() -> tuple[bool, str, dict[str, Any]]:
    from fastapi.testclient import TestClient

    from app.main import create_app

    os.environ["MOCK_MODE"] = "true"
    problems, answered, options = [], 0, 0
    tmp = REPO_ROOT / ".data" / "designer-check"
    shutil.rmtree(tmp, ignore_errors=True)
    os.environ["ARP_DATA_DIR"] = str(tmp)
    with TestClient(create_app(Settings.from_env())) as c:
        # a confirmed Marketplace desk, the way a Photon link import arrives (exercises the multi-option plan)
        desk = c.post("/furniture/manual", json={"name": "Marketplace desk", "category": "desk", "dims": {"w": 1.2, "d": 0.6, "h": 0.75}}).json()
        catalog = {**PRESETS, desk["id"]: FurnitureItem.model_validate(desk)}
        for sample in SAMPLES:
            made = c.post("/rooms", json={"sample": sample}).json()
            rid, cur = made["room"]["id"], made["currentLayout"]
            sk = RoomSkeleton.model_validate(made["room"]["skeleton"])
            locked = {i["id"]: i for i in cur["items"] if i["locked"]}
            for text, fid in [*((t, None) for t in REQUESTS), ("Will this fit beside my window without moving my bed?", desk["id"])]:
                out = c.post("/agent/request", json={"text": text, "roomId": rid, "baseLayoutId": cur["id"], "channel": "app",
                                                     **({"furnitureId": fid} if fid else {})}).json()
                tag = f"{sample} / {text!r}"
                problems += [f"{tag}: reply {p}" for p in _text_problems(out["reply"])]
                if out["status"] != "ok":
                    if out["status"] == "rejected" and not re.search(r"\d", out["reply"]) and "couldn't" not in out["reply"]:
                        problems.append(f"{tag}: rejection doesn't say how far off it is")
                    continue
                if (out["plan"] or {}).get("intent") == "answer":
                    if out["layout"] is not None or not out["reply"].strip():
                        problems.append(f"{tag}: an answer changed the room or said nothing")
                    continue
                answered += 1
                opts = out["options"]
                options += len(opts)
                if not 1 <= len(opts) <= 3 or not opts[0]["recommended"] or out["recommended"] != opts[0]["variantName"]:
                    problems.append(f"{tag}: options {len(opts)} / recommended not first")
                if not out.get("roomSummary"):
                    problems.append(f"{tag}: no room say-back")
                seen = set()
                for o in opts:
                    lay = c.get(f"/layouts/{o['layoutId']}").json()
                    items = [LayoutItem.model_validate(i) for i in lay["layout"]["items"]]
                    key = tuple(sorted((i.id, i.x, i.z, i.rotation) for i in items))
                    if key in seen:
                        problems.append(f"{tag}: near-duplicate option {o['variantName']}")
                    seen.add(key)
                    if lay["validation"]["blocked"] or any(v["severity"] == "error" for v in lay["validation"]["violations"]):
                        problems.append(f"{tag}: {o['variantName']} fails the app check")
                    sv = review.skill_validate(sk, catalog, items, [LayoutItem.model_validate(i) for i in cur["items"]])
                    if not sv["ok"] or not o["skillValidation"]["ok"]:
                        problems.append(f"{tag}: {o['variantName']} fails validate_layout.py: {[v['message'] for v in sv['violations']]}")
                    for lid, li in locked.items():
                        now = next((i for i in lay["layout"]["items"] if i["id"] == lid), None)
                        if now is None or (now["x"], now["z"], now["rotation"]) != (li["x"], li["z"], li["rotation"]) or lid in o["moved"]:
                            problems.append(f"{tag}: locked {lid} moved")
                    if not (o.get("explanation") or "").strip() or not (o.get("tradeoff") or "").strip():
                        problems.append(f"{tag}: {o['variantName']} lacks explanation or tradeoff")
                    if len(o["variantName"].split()) > 4 or re.match(r"(?i)option\s*\d", o["variantName"]):
                        problems.append(f"{tag}: variant name '{o['variantName']}'")
                    problems += [f"{tag}: {o['variantName']} {p}" for p in _text_problems(f"{o.get('explanation')} {o.get('tradeoff')}")]
        # nothing fits: the reply must say how far off it is, and only suggest a wall the solver tested
        huge = c.post("/furniture/manual", json={"name": "Banquet table", "category": "table", "dims": {"w": 3.3, "d": 1.0, "h": 0.75}})
        made = c.post("/rooms", json={"sample": "nyc-bedroom"}).json()
        out = c.post("/agent/request", json={"text": "Will this fit beside my window?", "roomId": made["room"]["id"],
                                             "baseLayoutId": made["currentLayout"]["id"], "furnitureId": huge.json()["id"], "channel": "app"}).json()
        rejected = out["reply"]
        if out["status"] == "ok" or not re.search(r"\d", rejected) or "want me to try" in rejected.lower():
            problems.append(f"too-big table: status {out['status']}, reply {rejected!r}")
        problems += [f"too-big table reply {p}" for p in _text_problems(rejected)]
    shutil.rmtree(tmp, ignore_errors=True)
    return not problems, "; ".join(problems[:6]) or (f"{answered} answered requests, {options} options: all pass both validators, locks kept, "
                                                     f"explanation + tradeoff, plain words; too-big table: {rejected!r}"), {"answered": answered, "options": options}


# ---------- D. live Gemini ----------

QUIZ_SCHEMA = {
    "type": "object",
    "required": ["room_length_m", "room_width_m", "door_walls", "window_walls", "items"],
    "properties": {
        "room_length_m": {"type": "number", "description": "extent along x"},
        "room_width_m": {"type": "number", "description": "extent along z"},
        "door_walls": {"type": "array", "items": {"type": "string"}, "description": "wall ids (wall0...) that have a door"},
        "window_walls": {"type": "array", "items": {"type": "string"}, "description": "wall ids that have a window"},
        "items": {"type": "array", "items": {"type": "object", "required": ["id", "against_walls", "front_faces", "locked", "blocks_window"], "properties": {
            "id": {"type": "string"}, "against_walls": {"type": "array", "items": {"type": "string"}},
            "front_faces": {"type": "string", "enum": ["+x", "-x", "+z", "-z", "none"]}, "locked": {"type": "boolean"},
            "blocks_window": {"type": "boolean", "description": "taller than a window's sill and standing in front of it"}}}},
    },
}
QUIZ = ("Answer from the room data only. Give the room's length along x and width along z in meters, which walls (by id) have a door and "
        "which have a window, and for EVERY piece of furniture: which walls (ids) it stands flush against, which axis direction its front faces "
        "('none' for rugs and mats), whether it's locked, and whether it blocks a window.")


def truth(sk: RoomSkeleton, items: list[LayoutItem]) -> dict[str, Any]:
    from app.solver.grid import rects_overlap
    from app.solver.skeleton import window_band

    xs, zs = [p[0] for p in sk.floorPolygon], [p[1] for p in sk.floorPolygon]
    out = {"room_length_m": max(xs) - min(xs), "room_width_m": max(zs) - min(zs), "door_walls": sorted({f"wall{d.wall}" for d in sk.doors}),
           "window_walls": sorted({f"wall{w.wall}" for w in sk.windows}), "items": {}}
    for it in items:
        f = PRESETS[it.furnitureId]
        r = item_rect(it.x, it.z, it.rotation, f.dims)
        out["items"][it.id] = {
            "against_walls": sorted(f"wall{i}" for i in scene._touching(sk, r)),
            "front_faces": "none" if f.kind == "floor" else {(0, 1): "+z", (1, 0): "+x", (0, -1): "-z", (-1, 0): "-x"}[front_dir(it.rotation)],
            "locked": it.locked,
            "blocks_window": f.kind != "floor" and any(f.dims.h > w.sillHeight and rects_overlap(window_band(sk, w, 0.6), r) for w in sk.windows),
        }
    return out


def score(answer: dict[str, Any], want: dict[str, Any]) -> tuple[int, int, list[str]]:
    got, total, misses = 0, 0, []

    def mark(ok: bool, what: str) -> None:
        nonlocal got, total
        total += 1
        got += ok
        if not ok:
            misses.append(what)

    mark(abs(answer.get("room_length_m", 0) - want["room_length_m"]) < 0.05, "length")
    mark(abs(answer.get("room_width_m", 0) - want["room_width_m"]) < 0.05, "width")
    mark(sorted(answer.get("door_walls", [])) == want["door_walls"], "door walls")
    mark(sorted(answer.get("window_walls", [])) == want["window_walls"], "window walls")
    by_id = {i.get("id"): i for i in answer.get("items", [])}
    for iid, w in want["items"].items():
        a = by_id.get(iid, {})
        mark(sorted(a.get("against_walls", [])) == w["against_walls"], f"{iid} walls")
        mark(a.get("front_faces") == w["front_faces"], f"{iid} front")
        mark(a.get("locked") == w["locked"], f"{iid} locked")
        mark(a.get("blocks_window") == w["blocks_window"], f"{iid} window")
    return got, total, misses


def d_live(min_score: float = 0.9) -> list[Check]:
    settings = Settings.from_env()
    if not settings.gemini_live:
        return [Check("D. Live Gemini", "comprehension quiz on the real prompt", "SKIP", "no GEMINI_API_KEY (or MOCK_MODE=true)"),
                Check("D. Live Gemini", "live plan follows the skill", "SKIP", "no GEMINI_API_KEY (or MOCK_MODE=true)")]
    from app.agent.pipeline import parse_plan
    from app.integrations.gemini import PLAN_SCHEMA, GeminiAdapter

    gem = GeminiAdapter(settings)
    checks = []
    results = {}
    for mode in ("full prompt", "scene JSON only"):
        got = total = 0
        misses: list[str] = []
        for name in ROOMS:
            sk, items, purpose = room(name)
            system = prompts.build_system_prompt(sk, layout(items), PRESETS, [], None, purpose)
            if mode == "scene JSON only":
                system = prompts.SCENE_OPEN + "\n" + json.dumps(prompts.parse_scene(system)) + "\n" + prompts.SCENE_CLOSE
            answer = asyncio.run(gem._generate(system, [QUIZ], QUIZ_SCHEMA))
            g, t, m = score(answer, truth(sk, items))
            got, total, misses = got + g, total + t, misses + [f"{name}: {x}" for x in m]
        results[mode] = (got, total, misses)
    g, t, m = results["full prompt"]
    j = results["scene JSON only"]
    checks.append(Check("D. Live Gemini", "comprehension quiz on the real prompt", "PASS" if g / t >= min_score else "FAIL",
                        f"{g}/{t} with the production prompt; {j[0]}/{j[1]} from the bare scene JSON" + (f"; misses: {', '.join(m[:6])}" if m else ""),
                        {"full": [g, t], "jsonOnly": [j[0], j[1]], "misses": m}))
    sk, items, purpose = room("nyc-bedroom")
    system = prompts.build_system_prompt(sk, layout(items), PRESETS, [], None, purpose, "Will a 4 foot desk fit beside my window without moving my bed?")
    raw = asyncio.run(gem.plan(system, "Will a 4 foot desk fit beside my window without moving my bed?"))
    plan = parse_plan(raw)
    problems = []
    if isinstance(plan, str):
        problems.append(plan)
    else:
        if plan.intent != "fit_item" or not 1 <= len(plan.options or [plan]) <= 3:
            problems.append(f"intent {plan.intent}, {len(plan.options)} options")
        if not plan.roomSummary:
            problems.append("no roomSummary")
        if not any(c.type == "lock" and "bed" in (c.item or "") for c in plan.constraints):
            problems.append("didn't lock the bed")
        text = " ".join([plan.reply, plan.roomSummary or "", *(f"{o.explanation} {o.tradeoff}" for o in plan.options)])
        problems += _text_problems(text)
        if any(o.tradeoff in (None, "") for o in plan.options):
            problems.append("option without tradeoff")
    checks.append(Check("D. Live Gemini", "live plan follows the skill", "FAIL" if problems else "PASS", "; ".join(problems) or f"reply: {plan.reply}",  # type: ignore[union-attr]
                        {"plan": raw}))
    _ = PLAN_SCHEMA
    return checks


# ---------- runner ----------

CHECKS: list[tuple[str, str, Callable[[], tuple[bool | None, str, dict[str, Any]]]]] = [
    ("A. Skill fidelity", "copy matches the lock byte-for-byte", a_copy_matches_lock),
    ("A. Skill fidelity", "copy matches the installed skill", a_copy_matches_installed),
    ("A. Skill fidelity", "Gemini prompt carries SKILL.md + references verbatim", a_prompt_carries_skill),
    ("A. Skill fidelity", "skill's own scripts run as documented", a_skill_scripts_run_as_documented),
    ("B. 3D understanding", "scene in the prompt round-trips to the editor's 3D view", b_scene_round_trip),
    ("B. 3D understanding", "scene facts cover every opening and item", b_facts_cover_scene),
    ("B. 3D understanding", "skill validator agrees with the app on hard rules", b_rules_agree),
    ("B. 3D understanding", "GLB models match what the data says (inspect_glb.py)", b_glb_models),
    ("C. Designer behavior", "options pass both validators, keep locks, speak plainly", c_designer_behavior),
]


def run_all(live: bool = True) -> list[Check]:
    results = [_check(g, n, fn) for g, n, fn in CHECKS]
    return results + (d_live() if live else [])


def sync(src: Path) -> None:
    """Replace the copy with the installed skill (byte-for-byte) and rewrite the lock."""
    if not (src / "SKILL.md").exists():
        raise SystemExit(f"{src} has no SKILL.md")
    shutil.rmtree(skill.SKILL_DIR)
    shutil.copytree(src, skill.SKILL_DIR, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
    data = skill.lock()
    data["files"] = skill.file_hashes()
    skill.LOCK_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"copied {len(data['files'])} files from {src}")  # type: ignore[arg-type]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, help="also write the results here")
    ap.add_argument("--sync", type=Path, help="refresh the verbatim copy from this skill folder, then check")
    ap.add_argument("--no-live", action="store_true", help="skip the live Gemini checks even when a key is set")
    args = ap.parse_args()
    if args.sync:
        sync(args.sync.expanduser())
    results = run_all(live=not args.no_live)
    width = max(len(r.name) for r in results)
    group = None
    for r in results:
        if r.group != group:
            group = r.group
            print(f"\n{group}")
        print(f"  {r.status:4}  {r.name:<{width}}  {r.detail}")
    fails = sum(r.status == "FAIL" for r in results)
    skips = sum(r.status == "SKIP" for r in results)
    print(f"\n{len(results) - fails - skips} passed, {fails} failed, {skips} skipped")
    if args.json:
        args.json.write_text(json.dumps([r.__dict__ for r in results], indent=2, default=str))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
