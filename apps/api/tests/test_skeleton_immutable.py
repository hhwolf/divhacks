from fastapi.testclient import TestClient


def test_layout_edits_never_touch_skeleton(client: TestClient, bedroom: dict) -> None:
    before = client.get(f"/rooms/{bedroom['roomId']}").json()["room"]["skeleton"]
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Scratch"}).json()
    items = [dict(i, x=i["x"] + 0.1) if i["furnitureId"] == "plant" else i for i in fork["items"]]
    assert client.put(f"/layouts/{fork['id']}", json={"items": items, "zones": [{"label": "Yoga", "x": 1.4, "z": 0.4, "w": 1.2, "d": 1.8}]}).status_code == 200
    assert client.put(f"/layouts/{bedroom['currentId']}", json={"items": bedroom["current"]["items"], "source": "editor"}).status_code == 200
    assert client.delete(f"/layouts/{fork['id']}").status_code == 204
    r = client.post("/agent/request", json={"text": "make space for yoga, keep my dresser", "roomId": bedroom["roomId"], "layoutId": bedroom["currentId"]})
    assert r.json()["status"] == "ok"
    after = client.get(f"/rooms/{bedroom['roomId']}").json()["room"]["skeleton"]
    assert after == before
