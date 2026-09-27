import json

from fastapi.testclient import TestClient

from tests.conftest import load_fixture

GEOMETRY = ("x1", "z1", "x2", "z2", "height")


def test_sample_room_creates_base_and_current(client: TestClient) -> None:
    r = client.post("/rooms", json={"sample": "nyc-bedroom"})
    assert r.status_code == 201
    body = r.json()
    sample = load_fixture("rooms", "sample-nyc-bedroom.json")
    room, base, cur = body["room"], body["baseLayout"], body["currentLayout"]
    sk = room["skeleton"]
    assert [{k: w[k] for k in GEOMETRY} for w in sk["walls"]] == sample["skeleton"]["walls"]
    assert [w["id"] for w in sk["walls"]] == ["w0", "w1", "w2", "w3"] and sk["ceilingHeight"] == 2.7
    door = sk["doors"][0]
    assert door["swing"] == "in" and door["id"] == "d0" and door["wallId"] == "w2" and door["center"] == [2.65, 3.0]
    assert sk["windows"][0]["width"] == 1.2 and sk["windows"][0]["center"] == [1.6, 0.0]
    assert base["kind"] == "base" and base["name"] == "Original Room" and base["isCurrent"] is False and base["createdBy"] == "system"
    assert cur["kind"] == "current" and cur["isCurrent"] is True and cur["name"] == "Current Room" and cur["parentLayoutId"] == base["id"]
    assert room["baseLayoutId"] == base["id"] and room["currentLayoutId"] == cur["id"]
    assert [i["id"] for i in cur["items"]] == ["bed_double_1", "nightstand_2", "dresser_3", "bookshelf_low_4", "plant_5"]
    assert cur["items"] == base["items"] and cur["items"][0]["locked"] is True
    assert cur["metrics"]["openFloor"] == 62.3 and cur["metrics"]["openFloorPct"] == 62.3 and cur["metrics"]["warnings"] == []
    assert cur["version"] == 1 and body["layouts"] == [base, cur]


def test_sample_true_uses_default_sample(client: TestClient) -> None:
    assert client.post("/rooms", json={"sample": True}).json()["room"]["name"] == "NYC bedroom (sample)"
    form = client.post("/rooms", data={"sample": "true"})
    assert form.status_code == 201 and form.json()["room"]["source"] == "sample"


def test_studio_sample(client: TestClient) -> None:
    body = client.post("/rooms", json={"sample": "studio"}).json()
    assert body["room"]["skeleton"]["dimensions"] == {"l": 5.0, "w": 3.6, "h": 2.6}
    assert len(body["room"]["skeleton"]["windows"]) == 2


def test_manual_dimensions_build_walls(client: TestClient) -> None:
    body = client.post(
        "/rooms",
        json={
            "name": "Manual",
            "dimensions": {"l": 3.0, "w": 2.5, "h": 2.6},
            "doors": [{"wall": 2, "offset": 0.2, "width": 0.8, "swing": "in", "hinge": "left"}],
            "windows": [{"wall": 0, "offset": 1.0, "width": 1.0, "sillHeight": 0.9, "height": 1.2}],
        },
    ).json()
    sk = body["room"]["skeleton"]
    assert body["room"]["source"] == "manual"
    assert len(sk["walls"]) == 4
    assert sk["walls"][0] == {"x1": 0.0, "z1": 0.0, "x2": 3.0, "z2": 0.0, "height": 2.6, "id": "w0"}
    assert sk["floorPolygon"] == [[0.0, 0.0], [3.0, 0.0], [3.0, 2.5], [0.0, 2.5]]
    assert sk["doors"][0]["hinge"] == "left" and sk["windows"][0]["offset"] == 1.0
    assert body["currentLayout"]["items"] == [] and body["baseLayout"]["items"] == []


def test_manual_dimensions_as_multipart(client: TestClient) -> None:
    r = client.post("/rooms", data={"name": "Form room", "dimensions": json.dumps({"l": 3.2, "w": 2.8, "h": 2.5}), "doors": json.dumps([{"wall": 1, "offset": 0.4, "width": 0.8, "swing": "in", "hinge": "right"}])})
    assert r.status_code == 201
    assert r.json()["room"]["skeleton"]["doors"][0]["wallId"] == "w1"


def test_legacy_skeleton_json_body(client: TestClient) -> None:
    sample = load_fixture("rooms", "sample-studio.json")
    body = client.post("/rooms", json={"name": "Scan", "skeleton": sample["skeleton"], "objects": sample["objects"][:2]}).json()
    assert body["room"]["source"] == "scan"
    assert {k: v for k, v in body["room"]["skeleton"]["doors"][0].items() if k in sample["skeleton"]["doors"][0]} == sample["skeleton"]["doors"][0]
    assert [i["furnitureId"] for i in body["currentLayout"]["items"]] == ["bed_single", "sofa"]


def test_rejects_missing_shape_and_bad_openings(client: TestClient) -> None:
    assert client.post("/rooms", json={"name": "nothing"}).status_code == 422
    bad = client.post("/rooms", json={"dimensions": {"l": 3, "w": 3, "h": 2.5}, "doors": [{"wall": 7, "offset": 0, "width": 0.8, "swing": "in", "hinge": "left"}]})
    assert bad.status_code == 422 and "wall 7" in bad.json()["detail"]
    past_end = client.post("/rooms", json={"dimensions": {"l": 3, "w": 3, "h": 2.5}, "windows": [{"wall": 0, "offset": 2.5, "width": 1.0, "sillHeight": 0.9, "height": 1.0}]})
    assert past_end.status_code == 422


def test_get_list_and_rename_rooms(client: TestClient) -> None:
    created = client.post("/rooms", json={"sample": "nyc-bedroom"}).json()
    room_id = created["room"]["id"]
    got = client.get(f"/rooms/{room_id}").json()
    assert got["room"]["id"] == room_id and {l["kind"] for l in got["layouts"]} == {"base", "current"}
    listed = client.get("/rooms").json()
    row = next(r for r in listed if r["id"] == room_id)
    assert row["thumbnailUrl"] is None and row["updatedAt"] and row["userId"] == "demo"
    assert [r["id"] for r in client.get("/rooms", params={"userId": "demo"}).json()] == [room_id]
    assert client.get("/rooms", params={"userId": "someone-else"}).json() == []
    renamed = client.patch(f"/rooms/{room_id}", json={"name": "My bedroom"}).json()
    assert renamed["name"] == "My bedroom" and renamed["skeleton"] == created["room"]["skeleton"]
    assert client.get("/rooms/nope").status_code == 404
