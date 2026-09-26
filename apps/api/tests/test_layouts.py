from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_get_layout_resolves_furniture_and_validation(client: TestClient, bedroom: dict) -> None:
    body = client.get(f"/layouts/{bedroom['currentId']}").json()
    assert body["furniture"]["bed_double"]["dims"] == {"w": 1.4, "d": 1.9, "h": 0.55}
    assert body["furniture"]["bed_double"]["glbUrl"] == "/assets/furniture/bed_double.glb"
    assert body["validation"]["blocked"] is False and body["validation"]["metrics"]["walkability"] == "Good"


def test_put_blocked_layout_returns_422(client: TestClient, bedroom: dict) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={}).json()
    items = fork["items"] + [{"id": "desk_1", "furnitureId": "desk", "x": 3.2, "z": 2.0, "rotation": 0, "locked": False}]
    r = client.put(f"/layouts/{fork['id']}", json={"items": items})
    assert r.status_code == 422
    rules = {v["rule"] for v in r.json()["detail"]["violations"]}
    assert "bounds" in rules
    assert len(client.get(f"/layouts/{fork['id']}").json()["layout"]["items"]) == len(fork["items"])


def test_put_warning_layout_saves_and_recomputes_metrics(client: TestClient, bedroom: dict) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Desk try"}).json()
    items = fork["items"] + [{"id": "desk_1", "furnitureId": "desk", "x": 2.6, "z": 2.4, "rotation": 0, "locked": False}]
    body = client.put(f"/layouts/{fork['id']}", json={"items": items, "name": "Desk by door"}).json()
    assert body["layout"]["name"] == "Desk by door"
    assert body["layout"]["metrics"]["conflicts"] == 1 and body["validation"]["blocked"] is False
    assert {v["rule"] for v in body["validation"]["violations"]} == {"door_clearance"}


def test_fork_creates_child(client: TestClient, bedroom: dict) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Variant A"}).json()
    assert fork["isCurrent"] is False and fork["parentLayoutId"] == bedroom["currentId"] and fork["name"] == "Variant A"
    assert fork["items"] == bedroom["current"]["items"]
    assert len(client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]) == 2


def test_current_room_protections(client: TestClient, bedroom: dict) -> None:
    cur = bedroom["currentId"]
    assert client.delete(f"/layouts/{cur}").status_code == 409
    assert client.put(f"/layouts/{cur}", json={"name": "Renamed", "source": "editor"}).status_code == 409
    assert client.put(f"/layouts/{cur}", json={"items": bedroom["current"]["items"]}).status_code == 403
    assert client.put(f"/layouts/{cur}", json={"items": bedroom["current"]["items"], "source": "editor"}).status_code == 200
    assert client.get(f"/layouts/{cur}").json()["layout"]["name"] == "Current Room"


def test_delete_variant(client: TestClient, bedroom: dict) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={}).json()
    assert client.delete(f"/layouts/{fork['id']}").status_code == 204
    assert client.get(f"/layouts/{fork['id']}").status_code == 404


def test_persistence_across_restart(client: TestClient, bedroom: dict, data_dir: Path) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Keep me"}).json()
    assert (data_dir / "db.json").exists()
    with TestClient(create_app(Settings.from_env())) as fresh:
        names = {l["name"] for l in fresh.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]}
        assert names == {"Current Room", "Keep me"}
        assert fresh.get(f"/layouts/{fork['id']}").json()["layout"]["parentLayoutId"] == bedroom["currentId"]
