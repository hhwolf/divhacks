"""RoomPlan USDZ -> canonical JSON. Synthetic scans from tests/usdz_factory.py; a real export at fixtures/rooms/real_scan.usdz is used when present."""

from pathlib import Path

import pytest
from app.usdz_convert import ConversionError, classify, convert_usdz

from tests.conftest import FIXTURES
import importlib.util
HAS_USD = importlib.util.find_spec("pxr") is not None
requires_usd = pytest.mark.skipif(not HAS_USD, reason="optional usd-core is not installed (apps/api/requirements-usdz.txt)")
if HAS_USD:
    from tests.usdz_factory import Box, bedroom, build_usdz

VARIANTS = {
    "plain": {},
    "yawed_and_offset": {"yaw": 30, "offset": (5.0, -2.0)},
    "centimeters": {"meters_per_unit": 0.01, "yaw": -65},
    "z_up": {"up": "Z", "yaw": 121, "offset": (-3.0, 7.0)},
    "mpu_not_authored": {"meters_per_unit": None},
    "no_floor_prim": {"with_floor": False, "yaw": 10},
}


@pytest.fixture(scope="module")
def plain(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    if not HAS_USD:
        pytest.skip("optional usd-core is not installed")
    return convert_usdz(build_usdz(tmp_path_factory.mktemp("usdz") / "plain.usdz"))


def test_classifier_names() -> None:
    assert classify("Wall0") == ("wall", "Wall") and classify("wall_3") == ("wall", "Wall") and classify("Wall_3F2504E0ab") == ("wall", "Wall")
    assert classify("Storage12") == ("object", "Storage") and classify("WasherDryer0") == ("object", "WasherDryer")
    assert classify("Opening1") == ("opening", "Opening") and classify("Floor0") == ("floor", "Floor")
    for group in ("Wall_grp", "Walls", "Object_grp", "Arch_grp", "Parametric_grp", "Television_group", "Room"):
        assert classify(group) is None, group


def test_canonical_skeleton(plain) -> None:  # type: ignore[no-untyped-def]
    sk, report = plain.skeleton, plain.report
    # 3.0 x 3.6 m room whose long walls run along z: normalized so the longest (window) wall lies on +x at z = 0
    assert (sk.dimensions.l, sk.dimensions.w, sk.dimensions.h) == (3.6, 3.0, 2.6) and report["ceilingHeightM"] == 2.6
    assert [(w.x1, w.z1, w.x2, w.z2) for w in sk.walls] == [(0, 0, 3.6, 0), (3.6, 0, 3.6, 3.0), (3.6, 3.0, 0, 3.0), (0, 3.0, 0, 0)]
    assert report["wallThicknessM"] == [0, 0, 0, 0]
    assert sorted(map(tuple, sk.floorPolygon)) == [(0, 0), (0, 3.0), (3.6, 0), (3.6, 3.0)]
    (win,) = sk.windows
    assert (win.wall, win.offset, win.width, win.sillHeight, win.height) == (0, 0.9, 1.2, 0.9, 1.3)
    (door,) = sk.doors  # nested under its wall in the USD, still found; no swing data in USDZ -> in/left
    assert (door.wall, door.width, door.height, door.swing, door.hinge) == (1, 0.9, 2.0, "in", "left")
    assert report["primCounts"]["wall"] == 4 and report["primCounts"]["duplicate"] == 9 and report["upAxis"] == "Y" and report["metersPerUnit"] == 1.0
    beds = [o for o in plain.objects if o.category == "Bed"]
    assert len(plain.objects) == 3 and (beds[0].w, beds[0].d, beds[0].h) == (1.4, 2.0, 0.55)
    assert all(o.rotation in (0, 90, 180, 270) for o in plain.objects)


@pytest.mark.parametrize("name", list(VARIANTS))
@requires_usd
def test_conversion_is_invariant(name: str, plain, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    out = convert_usdz(build_usdz(tmp_path / f"{name}.usdz", **VARIANTS[name]))
    assert out.skeleton == plain.skeleton
    assert [(o.category, o.x, o.z, o.rotation, o.w, o.d, o.h) for o in out.objects] == [(o.category, o.x, o.z, o.rotation, o.w, o.d, o.h) for o in plain.objects]


@requires_usd
def test_sanity_checks_fail_with_report(tmp_path: Path) -> None:
    tiny = ([Box("Wall0", (0.5, 1.2, 0), (1, 2.4, 0)), Box("Wall1", (1, 1.2, 0.5), (1, 2.4, 0), yaw=90), Box("Wall2", (0.5, 1.2, 1), (1, 2.4, 0))], [], [(0, 0), (1, 0), (1, 1), (0, 1)])
    with pytest.raises(ConversionError) as err:
        convert_usdz(build_usdz(tmp_path / "tiny.usdz", room=tiny))
    assert "floor area" in str(err.value) and err.value.report["primCounts"]["wall"] == 3
    walls, objects, floor = bedroom()
    with pytest.raises(ConversionError) as err2:
        convert_usdz(build_usdz(tmp_path / "two.usdz", room=(walls[:2], objects, floor)))
    assert "need at least 3" in str(err2.value)








@pytest.mark.skipif(not (FIXTURES / "rooms" / "real_scan.usdz").exists(), reason="no real RoomPlan export saved at fixtures/rooms/real_scan.usdz yet")
@requires_usd
def test_real_roomplan_export_converts() -> None:
    out = convert_usdz(FIXTURES / "rooms" / "real_scan.usdz")
    assert len(out.skeleton.walls) >= 3 and 2.0 <= out.skeleton.dimensions.h <= 4.0
    assert min(p[0] for p in out.skeleton.floorPolygon) == 0 and min(p[1] for p in out.skeleton.floorPolygon) == 0




def test_converter_emits_current_strict_contract_without_optional_usd(monkeypatch) -> None:
    """Exercise geometry conversion independently of the optional native reader."""
    from app import usdz_convert as converter
    from app.models import RoomSkeleton

    def box(kind, category, center, size, points=None):
        cx, cy, cz = center
        w, h, d = size
        corners = [(cx + sx * w / 2, cy + sy * h / 2, cz + sz * d / 2)
                   for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        return converter._Box(category, kind, category, corners, [(w, 0, 0), (0, h, 0), (0, 0, d)], points or [])

    boxes = [box("wall", "Wall", (2, 1.3, 0), (4, 2.6, 0)),
             box("wall", "Wall", (4, 1.3, 1.5), (0, 2.6, 3)),
             box("wall", "Wall", (2, 1.3, 3), (4, 2.6, 0)),
             box("wall", "Wall", (0, 1.3, 1.5), (0, 2.6, 3)),
             box("floor", "Floor", (2, 0, 1.5), (4, 0, 3), [(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)]),
             box("opening", "Opening", (1, 1, 3), (0.9, 2, 0)),
             box("window", "Window", (2, 1.5, 0), (1.2, 1.2, 0))]
    monkeypatch.setattr(converter, "_read", lambda path: (boxes, {"primCounts": {"wall": 4}, "warnings": []}))
    result = converter.convert_usdz("unused.usdz")
    assert RoomSkeleton.model_validate(result.skeleton.model_dump()) == result.skeleton
    assert result.report["floorAreaM2"] == 12
    assert result.skeleton.doors[0].swing == "out"
    assert result.skeleton.dimensions.h == 2.6
    assert all(window.wall < len(result.skeleton.walls) for window in result.skeleton.windows)
