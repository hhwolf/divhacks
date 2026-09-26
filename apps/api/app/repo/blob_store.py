"""Vercel Blob-backed repository for the serverless deploy (shared across function instances).

Same single-document-set semantics as JsonStore, persisted as immutable versioned snapshots `db/<ts>-<rand>.json`.
Every operation first asks the Blob *list API* (never CDN-cached) for the newest snapshot and reloads it if it is newer
than what this instance holds, so a room created by one instance is visible to the next request on another instance.
Mutations upload a new snapshot and prune old ones (keeping the last few). Selected when BLOB_READ_WRITE_TOKEN is set and
MONGODB_URI is not.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from app.repo.base import COLLECTIONS, Collection, Doc, Repository

BLOB_API = "https://blob.vercel-storage.com"
PREFIX = "db-"
KEEP = 4
FRESH_SECONDS = 0.25


class BlobStore(Repository):
    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._db: dict[str, list[Doc]] = {c: [] for c in COLLECTIONS}
        self._loaded_path: str | None = None
        self._latest_ms = 0  # newest snapshot version seen; uploads are strictly monotonic even within one millisecond
        self._synced_at = 0.0

    # -- transport -------------------------------------------------------------------------------------------------
    def _headers(self, **extra: str) -> dict[str, str]:
        return {"authorization": f"Bearer {self._token}", "x-api-version": "12", "x-vercel-blob-access": "private", **extra}

    @staticmethod
    def _version(pathname: str) -> int:
        try:
            return int(pathname[len(PREFIX):].split("-")[0])
        except ValueError:
            return 0

    async def _list(self) -> list[dict[str, Any]]:
        r = await self._client.get(f"{BLOB_API}/", params={"prefix": PREFIX, "limit": "1000"}, headers=self._headers())
        r.raise_for_status()
        return list(r.json().get("blobs", []))

    async def _download(self, blob: dict[str, Any]) -> dict[str, list[Doc]]:
        r = await self._client.get(blob["url"], headers={"authorization": f"Bearer {self._token}"})
        r.raise_for_status()
        return r.json()

    async def _upload(self, payload: dict[str, list[Doc]]) -> str:
        self._latest_ms = max(int(time.time() * 1000), self._latest_ms + 1)
        pathname = f"{PREFIX}{self._latest_ms:013d}-{uuid.uuid4().hex[:6]}.json"
        r = await self._client.put(
            f"{BLOB_API}/",
            params={"pathname": pathname},  # the Blob API takes the pathname as a query parameter, like @vercel/blob's put()
            content=json.dumps(payload).encode(),
            headers=self._headers(**{"x-add-random-suffix": "0", "x-content-type": "application/json", "x-cache-control-max-age": "60"}),
        )
        r.raise_for_status()
        return pathname

    async def _delete(self, urls: list[str]) -> None:
        if urls:
            await self._client.post(f"{BLOB_API}/delete", json={"urls": urls}, headers=self._headers())

    # -- sync ------------------------------------------------------------------------------------------------------
    async def _sync(self, force: bool = False) -> None:
        if not force and time.monotonic() - self._synced_at < FRESH_SECONDS:
            return
        blobs = sorted(await self._list(), key=lambda b: b["pathname"])
        self._synced_at = time.monotonic()
        if not blobs:
            return
        newest = blobs[-1]
        self._latest_ms = max(self._latest_ms, self._version(newest["pathname"]))
        if newest["pathname"] != self._loaded_path:
            loaded = await self._download(newest)
            self._db = {c: list(loaded.get(c, [])) for c in COLLECTIONS}
            self._loaded_path = newest["pathname"]

    async def _flush(self) -> None:
        self._loaded_path = await self._upload(self._db)
        self._synced_at = time.monotonic()
        blobs = sorted(await self._list(), key=lambda b: b["pathname"])
        stale = [b["url"] for b in blobs[:-KEEP] if b["pathname"] != self._loaded_path]
        await self._delete(stale)

    # -- Repository ------------------------------------------------------------------------------------------------
    async def get(self, collection: Collection, doc_id: str) -> Doc | None:
        await self._sync()
        return next((dict(d) for d in self._db[collection] if d["id"] == doc_id), None)

    async def list(self, collection: Collection, **filters: Any) -> list[Doc]:
        await self._sync()
        return [dict(d) for d in self._db[collection] if all(d.get(k) == v for k, v in filters.items())]

    async def insert(self, collection: Collection, doc: Doc) -> Doc:
        await self._sync(force=True)
        self._db[collection].append(dict(doc))
        await self._flush()
        return dict(doc)

    async def update(self, collection: Collection, doc_id: str, patch: Doc) -> Doc | None:
        await self._sync(force=True)
        for d in self._db[collection]:
            if d["id"] == doc_id:
                d.update(patch)
                await self._flush()
                return dict(d)
        return None

    async def delete(self, collection: Collection, doc_id: str) -> bool:
        await self._sync(force=True)
        before = len(self._db[collection])
        self._db[collection] = [d for d in self._db[collection] if d["id"] != doc_id]
        if len(self._db[collection]) == before:
            return False
        await self._flush()
        return True
