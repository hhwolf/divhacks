"""Print a USDZ's full prim tree: type, name, how the converter classifies it, world center and local extent.

    .venv/bin/python apps/api/scripts/inspect_usdz.py fixtures/rooms/real_scan.usdz [--convert]

Run this on a real RoomPlan export before touching the classifier in app/usdz_convert.py. Centers are in the stage's own
units and axes (no meters/up-axis correction), so they can be compared with Reality Composer / usdview. `--convert` also runs the
converter and prints the resulting skeleton, detected objects and conversion report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))



from app.usdz_convert import ConversionError, classify, convert_usdz  # noqa: E402


def _fmt(v: object) -> str:
    return "(" + ", ".join(f"{float(c):7.3f}" for c in v) + ")"  # type: ignore[attr-defined]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("usdz", type=Path)
    ap.add_argument("--convert", action="store_true", help="also run the converter and print its output")
    args = ap.parse_args()

    try:
        from pxr import Usd, UsdGeom
    except ImportError:
        print("USDZ support is optional. Install apps/api/requirements-usdz.txt first.", file=sys.stderr)
        return 2
    stage = Usd.Stage.Open(str(args.usdz))
    if stage is None:
        print(f"could not open {args.usdz}", file=sys.stderr)
        return 1
    mpu_note = "" if stage.HasAuthoredMetadata("metersPerUnit") else "  (not authored: USD fallback)"
    print(f"file:          {args.usdz}")
    print(f"metersPerUnit: {UsdGeom.GetStageMetersPerUnit(stage)}{mpu_note}")
    print(f"upAxis:        {UsdGeom.GetStageUpAxis(stage)}")
    print(f"defaultPrim:   {stage.GetDefaultPrim().GetPath() if stage.GetDefaultPrim() else '-'}")
    print()
    time = Usd.TimeCode.Default()
    bbox_cache = UsdGeom.BBoxCache(time, [UsdGeom.Tokens.default_])
    xf_cache = UsdGeom.XformCache(time)
    print(f"{'prim':<60} {'type':<12} {'class':<16} {'world center':<27} local extent (size)")
    for prim in stage.Traverse():
        depth = len(prim.GetPath().pathElementCount and str(prim.GetPath()).split("/")) - 2
        label = ("  " * depth + prim.GetName())[:60]
        hit = classify(prim.GetName())
        cls = f"{hit[0]}:{hit[1]}" if hit else ""
        box = bbox_cache.ComputeUntransformedBound(prim).ComputeAlignedBox()
        if box.IsEmpty():
            print(f"{label:<60} {prim.GetTypeName() or '-':<12} {cls:<16} {'-':<27} (no geometry)")
            continue
        center = xf_cache.GetLocalToWorldTransform(prim).Transform(box.GetMidpoint())
        print(f"{label:<60} {prim.GetTypeName() or '-':<12} {cls:<16} {_fmt(center):<27} {_fmt(box.GetSize())}")

    if args.convert:
        print()
        try:
            out = convert_usdz(args.usdz)
        except ConversionError as exc:
            print(f"conversion FAILED: {exc}")
            print(json.dumps(exc.report, indent=1))
            return 2
        print("skeleton:", json.dumps(out.skeleton.model_dump(exclude_none=True), indent=1))
        print("objects:", json.dumps([o.__dict__ for o in out.objects], indent=1))
        print("report:", json.dumps(out.report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
