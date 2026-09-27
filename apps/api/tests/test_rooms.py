from fastapi.testclient import TestClient

from tests.conftest import load_fixture


def test_sample_room_seeds_current_layout(client: TestClient) -> None:
    r = client.post("/rooms", json={"sample": "nyc-bedroom"})
    assert r.status_code == 201
    body = r.json()
    sample = load_fixture("rooms", "sample-nyc-bedroom.json")
    assert body["room"]["skeleton"]["walls"] == [{**w} for w in sample["skeleton"]["walls"]]
    assert body["room"]["spaceTypes"] == sample["spaceTypes"]
    assert [e["id"] for e in body["room"]["elements"]] == [e["id"] for e in sample["elements"]]
    assert body["room"]["skeleton"]["doors"][0]["swing"] == "in"
    assert body["room"]["skeleton"]["windows"][0]["width"] == 1.2
    cur = body["currentLayout"]
    assert cur["isCurrent"] is True and cur["createdBy"] == "system" and cur["name"] == "Current Room"
    assert [i["id"] for i in cur["items"]] == ["bed_double_1", "nightstand_2", "dresser_3", "bookshelf_low_4", "plant_5"]
    assert cur["items"][0]["locked"] is True
    assert cur["metrics"]["openFloor"] == 62.3
    assert body["layouts"] == [cur]


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
    assert sk["walls"][0] == {"x1": 0.0, "z1": 0.0, "x2": 3.0, "z2": 0.0, "height": 2.6}
    assert sk["walls"][2] == {"x1": 3.0, "z1": 2.5, "x2": 0.0, "z2": 2.5, "height": 2.6}
    assert sk["floorPolygon"] == [[0.0, 0.0], [3.0, 0.0], [3.0, 2.5], [0.0, 2.5]]
    assert sk["doors"][0]["hinge"] == "left" and sk["windows"][0]["offset"] == 1.0
    assert body["currentLayout"]["items"] == []


def test_roomplan_export_body(client: TestClient) -> None:
    sample = load_fixture("rooms", "sample-studio.json")
    body = client.post("/rooms", json={"name": "Scan", "skeleton": sample["skeleton"], "objects": sample["objects"][:2]}).json()
    assert body["room"]["source"] == "scan"
    assert body["room"]["skeleton"]["doors"] == [{**sample["skeleton"]["doors"][0]}]
    assert [i["furnitureId"] for i in body["currentLayout"]["items"]] == ["bed_single", "sofa"]


def test_missing_shape_rejected(client: TestClient) -> None:
    assert client.post("/rooms", json={"name": "nothing"}).status_code == 422


def test_get_and_list_rooms(client: TestClient) -> None:
    created = client.post("/rooms", json={"sample": "nyc-bedroom"}).json()
    got = client.get(f"/rooms/{created['room']['id']}").json()
    assert got["room"]["id"] == created["room"]["id"] and len(got["layouts"]) == 1
    assert any(r["id"] == created["room"]["id"] for r in client.get("/rooms").json())
    assert client.get("/rooms/nope").status_code == 404
