from fastapi.testclient import TestClient


def test_compare_current_vs_desk_variant(client: TestClient, bedroom: dict) -> None:
    item = client.post("/furniture/from-link", json={"url": "http://testserver/fixtures/listings/desk"}).json()
    out = client.post("/agent/request", json={"text": "Will this fit beside my window without moving my bed?", "roomId": bedroom["roomId"], "baseLayoutId": bedroom["currentId"], "furnitureId": item["id"], "channel": "app"}).json()
    body = client.get(f"/layouts/{bedroom['currentId']}/compare/{out['layout']['id']}").json()
    assert body["a"]["id"] == bedroom["currentId"] and body["b"]["id"] == out["layout"]["id"]
    assert body["deltas"]["openFloor"] < 0 and body["deltas"]["conflicts"] == 0
    assert set(body["deltas"]) == {"openFloor", "conflicts", "reachableStorage", "largestFreeRectArea"}
    assert body["moved"] == [] and body["removed"] == []
    assert len(body["added"]) == 1 and body["added"][0]["name"] == "Desk"


def test_compare_reports_moved_items(client: TestClient, bedroom: dict) -> None:
    out = client.post("/agent/request", json={"text": "make space for yoga, keep my dresser", "roomId": bedroom["roomId"], "baseLayoutId": bedroom["currentId"], "channel": "app"}).json()
    body = client.get(f"/layouts/{bedroom['currentId']}/compare/{out['layout']['id']}").json()
    moved = {m["id"]: m for m in body["moved"]}
    assert set(moved) == {"bookshelf_low_4", "plant_5"}
    assert moved["plant_5"]["name"] == "Potted plant" and set(moved["plant_5"]["from"]) == {"x", "z", "rotation"}
    assert body["added"] == [] and body["removed"] == []
    assert client.get(f"/layouts/{bedroom['currentId']}/compare/missing").status_code == 404
