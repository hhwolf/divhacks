"""RoomPlan USDZ -> canonical JSON. Synthetic scans from tests/usdz_factory.py; a real export at fixtures/rooms/real_scan.usdz is used when present."""

from pathlib import Path

import pytest
from app.services.usdz_convert import ConversionError, classify, convert_usdz
from fastapi.testclient import TestClient

from tests.conftest import FIXTURES
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
    assert (sk.dimensions.l, sk.dimensions.w, sk.dimensions.h) == (3.6, 3.0, 2.6) and sk.ceilingHeight == 2.6
    assert [(w.x1, w.z1, w.x2, w.z2) for w in sk.walls] == [(0, 0, 3.6, 0), (3.6, 0, 3.6, 3.0), (3.6, 3.0, 0, 3.0), (0, 3.0, 0, 0)]
    assert [w.id for w in sk.walls] == ["w0", "w1", "w2", "w3"] and all(w.thickness == 0 for w in sk.walls)
    assert sorted(map(tuple, sk.floorPolygon)) == [(0, 0), (0, 3.0), (3.6, 0), (3.6, 3.0)]
    (win,) = sk.windows
    assert (win.wall, win.wallId, win.offset, win.width, win.sillHeight, win.height) == (0, "w0", 0.9, 1.2, 0.9, 1.3)
    (door,) = sk.doors  # nested under its wall in the USD, still found; no swing data in USDZ -> in/left
    assert (door.wallId, door.width, door.height, door.swing, door.hinge, door.opening) == ("w1", 0.9, 2.0, "in", "left", None)
    assert report["primCounts"]["wall"] == 4 and report["primCounts"]["duplicate"] == 9 and report["upAxis"] == "Y" and report["metersPerUnit"] == 1.0
    beds = [o for o in plain.objects if o.category == "Bed"]
    assert len(plain.objects) == 3 and (beds[0].w, beds[0].d, beds[0].h) == (1.4, 2.0, 0.55)
    assert all(o.rotation in (0, 90, 180, 270) for o in plain.objects)


