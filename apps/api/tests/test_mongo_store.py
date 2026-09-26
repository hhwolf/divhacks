"""Evidence for benchmark line E3: with MONGODB_URI set the API runs on MongoDB (motor). Uses an in-memory mongod from pymongo_inmemory.

pymongo_inmemory downloads a mongod tarball on first run (mongodb-macos-x86_64-8.0.4 here, ~440 MB extracted) into
`<site-packages>/pymongo_inmemory/../.cache/{download,extract}` (i.e. `.venv/lib/python3.13/site-packages/.cache`) and reuses it on later runs
(cold start ~14 s, warm ~1 s). Configuration precedence is env vars `PYMONGOIM__<OPTION>` > `setup.cfg` > `pymongo_inmemory.ini` (both in the
directory pytest is invoked from) > defaults. Useful knobs: `PYMONGOIM__DOWNLOAD_FOLDER` / `PYMONGOIM__EXTRACT_FOLDER` to relocate the cache (e.g.
outside the venv so `rm -rf .venv` doesn't force a re-download), `PYMONGOIM__MONGO_VERSION` to pin a version, `PYMONGOIM__USE_LOCAL_MONGOD=True`
to use an installed mongod instead of downloading. This module sets `PYMONGOIM__MONGOD_PORT` to a free port so a real local mongod on 27017 is
never touched. If the binary cannot be downloaded (offline CI), every test here is skipped with the reason.
"""

from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator

import pytest
from app.config import Settings
from app.main import create_app
from app.repo.mongo_store import MongoStore
from fastapi.testclient import TestClient


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def mongo_uri() -> Iterator[str]:
    """One in-memory mongod for the module; its data folder is discarded on stop."""
    pytest.importorskip("pymongo_inmemory")
    import os

    from pymongo_inmemory import Mongod
    from pymongo_inmemory.context import Context

    os.environ["PYMONGOIM__MONGOD_PORT"] = str(_free_port())
    try:
        mongod = Mongod(Context())
        mongod.start()
    except Exception as exc:  # download blocked / unsupported platform
        pytest.skip(f"in-memory mongod unavailable: {exc}")
    try:
        yield mongod.connection_string
    finally:
        mongod.stop()
        os.environ.pop("PYMONGOIM__MONGOD_PORT", None)


def _db() -> str:
    return f"arp_test_{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_rooms_crud(mongo_uri: str) -> None:
    store = MongoStore(mongo_uri, _db())
    room = {"id": "r1", "name": "Bedroom", "userId": "u1", "skeleton": {"walls": []}}
    assert await store.insert("rooms", room) == room
    got = await store.get("rooms", "r1")
    assert got == room and "_id" not in got
    assert await store.get("rooms", "missing") is None
    await store.insert("rooms", {"id": "r2", "name": "Studio", "userId": "u2"})
    assert [r["id"] for r in await store.list("rooms")] == ["r1", "r2"]
    assert [r["id"] for r in await store.list("rooms", userId="u2")] == ["r2"]
    updated = await store.update("rooms", "r1", {"name": "Renamed"})
    assert updated and updated["name"] == "Renamed" and updated["skeleton"] == {"walls": []}
    assert await store.update("rooms", "missing", {"name": "x"}) is None
    assert await store.delete("rooms", "r1") is True
    assert await store.delete("rooms", "r1") is False
    assert [r["id"] for r in await store.list("rooms")] == ["r2"]


@pytest.mark.asyncio
async def test_layouts_list_by_room_update_delete(mongo_uri: str) -> None:
    store = MongoStore(mongo_uri, _db())
    for i, room in enumerate(("ra", "ra", "rb")):
        await store.insert("layouts", {"id": f"l{i}", "roomId": room, "name": f"L{i}", "isCurrent": i == 0, "items": [], "zones": []})
    assert [l["id"] for l in await store.list_by_room("layouts", "ra")] == ["l0", "l1"]
    assert [l["id"] for l in await store.list_by_room("layouts", "rb")] == ["l2"]
    assert await store.list_by_room("layouts", "nope") == []
    items = [{"id": "desk_1", "furnitureId": "desk", "x": 2.5, "z": 0.3, "rotation": 0, "locked": False}]
    saved = await store.update("layouts", "l1", {"items": items, "metrics": {"conflicts": 0}})
    assert saved and saved["items"] == items and saved["metrics"] == {"conflicts": 0} and saved["name"] == "L1"
    assert (await store.get("layouts", "l1"))["items"] == items
    assert await store.delete("layouts", "l1") is True
    assert [l["id"] for l in await store.list_by_room("layouts", "ra")] == ["l0"]


def test_api_flow_with_mongodb_uri(mongo_uri: str, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("MONGODB_URI", mongo_uri)
    monkeypatch.setenv("MONGODB_DB", _db())
    monkeypatch.setenv("ARP_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MOCK_MODE", raising=False)
    settings = Settings.from_env()
    assert settings.mongo_live
    with TestClient(create_app(settings)) as client:
        assert type(client.app.state.ctx.repo).__name__ == "MongoStore"
        assert client.get("/health").json()["integrations"]["mongo"] == "live"
        created = client.post("/rooms", json={"sample": "nyc-bedroom"}).json()
        room_id, cur = created["room"]["id"], created["currentLayout"]["id"]
        fork = client.post(f"/layouts/{cur}/fork", json={"name": "Mongo variant"})
        assert fork.status_code == 201
        items = fork.json()["items"] + [{"id": "desk_1", "furnitureId": "desk", "x": 2.5, "z": 0.3, "rotation": 0, "locked": False}]
        put = client.put(f"/layouts/{fork.json()['id']}", json={"items": items})
        assert put.status_code == 200 and len(put.json()["layout"]["items"]) == 6
        assert len(client.get(f"/layouts/{fork.json()['id']}").json()["layout"]["items"]) == 6
        assert [l["name"] for l in client.get(f"/rooms/{room_id}").json()["layouts"]] == ["Current Room", "Mongo variant"]
        assert client.delete(f"/layouts/{cur}").status_code == 409
        assert client.get(f"/layouts/{cur}").json()["layout"]["isCurrent"] is True
    assert not (tmp_path / "db.json").exists()  # nothing was written to the JSON store
