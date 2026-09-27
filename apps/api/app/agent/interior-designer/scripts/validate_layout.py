#!/usr/bin/env python3
"""Check furniture layouts against the Adaptive Room Planner fit rules (PRD section 8).

Usage:
    python validate_layout.py layout.json [--min-path 0.6] [--grid 0.1]

Input JSON (meters, floor plane x/z, rotation in degrees like three.js rotation.y):
{
  "room": {
    "floor_polygon": [[x, z], ...],
    "doors":   [{"id": "d1", "a": [x, z], "b": [x, z]}],
    "windows": [{"id": "w1", "a": [x, z], "b": [x, z]}]
  },
  "furniture": {"bed": {"name": "Full bed", "category": "bed", "w": 1.4, "d": 2.0, "h": 0.5}},
  "items": [{"furnitureId": "bed", "x": 1.0, "z": 1.2, "rotation": 0, "locked": true}],
  "clear_zones": [{"label": "yoga", "w": 1.8, "d": 1.2}],
  "keep_clear": [{"feature": "w1", "depth": 0.5}]
}
Instead of "items" you can pass "options": [{"name": "...", "items": [...]}, ...]
to check up to several arrangements in one run. "base_items" (the Current Room)
lets the script report which locked items moved.

Item convention: (x, z) is the center of the footprint. At rotation 0 the width
runs along +x, the depth along +z, and the front faces +z.
"""
import argparse
import json
import math
import sys
from collections import deque

ACCESS_DEPTH = 0.75          # free strip beside beds/desks and in front of storage
DOOR_DEPTH = 0.9             # empty space in front of a door
EPS = 0.005                  # 5 mm tolerance so touching items don't count as overlapping
BED_DESK = {"bed", "desk"}
STORAGE = {"dresser", "wardrobe", "bookshelf", "bookcase", "storage", "cabinet",
           "shelf", "closet", "chest"}
UNDERFOOT = {"rug", "mat"}   # sits under other furniture, never blocks


# ---------- geometry helpers ----------

def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            xi = x1 + (z - z1) * (x2 - x1) / (z2 - z1)
            if x < xi:
                inside = not inside
    return inside


def poly_centroid(poly):
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))


class Box:
    """Oriented rectangle on the floor."""

    def __init__(self, cx, cz, ux, uz, hw, hd):
        self.cx, self.cz = cx, cz
        self.ux, self.uz = ux, uz      # unit axes (tuples)
        self.hw, self.hd = hw, hd      # half extents

    @classmethod
    def from_item(cls, x, z, w, d, rot_deg):
        r = math.radians(rot_deg)
        ux = (math.cos(r), -math.sin(r))
        uz = (math.sin(r), math.cos(r))
        return cls(x, z, ux, uz, w / 2, d / 2)

    def corners(self, shrink=0.0):
        hw, hd = self.hw - shrink, self.hd - shrink
        out = []
        for sw, sd in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            out.append((self.cx + sw * hw * self.ux[0] + sd * hd * self.uz[0],
                        self.cz + sw * hw * self.ux[1] + sd * hd * self.uz[1]))
        return out

    def contains(self, px, pz, margin=0.0):
        dx, dz = px - self.cx, pz - self.cz
        a = dx * self.ux[0] + dz * self.ux[1]
        b = dx * self.uz[0] + dz * self.uz[1]
        return abs(a) <= self.hw + margin - 1e-9 and abs(b) <= self.hd + margin - 1e-9

    def distance_to(self, px, pz):
        dx, dz = px - self.cx, pz - self.cz
        a = abs(dx * self.ux[0] + dz * self.ux[1]) - self.hw
        b = abs(dx * self.uz[0] + dz * self.uz[1]) - self.hd
        return math.hypot(max(a, 0), max(b, 0))

    def overlaps(self, other, eps=EPS):
        for axis in (self.ux, self.uz, other.ux, other.uz):
            p1 = [c[0] * axis[0] + c[1] * axis[1] for c in self.corners()]
            p2 = [c[0] * axis[0] + c[1] * axis[1] for c in other.corners()]
            if min(p1) >= max(p2) - eps or min(p2) >= max(p1) - eps:
                return False
        return True

    def edge_strip(self, side, depth):
        """Rectangle of `depth` just outside one side: '+w', '-w', '+d', '-d'."""
        if side in ("+d", "-d"):
            s = 1 if side == "+d" else -1
            off = self.hd + depth / 2
            return Box(self.cx + s * off * self.uz[0], self.cz + s * off * self.uz[1],
                       self.ux, self.uz, self.hw, depth / 2)
        s = 1 if side == "+w" else -1
        off = self.hw + depth / 2
        return Box(self.cx + s * off * self.ux[0], self.cz + s * off * self.ux[1],
                   self.ux, self.uz, depth / 2, self.hd)


