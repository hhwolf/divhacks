"""BlobStore against a fake Vercel Blob API (httpx.MockTransport): versioned snapshots, cross-instance visibility, pruning."""

from __future__ import annotations

import json

import httpx
import pytest

from app.repo.blob_store import PREFIX, BlobStore


class FakeBlobApi:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer tok"
        host, path = request.url.host, request.url.path
        if host == "blob.vercel-storage.com":
            if request.method == "GET" and path == "/":
                prefix = request.url.params.get("prefix", "")
                blobs = [{"pathname": p, "url": f"https://store.blob/{p}", "size": len(b)} for p, b in self.blobs.items() if p.startswith(prefix)]
                return httpx.Response(200, json={"blobs": blobs, "hasMore": False})
            if request.method == "PUT":
                pathname = request.url.params["pathname"]
                assert request.headers.get("x-vercel-blob-access") == "private"
                self.blobs[pathname] = request.content
                return httpx.Response(200, json={"url": f"https://store.blob/{pathname}", "pathname": pathname})
            if request.method == "POST" and path == "/delete":
                for url in json.loads(request.content)["urls"]:
                    self.blobs.pop(url.split("https://store.blob/")[1], None)
                return httpx.Response(200, json={})
        if host == "store.blob":
            body = self.blobs.get(path.lstrip("/"))
            return httpx.Response(200, content=body) if body is not None else httpx.Response(404)
        return httpx.Response(500)


def make_store(api: FakeBlobApi) -> BlobStore:
    return BlobStore("tok", client=httpx.AsyncClient(transport=httpx.MockTransport(api.handler)))


@pytest.mark.asyncio
async def test_cross_instance_visibility_and_versioning() -> None:
    api = FakeBlobApi()
    a, b = make_store(api), make_store(api)  # two "function instances"
    await a.insert("rooms", {"id": "r1", "name": "one"})
    assert (await b.get("rooms", "r1")) == {"id": "r1", "name": "one"}
    await b.update("rooms", "r1", {"name": "two"})
    b._synced_at = 0  # noqa: SLF001 - expire a's freshness window to force a re-list
    a._synced_at = 0  # noqa: SLF001
    assert (await a.get("rooms", "r1"))["name"] == "two"
    assert all(p.startswith(PREFIX) for p in api.blobs)


@pytest.mark.asyncio
async def test_prunes_old_snapshots_and_deletes() -> None:
    api = FakeBlobApi()
    s = make_store(api)
    for i in range(8):
        await s.insert("layouts", {"id": f"l{i}", "roomId": "r"})
    assert len(api.blobs) <= 4
    assert await s.delete("layouts", "l3") is True
    assert await s.delete("layouts", "l3") is False
    assert len(await s.list("layouts", roomId="r")) == 7
