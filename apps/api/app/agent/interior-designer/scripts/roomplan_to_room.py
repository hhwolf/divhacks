#!/usr/bin/env python3
"""Convert an Apple RoomPlan CapturedRoom JSON export into the room format used
by validate_layout.py, plus a draft list of furniture RoomPlan detected.

Usage:
    python roomplan_to_room.py scan.json [--no-normalize] > room.json

RoomPlan gives every wall, door, window and object a `dimensions` [x, y, z]
(meters) and a 4x4 `transform` (column-major, y-up). This script:
  - turns each wall into a floor-plane segment and chains them into a floor polygon
  - turns doors and windows into segments {a, b} on their walls
  - turns detected objects into furniture + items (x, z center, rotation in degrees
    matching three.js rotation.y)
  - by default shifts everything so the room's corner nearest the origin is (0, 0)

It is a best-effort converter. Check the printed "notes" and eyeball the result in
the editor, especially for L-shaped rooms or scans with gaps between walls.
"""
import argparse
import json
import math
import sys


def columns(t):
    """Return the 4 columns of a transform given flat[16] or nested[4][4] (columns)."""
    if isinstance(t, dict):
        t = t.get("columns", t)
    if len(t) == 16:
        return [t[0:4], t[4:8], t[8:12], t[12:16]]
    return [list(c) for c in t]


def segment(surface):
    c = columns(surface["transform"])
    ux, uz = c[0][0], c[0][2]
    n = math.hypot(ux, uz) or 1
    ux, uz = ux / n, uz / n
    px, pz = c[3][0], c[3][2]
    half = surface["dimensions"][0] / 2
    return [px - ux * half, pz - uz * half], [px + ux * half, pz + uz * half]


def chain_walls(segs, notes):
    if not segs:
        return []
    remaining = segs[1:]
    poly = [segs[0][0], segs[0][1]]
    while remaining:
        end = poly[-1]
        best_i, best_flip, best_d = None, False, math.inf
        for i, (a, b) in enumerate(remaining):
            da, db = math.dist(end, a), math.dist(end, b)
            if da < best_d:
                best_i, best_flip, best_d = i, False, da
            if db < best_d:
                best_i, best_flip, best_d = i, True, db
        a, b = remaining.pop(best_i)
        if best_flip:
            a, b = b, a
        if best_d > 0.15:
            notes.append(f"gap of {best_d:.2f} m between two walls; the polygon bridges it")
        poly[-1] = [(poly[-1][0] + a[0]) / 2, (poly[-1][1] + a[1]) / 2]
        poly.append(b)
    if math.dist(poly[0], poly[-1]) < 0.15:
        poly[0] = [(poly[0][0] + poly[-1][0]) / 2, (poly[0][1] + poly[-1][1]) / 2]
        poly.pop()
    else:
        notes.append("walls don't close into a loop; the last wall is joined to the first")
    return poly


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scan")
    ap.add_argument("--no-normalize", action="store_true")
    args = ap.parse_args()
    with open(args.scan) as fh:
        scan = json.load(fh)

    notes = []
    walls = [segment(w) for w in scan.get("walls", [])]
    poly = chain_walls(walls, notes)
    doors = [dict(zip(("a", "b"), segment(d)), id=f"door{i+1}") for i, d in enumerate(scan.get("doors", []))]
    windows = [dict(zip(("a", "b"), segment(w)), id=f"window{i+1}") for i, w in enumerate(scan.get("windows", []))]

    furniture, items = {}, []
    for i, obj in enumerate(scan.get("objects", [])):
        cat = obj.get("category", "object")
        if isinstance(cat, dict):  # Swift enum encoding: {"bed": {}}
            cat = next(iter(cat), "object")
        c = columns(obj["transform"])
        rot = math.degrees(math.atan2(-c[0][2], c[0][0])) % 360
        w, h, d = obj["dimensions"]
        fid = f"{cat}{i+1}"
        furniture[fid] = {"name": cat, "category": cat, "w": round(w, 3), "d": round(d, 3), "h": round(h, 3),
                          "source": "roomplan", "estimated": True}
        items.append({"furnitureId": fid, "x": c[3][0], "z": c[3][2], "rotation": round(rot, 1), "locked": False})

    if not args.no_normalize and poly:
        ox, oz = min(p[0] for p in poly), min(p[1] for p in poly)
        shift = lambda p: [round(p[0] - ox, 3), round(p[1] - oz, 3)]
        poly = [shift(p) for p in poly]
        for f in doors + windows:
            f["a"], f["b"] = shift(f["a"]), shift(f["b"])
        for it in items:
            it["x"], it["z"] = shift((it["x"], it["z"]))

    out = {"room": {"floor_polygon": poly, "doors": doors, "windows": windows},
           "furniture": furniture, "items": items, "notes": notes}
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