def zone_in_front(feature, depth, poly, min_width=None):
    """Rectangle on the room side of a door or window segment."""
    ax, az = feature["a"]
    bx, bz = feature["b"]
    length = math.hypot(bx - ax, bz - az)
    if length == 0:
        return None
    t = ((bx - ax) / length, (bz - az) / length)
    n = (-t[1], t[0])
    mx, mz = (ax + bx) / 2, (az + bz) / 2
    # flip the normal so it points into the room
    if not point_in_poly(mx + n[0] * 0.05, mz + n[1] * 0.05, poly):
        n = (-n[0], -n[1])
    depth = max(depth, min_width or 0)
    return Box(mx + n[0] * depth / 2, mz + n[1] * depth / 2, t, n, length / 2, depth / 2)


# ---------- validation ----------

def norm_furniture(f):
    def g(*keys):
        for k in keys:
            if k in f and f[k] is not None:
                return float(f[k])
        return None
    dims = f.get("dims", {})
    w = g("w", "w_m", "width") or float(dims.get("w", 0))
    d = g("d", "d_m", "depth") or float(dims.get("d", 0))
    h = g("h", "h_m", "height") or float(dims.get("h", 0) or 0)
    return {"name": f.get("name", "item"), "category": (f.get("category") or f.get("type") or "").lower(),
            "w": w, "d": d, "h": h}


