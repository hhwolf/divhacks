"""Evidence for benchmark line E3: with Supabase configured, the API uses Supabase REST storage.

The tests run against an httpx.MockTransport fake of Supabase's `/rest/v1/{table}` Data API, so they do not need network or a real project.
"""

from __future__ import annotations

import time
import json
from typing import Any

import httpx
import pytest
from app.config import Settings
from app.main import create_app
from app.repo.supabase_store import SupabaseStore
from fastapi.testclient import TestClient


class FakeSupabaseApi:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    @staticmethod
    def _match(row: dict[str, Any], key: str, value: str) -> bool:
        return str(row.get(key)) == value[3:] if value.startswith("eq.") else True

    def _filtered(self, params: httpx.QueryParams) -> list[dict[str, Any]]:
        out = list(self.rows)
        for key in ("collection", "id", "room_id", "user_id", "phone"):
            if key in params:
                out = [r for r in out if self._match(r, key, params[key])]
        out.sort(key=lambda r: r.get("seq", 0))
        if "limit" in params:
            out = out[: int(params["limit"])]
        return out

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("apikey") == "sb_secret_test"
        assert request.url.path == "/rest/v1/arp_documents"
        params = request.url.params
        if request.method == "GET":
            return httpx.Response(200, json=[{"doc": r["doc"]} for r in self._filtered(params)])
        if request.method == "POST":
            row = dict(json.loads(request.content))
            self.rows.append(row)
            return httpx.Response(201, json=[row])
        if request.method == "PATCH":
            body = dict(json.loads(request.content))
            changed = []
            for i, row in enumerate(self.rows):
                if self._match(row, "collection", params["collection"]) and self._match(row, "id", params["id"]):
                    body["seq"] = body.get("seq") or time.time_ns()
                    self.rows[i] = body
                    changed.append(body)
            return httpx.Response(200, json=changed)
        if request.method == "DELETE":
            before = len(self.rows)
            self.rows = [r for r in self.rows if not (self._match(r, "collection", params["collection"]) and self._match(r, "id", params["id"]))]
            return httpx.Response(204 if len(self.rows) != before else 200)
        return httpx.Response(500)


def make_store(api: FakeSupabaseApi) -> SupabaseStore:
    return SupabaseStore("https://unit.test", "sb_secret_test", client=httpx.AsyncClient(transport=httpx.MockTransport(api.handler)))


@pytest.mark.asyncio
async def test_supabase_crud_and_filters() -> None:
    api = FakeSupabaseApi()
    store = make_store(api)
    room = {"id": "r1", "name": "Bedroom", "userId": "u1"}
    assert await store.insert("rooms", room) == room
    assert await store.get("rooms", "r1") == room
    await store.insert("rooms", {"id": "r2", "name": "Studio", "userId": "u2"})
    assert [r["id"] for r in await store.list("rooms")] == ["r1", "r2"]
    assert [r["id"] for r in await store.list("rooms", userId="u2")] == ["r2"]
    await store.insert("layouts", {"id": "l1", "roomId": "r1", "name": "Current", "isCurrent": True, "items": [], "zones": []})
    assert [l["id"] for l in await store.list_by_room("layouts", "r1")] == ["l1"]
    updated = await store.update("rooms", "r1", {"name": "Renamed"})
    assert updated and updated["name"] == "Renamed" and updated["userId"] == "u1"
    assert await store.delete("rooms", "r1") is True
    assert await store.delete("rooms", "r1") is False


def test_api_flow_with_supabase(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://unit.test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("ARP_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MOCK_MODE", raising=False)
    settings = Settings.from_env()
    assert settings.supabase_live
    app = create_app(settings)
    app.state.ctx.repo = make_store(FakeSupabaseApi())
    with TestClient(app) as client:
        assert client.get("/health").json()["integrations"]["supabase"] == "supabase"
        created = client.post("/rooms", json={"sample": "nyc-bedroom"}).json()
        room_id, cur = created["room"]["id"], created["currentLayout"]["id"]
        fork = client.post(f"/layouts/{cur}/fork", json={"name": "Supabase variant"})
        assert fork.status_code == 201
        items = fork.json()["items"] + [{"id": "desk_1", "furnitureId": "desk", "x": 2.5, "z": 0.3, "rotation": 0, "locked": False}]
        put = client.put(f"/layouts/{fork.json()['id']}", json={"items": items})
        assert put.status_code == 200 and len(put.json()["layout"]["items"]) == 6
        assert [l["name"] for l in client.get(f"/rooms/{room_id}").json()["layouts"]] == ["Current Room", "Supabase variant"]
    assert not (tmp_path / "db.json").exists()
