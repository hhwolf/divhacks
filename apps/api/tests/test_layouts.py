from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

from tests.usdz_factory import build_usdz

DESK_BY_DOOR = {"id": "desk_1", "furnitureId": "desk", "x": 2.6, "z": 2.4, "rotation": 0, "locked": False}


def _kinds(client: TestClient, room_id: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for l in client.get(f"/rooms/{room_id}").json()["layouts"]:
        out.setdefault(l["kind"], []).append(l["name"])
    return out


def test_get_layout_resolves_furniture_and_validation(client: TestClient, bedroom: dict) -> None:
    body = client.get(f"/layouts/{bedroom['currentId']}").json()
    assert body["furniture"]["bed_double"]["dims"] == {"w": 1.4, "d": 1.9, "h": 0.55}
    assert body["furniture"]["bed_double"]["glbUrl"] == "/assets/furniture/bed_double.glb"
    assert body["validation"]["blocked"] is False and body["validation"]["metrics"]["walkability"] == "Good"


def test_base_layout_is_read_only(client: TestClient, bedroom: dict) -> None:
    base = bedroom["baseId"]
    items = client.get(f"/layouts/{base}").json()["layout"]["items"]
    assert client.put(f"/layouts/{base}", json={"items": items, "source": "editor"}).status_code == 403
    assert client.patch(f"/layouts/{base}", json={"name": "Mine now"}).status_code == 403
    assert client.delete(f"/layouts/{base}").status_code == 403
    assert client.post(f"/layouts/{base}/promote").status_code == 403
    fork = client.post(f"/layouts/{base}/fork", json={"name": "From base"})
    assert fork.status_code == 201 and fork.json()["kind"] == "variant" and fork.json()["parentLayoutId"] == base


def test_put_blocked_layout_returns_422_by_item(client: TestClient, bedroom: dict) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={}).json()
    items = fork["items"] + [{"id": "desk_1", "furnitureId": "desk", "x": 3.2, "z": 2.0, "rotation": 0, "locked": False}]
    r = client.put(f"/layouts/{fork['id']}", json={"items": items, "version": fork["version"]})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "bounds" in {v["rule"] for v in detail["violations"]}
    assert {v["rule"] for v in detail["byItem"]["desk_1"]} >= {"bounds"}
    saved = client.get(f"/layouts/{fork['id']}").json()["layout"]
    assert len(saved["items"]) == len(fork["items"]) and saved["version"] == 1


def test_put_versions_warnings_and_stale_writes(client: TestClient, bedroom: dict) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Desk try"}).json()
    body = client.put(f"/layouts/{fork['id']}", json={"items": fork["items"] + [DESK_BY_DOOR], "name": "Desk by door", "version": 1}).json()
    saved = body["layout"]
    assert saved["name"] == "Desk by door" and saved["version"] == 2
    assert saved["metrics"]["conflicts"] == 1 and body["validation"]["blocked"] is False  # door clearance is a conflict, not a save blocker
    assert {v["rule"] for v in body["validation"]["violations"]} == {"door_clearance"}
    stale = client.put(f"/layouts/{fork['id']}", json={"items": fork["items"], "version": 1})
    assert stale.status_code == 409 and stale.json()["detail"]["version"] == 2
    ok = client.put(f"/layouts/{fork['id']}", json={"items": fork["items"], "version": 2})
    assert ok.status_code == 200 and ok.json()["layout"]["version"] == 3
    legacy = client.put(f"/layouts/{fork['id']}", json={"items": fork["items"]})  # clients that don't send a version yet
    assert legacy.status_code == 200 and legacy.json()["layout"]["version"] == 4


def test_soft_warnings_are_saved_into_metrics(client: TestClient, bedroom: dict) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={}).json()
    shelf = {"id": "bookshelf_low_9", "furnitureId": "bookshelf_low", "x": 2.5, "z": 1.3, "rotation": 90, "locked": False}  # in front of the dresser
    r = client.put(f"/layouts/{fork['id']}", json={"items": fork["items"] + [shelf], "version": 1})
    assert r.status_code == 200
    assert r.json()["layout"]["metrics"]["warnings"] == ["Dresser needs 75 cm clear in front"]


def test_fork_dedupes_names(client: TestClient, bedroom: dict) -> None:
    a = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Variant A"}).json()
    b = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Variant A"}).json()
    assert a["kind"] == "variant" and a["isCurrent"] is False and a["parentLayoutId"] == bedroom["currentId"] and a["version"] == 1
    assert b["name"] == "Variant A (2)" and a["items"] == bedroom["current"]["items"]
    assert _kinds(client, bedroom["roomId"]) == {"base": ["Original Room"], "current": ["Current Room"], "variant": ["Variant A", "Variant A (2)"]}


def test_current_room_protections(client: TestClient, bedroom: dict) -> None:
    cur = bedroom["currentId"]
    assert client.delete(f"/layouts/{cur}").status_code == 409
    assert client.patch(f"/layouts/{cur}", json={"name": "Renamed"}).status_code == 409
    assert client.put(f"/layouts/{cur}", json={"name": "Renamed", "source": "editor"}).status_code == 409
    assert client.put(f"/layouts/{cur}", json={"items": bedroom["current"]["items"]}).status_code == 403  # the agent path never saves Current
    assert client.put(f"/layouts/{cur}", json={"items": bedroom["current"]["items"], "source": "editor"}).status_code == 200
    assert client.get(f"/layouts/{cur}").json()["layout"]["name"] == "Current Room"


