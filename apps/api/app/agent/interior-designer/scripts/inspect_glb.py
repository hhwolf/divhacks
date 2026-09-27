#!/usr/bin/env python3
"""Measure 3D furniture assets (.glb or .gltf) without any extra libraries.

Usage:
    python inspect_glb.py desk.glb bed.glb ...
    python inspect_glb.py desk.glb --expect 1.2 0.6 0.75     # compare with catalog w d h

For each file it prints the real-world footprint the model occupies:
    w = size along x, d = size along z, h = size along y (glTF is y-up, meters)
plus where the model's origin sits (bottom-center is what the editor usually wants).
It reads the min/max bounds that glTF requires on every mesh, so it never
needs to decode vertex data.
"""
import argparse
import json
import math
import struct
import sys


def load_gltf_json(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] == b"glTF":
        _, _, _ = struct.unpack_from("<4sII", data, 0)
        chunk_len, chunk_type = struct.unpack_from("<II", data, 12)
        if chunk_type != 0x4E4F534A:  # 'JSON'
            raise ValueError("first GLB chunk is not JSON")
        return json.loads(data[20:20 + chunk_len].decode("utf-8"))
    return json.loads(data.decode("utf-8"))


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def node_matrix(node):
    if "matrix" in node:
        m = node["matrix"]  # column-major
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    tx, ty, tz = node.get("translation", [0, 0, 0])
    qx, qy, qz, qw = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    r = [
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
    ]
    return [
        [r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
        [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
        [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
        [0, 0, 0, 1],
    ]


def measure(gltf):
    meshes, nodes, accessors = gltf.get("meshes", []), gltf.get("nodes", []), gltf.get("accessors", [])
    scene_idx = gltf.get("scene", 0)
    scenes = gltf.get("scenes") or [{"nodes": list(range(len(nodes)))}]
    roots = scenes[scene_idx].get("nodes", [])
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    mesh_count = 0

    identity = [[1 if i == j else 0 for j in range(4)] for i in range(4)]
    stack = [(n, identity) for n in roots]
    while stack:
        idx, parent = stack.pop()
        node = nodes[idx]
        world = mat_mul(parent, node_matrix(node))
        if "mesh" in node:
            mesh_count += 1
            for prim in meshes[node["mesh"]].get("primitives", []):
                acc_i = prim.get("attributes", {}).get("POSITION")
                if acc_i is None:
                    continue
                acc = accessors[acc_i]
                if "min" not in acc or "max" not in acc:
                    continue
                mn, mx = acc["min"], acc["max"]
                for cx in (mn[0], mx[0]):
                    for cy in (mn[1], mx[1]):
                        for cz in (mn[2], mx[2]):
                            p = [sum(world[r][c] * v for c, v in enumerate((cx, cy, cz, 1))) for r in range(3)]
                            for k in range(3):
                                lo[k] = min(lo[k], p[k])
                                hi[k] = max(hi[k], p[k])
        for child in node.get("children", []):
            stack.append((child, world))

    if mesh_count == 0 or lo[0] == math.inf:
        return None
    size = [hi[k] - lo[k] for k in range(3)]
    center = [(hi[k] + lo[k]) / 2 for k in range(3)]
    if abs(lo[1]) < 0.01 and abs(center[0]) < 0.01 and abs(center[2]) < 0.01:
        origin = "bottom-center (good: place x/z at footprint center, y = 0)"
    elif all(abs(c) < 0.01 for c in center):
        origin = "center of the box (lift by h/2 so it doesn't sink into the floor)"
    else:
        origin = (f"offset: footprint center is at x={center[0]:.3f}, z={center[2]:.3f} "
                  f"and the bottom at y={lo[1]:.3f} from the origin; correct for this when placing")
    unit_note = None
    if max(size) > 10:
        unit_note = "bigger than 10 m: probably modeled in centimeters, scale by 0.01"
    elif max(size) < 0.05:
        unit_note = "smaller than 5 cm: check the export units"
    return {
        "unit_warning": unit_note,
        "w": round(size[0], 3), "d": round(size[2], 3), "h": round(size[1], 3),
        "bbox_min": [round(v, 3) for v in lo], "bbox_max": [round(v, 3) for v in hi],
        "origin": origin, "meshes": mesh_count,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--expect", nargs=3, type=float, metavar=("W", "D", "H"),
                    help="catalog dimensions in meters to compare against (single file)")
    args = ap.parse_args()
    results = {}
    for f in args.files:
        try:
            m = measure(load_gltf_json(f))
        except Exception as e:  # keep going through a batch
            results[f] = {"error": str(e)}
            continue
        if m is None:
            results[f] = {"error": "no measurable meshes"}
            continue
        if args.expect and len(args.files) == 1:
            w, d, h = args.expect
            notes = []
            if abs(m["w"] - d) < 0.02 and abs(m["d"] - w) < 0.02:
                notes.append("model is turned 90 degrees compared with the catalog (w and d swapped); "
                             "rotate it 90 degrees in Blender or add 90 to its rotation")
                w, d = d, w
            for name, got, want in (("w", m["w"], w), ("d", m["d"], d), ("h", m["h"], h)):
                if want and abs(got - want) / want > 0.05:
                    notes.append(f"{name} is {got} m but the catalog says {want} m "
                                 f"(scale factor {want / got:.3f} if the catalog is right)" if got else f"{name} is zero")
            m["check"] = notes or ["matches the catalog within 5%"]
        if m.get("unit_warning") is None:
            m.pop("unit_warning")
        results[f] = m
    json.dump(results, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