@pytest.mark.parametrize("name", list(VARIANTS))
def test_conversion_is_invariant(name: str, plain, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    out = convert_usdz(build_usdz(tmp_path / f"{name}.usdz", **VARIANTS[name]))
    assert out.skeleton == plain.skeleton
    assert [(o.category, o.x, o.z, o.rotation, o.w, o.d, o.h) for o in out.objects] == [(o.category, o.x, o.z, o.rotation, o.w, o.d, o.h) for o in plain.objects]


def test_sanity_checks_fail_with_report(tmp_path: Path) -> None:
    tiny = ([Box("Wall0", (0.5, 1.2, 0), (1, 2.4, 0)), Box("Wall1", (1, 1.2, 0.5), (1, 2.4, 0), yaw=90), Box("Wall2", (0.5, 1.2, 1), (1, 2.4, 0))], [], [(0, 0), (1, 0), (1, 1), (0, 1)])
    with pytest.raises(ConversionError) as err:
        convert_usdz(build_usdz(tmp_path / "tiny.usdz", room=tiny))
    assert "floor area" in str(err.value) and err.value.report["primCounts"]["wall"] == 3
    walls, objects, floor = bedroom()
    with pytest.raises(ConversionError) as err2:
        convert_usdz(build_usdz(tmp_path / "two.usdz", room=(walls[:2], objects, floor)))
    assert "need at least 3" in str(err2.value)


def test_upload_usdz_creates_room_with_scanned_furniture(client: TestClient, tmp_path: Path, data_dir: Path) -> None:
    usdz = build_usdz(tmp_path / "scan.usdz", yaw=30, offset=(5.0, -2.0))
    with usdz.open("rb") as fh:
        r = client.post("/rooms", files={"usdz": ("Room.usdz", fh, "model/vnd.usdz+zip")}, data={"name": "Scanned bedroom"})
    assert r.status_code == 201, r.text
    body = r.json()
    room, base, cur = body["room"], body["baseLayout"], body["currentLayout"]
    assert room["source"] == "scan" and room["name"] == "Scanned bedroom" and room["usdzUrl"] == f"/blob/scans/{room['id']}.usdz"
    assert (data_dir / "blob" / "scans" / f"{room['id']}.usdz").read_bytes() == usdz.read_bytes()
    assert room["conversion"]["primCounts"]["object"] == 3 and room["conversion"]["upAxis"] == "Y"
    assert client.get(room["usdzUrl"]).status_code == 200
    layout = client.get(f"/layouts/{base['id']}").json()
    by_cat = {f["scanCategory"]: f for f in layout["furniture"].values()}
    assert by_cat["Bed"]["source"] == "scan" and by_cat["Bed"]["glbUrl"] == "/assets/furniture/bed_double.glb" and by_cat["Bed"]["dims"] == {"w": 1.4, "d": 2.0, "h": 0.55}
    assert by_cat["Storage"]["presetId"] == "dresser" and by_cat["Toilet"]["category"] == "other" and by_cat["Toilet"]["presetId"] is None
    locked = {layout["furniture"][i["furnitureId"]]["scanCategory"]: i["locked"] for i in base["items"]}
    assert locked == {"Bed": False, "Storage": False, "Toilet": True}  # nobody moves a toilet
    assert cur["items"] == base["items"] and cur["parentLayoutId"] == base["id"]
    assert not [f for f in client.get("/furniture").json()["items"] if f["source"] == "scan"]  # scanned pieces stay out of the palette


def test_failed_conversion_keeps_the_scan_and_can_rerun(client: TestClient, tmp_path: Path, data_dir: Path) -> None:
    walls, objects, floor = bedroom()
    broken = build_usdz(tmp_path / "broken.usdz", room=(walls[:2], objects, floor))
    with broken.open("rb") as fh:
        r = client.post("/rooms", files={"usdz": ("Room.usdz", fh, "model/vnd.usdz+zip")})
    assert r.status_code == 422
    detail = r.json()["detail"]
    report = detail["conversionReport"]
    assert "sample room" in detail["message"] and report["primCounts"]["wall"] == 2 and report["usdzUrl"].startswith("/blob/scans/")
    assert (data_dir / "blob" / report["usdzUrl"].removeprefix("/blob/")).exists()  # the raw scan is not lost
    assert client.get("/rooms").json() == []
    # the fixed classifier would re-run on the stored file: re-conversion by usdzUrl goes through the same path
    good = build_usdz(tmp_path / "good.usdz")
    with good.open("rb") as fh:
        stored = client.post("/rooms", files={"usdz": ("Room.usdz", fh, "model/vnd.usdz+zip")}).json()["room"]["usdzUrl"]
    again = client.post("/rooms", json={"usdzUrl": stored, "name": "Re-run"})
    assert again.status_code == 201 and again.json()["room"]["usdzUrl"] == stored and again.json()["room"]["name"] == "Re-run"


def test_bad_uploads(client: TestClient) -> None:
    garbage = client.post("/rooms", files={"usdz": ("Room.usdz", b"not a usdz at all", "model/vnd.usdz+zip")})
    assert garbage.status_code == 422 and "conversionReport" in garbage.json()["detail"]
    assert client.post("/rooms", files={"usdz": ("Room.usdz", b"", "model/vnd.usdz+zip")}).status_code == 422
    assert client.post("/rooms", json={"usdzUrl": "https://evil.example.com/x.usdz"}).status_code == 422


@pytest.mark.skipif(not (FIXTURES / "rooms" / "real_scan.usdz").exists(), reason="no real RoomPlan export saved at fixtures/rooms/real_scan.usdz yet")
def test_real_roomplan_export_converts() -> None:
    out = convert_usdz(FIXTURES / "rooms" / "real_scan.usdz")
    assert len(out.skeleton.walls) >= 3 and 2.0 <= (out.skeleton.ceilingHeight or 0) <= 4.0
    assert min(p[0] for p in out.skeleton.floorPolygon) == 0 and min(p[1] for p in out.skeleton.floorPolygon) == 0


def test_tucked_chair_is_pulled_out_so_the_scan_can_be_saved(client: TestClient, tmp_path: Path) -> None:
    walls, objects, floor = bedroom()
    objects = [o for o in objects if o.name != "Toilet0"] + [Box("Table0", (2.4, 0.375, 0.35), (1.2, 0.75, 0.6)), Box("Chair0", (2.4, 0.45, 0.55), (0.45, 0.9, 0.45), yaw=180)]
    with build_usdz(tmp_path / "tucked.usdz", room=(walls, objects, floor)).open("rb") as fh:
        body = client.post("/rooms", files={"usdz": ("Room.usdz", fh, "model/vnd.usdz+zip")}).json()
    assert "pulled a chair out from under the desk" in body["room"]["conversion"]["warnings"]
    cur = body["currentLayout"]
    assert not client.get(f"/layouts/{cur['id']}").json()["validation"]["blocked"]
    assert client.put(f"/layouts/{cur['id']}", json={"items": cur["items"], "source": "editor", "version": 1}).status_code == 200