def validate(room, furniture, items, clear_zones=(), keep_clear=(), base_items=None,
             grid=0.1, min_path=0.6):
    poly = room["floor_polygon"]
    violations, warnings = [], []

    placed = []
    for it in items:
        fid = it.get("furnitureId") or it.get("item")
        if fid not in furniture:
            violations.append({"rule": "unknown_item", "items": [fid],
                               "message": f"No furniture called '{fid}' in the catalog."})
            continue
        f = norm_furniture(furniture[fid])
        box = Box.from_item(float(it["x"]), float(it["z"]), f["w"], f["d"], float(it.get("rotation", 0)))
        placed.append({"id": fid, "f": f, "box": box, "locked": bool(it.get("locked")),
                       "underfoot": f["category"] in UNDERFOOT})

    # locked items must not move
    if base_items:
        base = {b.get("furnitureId") or b.get("item"): b for b in base_items}
        for p in placed:
            b = base.get(p["id"])
            if b and b.get("locked"):
                it = next(i for i in items if (i.get("furnitureId") or i.get("item")) == p["id"])
                moved = (abs(float(it["x"]) - float(b["x"])) > 1e-3 or
                         abs(float(it["z"]) - float(b["z"])) > 1e-3 or
                         (float(it.get("rotation", 0)) - float(b.get("rotation", 0))) % 360 > 1e-3)
                if moved:
                    violations.append({"rule": "locked_moved", "items": [p["id"]],
                                       "message": f"The {p['f']['name']} is locked but was moved."})
        for bid, b in base.items():
            if b.get("locked") and bid not in [p["id"] for p in placed]:
                violations.append({"rule": "locked_moved", "items": [bid],
                                   "message": f"The locked {bid} was removed."})

    # room bounds
    for p in placed:
        if not all(point_in_poly(x, z, poly) for x, z in p["box"].corners(shrink=EPS)):
            violations.append({"rule": "room_bounds", "items": [p["id"]],
                               "message": f"The {p['f']['name']} sticks out past a wall."})

    # overlap
    solid = [p for p in placed if not p["underfoot"]]
    for i in range(len(solid)):
        for j in range(i + 1, len(solid)):
            if solid[i]["box"].overlaps(solid[j]["box"]):
                violations.append({"rule": "overlap", "items": [solid[i]["id"], solid[j]["id"]],
                                   "message": f"The {solid[i]['f']['name']} and the {solid[j]['f']['name']} are on top of each other."})

    # door clearance
    door_zones = []
    for door in room.get("doors", []):
        z = zone_in_front(door, DOOR_DEPTH, poly,
                          min_width=math.dist(door["a"], door["b"]))
        if z is None:
            continue
        door_zones.append((door, z))
        for p in solid:
            if p["box"].overlaps(z):
                violations.append({"rule": "door_clearance", "items": [p["id"]],
                                   "message": f"The {p['f']['name']} is in the way of the door."})

    # keep-clear features (window, outlet, etc.)
    features = {f.get("id"): f for f in room.get("doors", []) + room.get("windows", []) + room.get("outlets", [])}
    for kc in keep_clear:
        feat = features.get(kc.get("feature"))
        if not feat:
            warnings.append({"rule": "keep_clear", "items": [],
                             "message": f"Couldn't find feature '{kc.get('feature')}' to keep clear."})
            continue
        z = zone_in_front(feat, float(kc.get("depth", 0.5)), poly)
        for p in solid:
            if z and p["box"].overlaps(z):
                violations.append({"rule": "keep_clear", "items": [p["id"]],
                                   "message": f"The {p['f']['name']} blocks {kc.get('feature')}, which you asked to keep clear."})

    def strip_free(strip, owner):
        if not all(point_in_poly(x, z, poly) for x, z in strip.corners(shrink=EPS)):
            return False
        return not any(o is not owner and strip.overlaps(o["box"]) for o in solid)

    # access edges
    for p in solid:
        cat, box = p["f"]["category"], p["box"]
        if cat in BED_DESK:
            sides = ("+d", "-d") if box.hw >= box.hd else ("+w", "-w")
            if not any(strip_free(box.edge_strip(s, ACCESS_DEPTH), p) for s in sides):
                warnings.append({"rule": "access_edge", "items": [p["id"]],
                                 "message": f"There's less than {ACCESS_DEPTH} m of room along both long sides of the {p['f']['name']}."})
        elif cat in STORAGE:
            if not strip_free(box.edge_strip("+d", ACCESS_DEPTH), p):
                warnings.append({"rule": "access_edge", "items": [p["id"]],
                                 "message": f"There's less than {ACCESS_DEPTH} m in front of the {p['f']['name']} to open it."})

    # ---- grid work: open floor, clear zones, walkable path ----
    xs, zs = [p[0] for p in poly], [p[1] for p in poly]
    minx, minz = min(xs), min(zs)
    nx = int(math.ceil((max(xs) - minx) / grid))
    nz = int(math.ceil((max(zs) - minz) / grid))
    cx = [minx + (i + 0.5) * grid for i in range(nx)]
    cz = [minz + (j + 0.5) * grid for j in range(nz)]
    floor = [[point_in_poly(cx[i], cz[j], poly) for j in range(nz)] for i in range(nx)]
    occ = [[floor[i][j] and any(p["box"].contains(cx[i], cz[j]) for p in solid)
            for j in range(nz)] for i in range(nx)]
    in_door = [[any(z.contains(cx[i], cz[j]) for _, z in door_zones) for j in range(nz)] for i in range(nx)]

    floor_cells = sum(floor[i][j] for i in range(nx) for j in range(nz))
    free_cells = sum(floor[i][j] and not occ[i][j] for i in range(nx) for j in range(nz))
    metrics = {"open_floor_pct": round(100 * free_cells / floor_cells, 1) if floor_cells else 0,
               "floor_area_m2": round(floor_cells * grid * grid, 2)}

    free = [[floor[i][j] and not occ[i][j] and not in_door[i][j] for j in range(nz)] for i in range(nx)]

    # largest free rectangle (axis aligned), histogram method
    best = (0, 0, 0, 0, 0)  # area, i0, j0, wi, dj
    heights = [0] * nz
    for i in range(nx):
        for j in range(nz):
            heights[j] = heights[j] + 1 if free[i][j] else 0
        stack = []
        for j in range(nz + 1):
            h = heights[j] if j < nz else 0
            start = j
            while stack and stack[-1][1] >= h:
                s, sh = stack.pop()
                area = sh * (j - s)
                if area > best[0]:
                    best = (area, i - sh + 1, s, sh, j - s)
                start = s
            stack.append((start, h))
    metrics["largest_open_area_m"] = [round(best[3] * grid, 2), round(best[4] * grid, 2)]

    # requested clear zones
    ps = [[0] * (nz + 1) for _ in range(nx + 1)]
    for i in range(nx):
        for j in range(nz):
            ps[i + 1][j + 1] = ps[i][j + 1] + ps[i + 1][j] - ps[i][j] + (1 if free[i][j] else 0)
    zone_results = []
    for cz_req in clear_zones:
        found = None
        for w, d in ((cz_req["w"], cz_req["d"]), (cz_req["d"], cz_req["w"])):
            kw, kd = int(math.ceil(w / grid - 1e-6)), int(math.ceil(d / grid - 1e-6))
            for i in range(nx - kw + 1):
                for j in range(nz - kd + 1):
                    s = ps[i + kw][j + kd] - ps[i][j + kd] - ps[i + kw][j] + ps[i][j]
                    if s == kw * kd:
                        found = {"x": round(minx + (i + kw / 2) * grid, 2),
                                 "z": round(minz + (j + kd / 2) * grid, 2), "w": w, "d": d}
                        break
                if found:
                    break
            if found:
                break
        label = cz_req.get("label", "open area")
        zone_results.append({"label": label, "fits": bool(found), "at": found})
        if not found:
            violations.append({"rule": "clear_zone", "items": [],
                               "message": f"No open {cz_req['w']} x {cz_req['d']} m space for {label}. "
                                          f"The biggest open area is {metrics['largest_open_area_m'][0]} x {metrics['largest_open_area_m'][1]} m."})
    metrics["clear_zones"] = zone_results

    # walkable path: flood fill from each door over cells wide enough to walk through
    INF = 10 ** 9
    dist = [[0 if (not floor[i][j] or occ[i][j]) else INF for j in range(nz)] for i in range(nx)]
    q = deque()
    for i in range(nx):
        for j in range(nz):
            if dist[i][j] == 0:
                q.append((i, j))
            elif i in (0, nx - 1) or j in (0, nz - 1):
                dist[i][j] = 1
                q.append((i, j))
    while q:
        i, j = q.popleft()
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                a, b = i + di, j + dj
                if 0 <= a < nx and 0 <= b < nz and dist[a][b] > dist[i][j] + 1:
                    dist[a][b] = dist[i][j] + 1
                    q.append((a, b))
    need = max(1, int(math.ceil(min_path / (2 * grid) - 1e-6)))
    passable = [[floor[i][j] and dist[i][j] >= need for j in range(nz)] for i in range(nx)]
    reached = [[False] * nz for _ in range(nx)]
    q = deque()
    for _, z in door_zones:
        for i in range(nx):
            for j in range(nz):
                if passable[i][j] and z.contains(cx[i], cz[j]) and not reached[i][j]:
                    reached[i][j] = True
                    q.append((i, j))
    if door_zones and not q:
        violations.append({"rule": "walkable_path", "items": [],
                           "message": "You can't walk in from the door; the doorway is too tight."})
    while q:
        i, j = q.popleft()
        for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if 0 <= a < nx and 0 <= b < nz and passable[a][b] and not reached[a][b]:
                reached[a][b] = True
                q.append((a, b))
    if door_zones:
        reach_r = (need + 1.5) * grid
        for p in solid:
            if p["f"]["category"] not in BED_DESK | STORAGE:
                continue
            ok = any(reached[i][j] and p["box"].distance_to(cx[i], cz[j]) <= reach_r
                     for i in range(nx) for j in range(nz))
            if not ok:
                violations.append({"rule": "walkable_path", "items": [p["id"]],
                                   "message": f"Path blocked to the {p['f']['name']}: you can't walk to it from the door."})

    return {"ok": not violations, "violations": violations, "warnings": warnings, "metrics": metrics}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("layout")
    ap.add_argument("--grid", type=float, default=0.1)
    ap.add_argument("--min-path", type=float, default=0.6, help="narrowest walkable gap in meters")
    args = ap.parse_args()
    with open(args.layout) as fh:
        data = json.load(fh)

    common = dict(room=data["room"], furniture=data["furniture"],
                  clear_zones=data.get("clear_zones", []), keep_clear=data.get("keep_clear", []),
                  base_items=data.get("base_items"), grid=args.grid, min_path=args.min_path)
    if "options" in data:
        out = {"options": []}
        for opt in data["options"]:
            res = validate(items=opt["items"],
                           **{**common,
                              "clear_zones": opt.get("clear_zones", common["clear_zones"]),
                              "keep_clear": opt.get("keep_clear", common["keep_clear"])})
            res["name"] = opt.get("name") or opt.get("variantName")
            out["options"].append(res)
    else:
        out = validate(items=data["items"], **common)
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
