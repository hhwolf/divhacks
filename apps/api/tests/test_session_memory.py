import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.auth import Principal
from app.repo.scoped import ScopedRepository


def test_session_memory_and_assistant_survive_later_requests(client):
    headers = {"X-Demo-Session": "memory-session-a-" + "a" * 32}
    owner = client.get("/session", headers=headers).json()["userId"]
    assert client.post("/rooms", json={"sample": "nyc-bedroom"}, headers=headers).status_code == 201
    ctx = client.app.state.ctx
    asyncio.run(ctx.backboard.add_memories(owner, ["Do not move the bed"]))
    assert asyncio.run(ctx.backboard.get_context(owner)) == ["Do not move the bed"]

    ctx.backboard._client = SimpleNamespace(create_assistant=AsyncMock(return_value=SimpleNamespace(assistant_id="assistant_fixture")))
    assert asyncio.run(ctx.backboard._assistant_id(owner)) == "assistant_fixture"
    assert client.post("/rooms", json={"sample": "studio"}, headers=headers).status_code == 201
    assert asyncio.run(ctx.backboard._assistant_id(owner)) == "assistant_fixture"
    assert ctx.backboard._client.create_assistant.await_count == 1
    saved = asyncio.run(ctx.repo.get("users", owner))
    assert saved["userId"] == owner and saved["memories"] == ["Do not move the bed"]

    other_headers = {"X-Demo-Session": "memory-session-b-" + "b" * 32}
    other = client.get("/session", headers=other_headers).json()["userId"]
    assert client.post("/rooms", json={"sample": "studio"}, headers=other_headers).status_code == 201
    assert asyncio.run(ctx.backboard.get_context(other)) == []


@pytest.mark.parametrize("store_conflict", [False, True])
def test_user_creation_conflict_preserves_winning_record(client, store_conflict):
    raw = client.app.state.ctx
    principal = Principal("verified-user", True)
    repo = ScopedRepository(raw.repo, principal.id)
    ctx = replace(raw, repo=repo, principal=principal)
    insert = repo.insert

    async def raced_insert(collection, doc):
        await insert(collection, {**doc, "memories": ["Keep the dresser"], "backboardAssistantId": "existing-assistant"})
        if store_conflict:
            response = httpx.Response(409, request=httpx.Request("POST", "https://storage.example.test"))
            response.raise_for_status()
        raise HTTPException(409, "Document already exists")

    repo.insert = raced_insert
    user = asyncio.run(ctx.demo_user())
    assert user.id == principal.id
    assert user.memories == ["Keep the dresser"]
    assert user.backboardAssistantId == "existing-assistant"
