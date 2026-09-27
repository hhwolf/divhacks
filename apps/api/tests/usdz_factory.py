"""Builds RoomPlan-like parametric USDZ files for tests (there is no real scan in the repo yet).

Mimics what RoomPlan's `.parametric` export looks like: `*_grp` group containers, one Xform per element named `Wall0` / `Door0` /
`Bed0` holding a same-named child box (so duplicates must be skipped), zero-thickness planar walls/doors/windows, a door nested under
its wall, a `Floor0` polygon mesh, and furniture + fixture boxes. The whole room can be yawed, offset, authored in centimeters,
authored Z-up, or left without `metersPerUnit`; the converter must produce the same skeleton in every case.

    .venv/bin/python -m tests.usdz_factory /tmp/synthetic.usdz     (from apps/api)
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from pxr import Gf, Usd, UsdGeom, UsdUtils


@dataclass
class Box:
    name: str
    center: tuple[float, float, float]  # meters, Y up, room frame
    size: tuple[float, float, float]  # local x, y, z
    yaw: float = 0.0  # degrees about +Y
    children: list[Box] = field(default_factory=list)


def bedroom(l: float = 3.0, w: float = 3.6, h: float = 2.6) -> tuple[list[Box], list[Box], list[tuple[float, float]]]:
    """A room whose longest walls run along z (so normalization has to rotate it), with one door, one window, three objects."""
    door = Box("Door0", (0.8 - l / 2, 1.0 - h / 2, 0.0), (0.9, 2.0, 0.0))  # nested: coordinates relative to Wall2's frame
    walls = [
        Box("Wall0", (l / 2, h / 2, 0.0), (l, h, 0.0)),
        Box("Wall1", (l, h / 2, w / 2), (w, h, 0.0), yaw=90),
        Box("Wall2", (l / 2, h / 2, w), (l, h, 0.0), children=[door]),
        Box("Wall3", (0.0, h / 2, w / 2), (w, h, 0.0), yaw=90),
        Box("Window0", (l, 0.9 + 0.65, 1.5), (1.2, 1.3, 0.0), yaw=90),
    ]
    objects = [
        Box("Bed0", (0.75, 0.275, 1.2), (1.4, 0.55, 2.0)),
        Box("Storage0", (2.2, 0.4, 3.3), (1.0, 0.8, 0.5), yaw=180),
        Box("Toilet0", (2.6, 0.4, 1.0), (0.4, 0.8, 0.7), yaw=270),
    ]
    floor = [(0.0, 0.0), (l, 0.0), (l, w), (0.0, w)]
    return walls, objects, floor


def _add_box(stage: Usd.Stage, parent: str, box: Box, scale: float) -> None:
    xf = UsdGeom.Xform.Define(stage, f"{parent}/{box.name}")
    xf.AddTranslateOp().Set(Gf.Vec3d(*(c * scale for c in box.center)))
    if box.yaw:
        xf.AddRotateYOp().Set(box.yaw)
    cube = UsdGeom.Cube.Define(stage, f"{parent}/{box.name}/{box.name}")  # RoomPlan repeats the element name on its mesh
    cube.GetSizeAttr().Set(1.0)
    cube.AddScaleOp().Set(Gf.Vec3f(*(s * scale for s in box.size)))
    for child in box.children:
        _add_box(stage, f"{parent}/{box.name}", child, scale)


def build_usdz(
    out: Path,
    *,
    yaw: float = 0.0,
    offset: tuple[float, float] = (0.0, 0.0),
    meters_per_unit: float | None = 1.0,
    up: str = "Y",
    with_floor: bool = True,
    room: tuple[list[Box], list[Box], list[tuple[float, float]]] | None = None,
) -> Path:
    walls, objects, floor = room or bedroom()
    scale = 1.0 / (meters_per_unit or 1.0)
    with tempfile.TemporaryDirectory() as tmp:
        usdc = Path(tmp) / "Room.usdc"
        stage = Usd.Stage.CreateNew(str(usdc))
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z if up == "Z" else UsdGeom.Tokens.y)
        if meters_per_unit is not None:
            UsdGeom.SetStageMetersPerUnit(stage, meters_per_unit)
        root = UsdGeom.Xform.Define(stage, "/Room")
        stage.SetDefaultPrim(root.GetPrim())
        if up == "Z":
            root.AddRotateXOp().Set(90.0)  # author in Y-up, then stand the whole room up in a Z-up world
        room_xf = UsdGeom.Xform.Define(stage, "/Room/Parametric_grp")
        room_xf.AddTranslateOp().Set(Gf.Vec3d(offset[0] * scale, 0.0, offset[1] * scale))
        room_xf.AddRotateYOp().Set(yaw)
        for group in ("Arch_grp", "Arch_grp/Wall_grp", "Arch_grp/Floor_grp", "Object_grp"):
            UsdGeom.Xform.Define(stage, f"/Room/Parametric_grp/{group}")
        for wall in walls:
            _add_box(stage, "/Room/Parametric_grp/Arch_grp/Wall_grp", wall, scale)
        if with_floor:
            mesh = UsdGeom.Mesh.Define(stage, "/Room/Parametric_grp/Arch_grp/Floor_grp/Floor0")
            mesh.GetPointsAttr().Set([Gf.Vec3f(x * scale, 0.0, z * scale) for x, z in floor])
            mesh.GetFaceVertexCountsAttr().Set([len(floor)])
            mesh.GetFaceVertexIndicesAttr().Set(list(range(len(floor))))
        for obj in objects:
            _add_box(stage, "/Room/Parametric_grp/Object_grp", obj, scale)
        stage.GetRootLayer().Save()
        out.parent.mkdir(parents=True, exist_ok=True)
        if not UsdUtils.CreateNewUsdzPackage(str(usdc), str(out)):
            raise RuntimeError("usdz packaging failed")
    return out


if __name__ == "__main__":
    print(build_usdz(Path(sys.argv[1] if len(sys.argv) > 1 else "synthetic_scan.usdz"), yaw=30, offset=(5.0, -2.0)))