def test_rename_and_delete_variant(client: TestClient, bedroom: dict) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Scratch"}).json()
    other = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Other"}).json()
    assert client.patch(f"/layouts/{fork['id']}", json={"name": "Other"}).status_code == 409
    assert client.patch(f"/layouts/{fork['id']}", json={"name": "Reading nook"}).json()["name"] == "Reading nook"
    assert client.delete(f"/layouts/{fork['id']}").status_code == 204
    assert client.get(f"/layouts/{fork['id']}").status_code == 404
    assert client.get(f"/layouts/{other['id']}").status_code == 200


def test_promote_keeps_the_old_current_as_a_variant(client: TestClient, bedroom: dict) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Marketplace Desk"}).json()
    assert client.put(f"/layouts/{fork['id']}", json={"items": fork["items"] + [dict(DESK_BY_DOOR, x=2.5, z=0.6, rotation=90)], "version": 1}).status_code == 200
    r = client.post(f"/layouts/{fork['id']}/promote")
    assert r.status_code == 200
    body = r.json()
    today = datetime.now(UTC)
    assert body["current"]["id"] == fork["id"] and body["current"]["kind"] == "current" and body["current"]["name"] == "Current Room"
    assert body["current"]["promotedFromName"] == "Marketplace Desk" and len(body["current"]["items"]) == 6
    assert body["previous"]["id"] == bedroom["currentId"] and body["previous"]["kind"] == "variant"
    assert body["previous"]["name"] == f"Previous Room, {today:%b} {today.day}" and body["previous"]["items"] == bedroom["current"]["items"]
    assert client.get(f"/rooms/{bedroom['roomId']}").json()["room"]["currentLayoutId"] == fork["id"]
    kinds = _kinds(client, bedroom["roomId"])
    assert len(kinds["base"]) == 1 and len(kinds["current"]) == 1
    assert client.post(f"/layouts/{fork['id']}/promote").status_code == 409
    assert client.delete(f"/layouts/{bedroom['currentId']}").status_code == 204  # the old current is an ordinary variant now


def test_restore_from_base_or_empty(client: TestClient, bedroom: dict) -> None:
    cur = bedroom["currentId"]
    moved = [dict(i, x=i["x"] + 0.1) if i["furnitureId"] == "plant" else i for i in bedroom["current"]["items"]]
    client.put(f"/layouts/{cur}", json={"items": moved, "source": "editor", "version": 1})
    restored = client.post(f"/rooms/{bedroom['roomId']}/restore", json={"target": "base"})
    assert restored.status_code == 201
    r = restored.json()
    assert r["kind"] == "variant" and r["name"] == "Original Room (restored)" and r["parentLayoutId"] == bedroom["baseId"]
    assert r["items"] == bedroom["current"]["items"] != moved
    empty = client.post(f"/rooms/{bedroom['roomId']}/restore", json={"target": "empty", "name": "Blank slate"}).json()
    assert empty["items"] == [] and empty["name"] == "Blank slate" and empty["metrics"]["openFloor"] == 100
    assert client.post(f"/rooms/{bedroom['roomId']}/restore", json={"target": "base"}).json()["name"] == "Original Room (restored) (2)"
    assert client.post(f"/rooms/{bedroom['roomId']}/restore", json={"target": "attic"}).status_code == 422


def test_delete_room_cascades(client: TestClient, data_dir: Path, tmp_path: Path) -> None:
    with build_usdz(tmp_path / "scan.usdz").open("rb") as fh:
        created = client.post("/rooms", files={"usdz": ("Room.usdz", fh, "model/vnd.usdz+zip")}).json()
    room_id, cur = created["room"]["id"], created["currentLayout"]["id"]
    client.post(f"/layouts/{cur}/fork", json={"name": "Keep?"})
    client.post("/agent/request", json={"roomId": room_id, "layoutId": cur, "text": "make space for yoga"})
    other = client.post("/rooms", json={"sample": True}).json()["room"]["id"]
    blob = data_dir / "blob" / "scans" / f"{room_id}.usdz"
    assert blob.exists()
    assert client.delete(f"/rooms/{room_id}").status_code == 204
    db = client.app.state.ctx.repo._db  # type: ignore[attr-defined]
    assert not [d for c in ("layouts", "agent_requests", "furniture") for d in db[c] if d.get("roomId") == room_id]
    assert not blob.exists() and client.get(f"/rooms/{room_id}").status_code == 404
    assert client.get(f"/rooms/{other}").status_code == 200 and len(client.get(f"/rooms/{other}").json()["layouts"]) == 2
    assert client.delete(f"/rooms/{room_id}").status_code == 404


def test_persistence_across_restart(client: TestClient, bedroom: dict, data_dir: Path) -> None:
    fork = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Keep me"}).json()
    assert (data_dir / "db.json").exists()
    with TestClient(create_app(Settings.from_env())) as fresh:
        names = {l["name"] for l in fresh.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]}
        assert names == {"Original Room", "Current Room", "Keep me"}
        assert fresh.get(f"/layouts/{fork['id']}").json()["layout"]["parentLayoutId"] == bedroom["currentId"]


def test_legacy_layout_docs_still_load(client: TestClient, bedroom: dict) -> None:
    """Layouts saved before `kind`/`version` existed: isCurrent maps to kind, PUT works without a version field."""
    repo = client.app.state.ctx.repo
    doc = next(d for d in repo._db["layouts"] if d["id"] == bedroom["currentId"])  # type: ignore[attr-defined]
    for key in ("kind", "version"):
        doc.pop(key)
    got = client.get(f"/layouts/{bedroom['currentId']}").json()["layout"]
    assert got["kind"] == "current" and got["version"] == 1
    assert client.put(f"/layouts/{bedroom['currentId']}", json={"items": bedroom["current"]["items"], "source": "editor"}).json()["layout"]["version"] == 2
