"""Supabase-backed repository using the Data REST API.

Expected table (default `arp_documents`):

    create table if not exists public.arp_documents (
      collection text not null,
      id text not null,
      room_id text,
      user_id text,
      phone text,
      doc jsonb not null,
      seq bigint not null,
      primary key (collection, id)
    );
    create index if not exists arp_documents_collection_seq_idx on public.arp_documents (collection, seq);
    create index if not exists arp_documents_room_idx on public.arp_documents (collection, room_id);
    create index if not exists arp_documents_phone_idx on public.arp_documents (collection, phone);
    grant select, insert, update, delete on public.arp_documents to service_role;

The FastAPI server uses a server-only Supabase secret/service key. Never expose that key to the browser.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.repo.base import Collection, Doc, Repository


class SupabaseStore(Repository):
    def __init__(self, url: str, key: str, table: str = "arp_documents", client: httpx.AsyncClient | None = None) -> None:
        self._base = url.rstrip("/").removesuffix("/rest/v1") + "/rest/v1"
        self._key = key
        self._table = table
        self._client = client or httpx.AsyncClient(timeout=15.0)

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {"apikey": self._key, "content-type": "application/json"}
        if self._key.startswith("eyJ"):
            headers["authorization"] = f"Bearer {self._key}"
        if prefer:
            headers["prefer"] = prefer
        return headers

    def _url(self) -> str:
        return f"{self._base}/{self._table}"

    @staticmethod
    def _row(collection: Collection, doc: Doc) -> dict[str, Any]:
        return {
            "collection": collection,
            "id": doc["id"],
            "room_id": doc.get("roomId"),
            "user_id": doc.get("userId"),
            "phone": doc.get("phone"),
            "doc": dict(doc),
            "seq": time.time_ns(),
        }

    @staticmethod
    def _doc(row: dict[str, Any] | None) -> Doc | None:
        if row is None:
            return None
        return dict(row.get("doc") or {})

    @staticmethod
    def _params(collection: Collection, **filters: Any) -> dict[str, str]:
        params = {"collection": f"eq.{collection}", "select": "doc", "order": "seq.asc"}
        mapped = {"id": "id", "roomId": "room_id", "userId": "user_id", "phone": "phone"}
        for key, value in filters.items():
            col = mapped.get(key)
            if col:
                params[col] = f"eq.{value}"
        return params

    @staticmethod
    def _local_match(doc: Doc, filters: dict[str, Any]) -> bool:
        return all(doc.get(k) == v for k, v in filters.items())

    async def get(self, collection: Collection, doc_id: str) -> Doc | None:
        r = await self._client.get(self._url(), params=self._params(collection, id=doc_id) | {"limit": "1"}, headers=self._headers())
        r.raise_for_status()
        rows = r.json()
        return self._doc(rows[0]) if rows else None

    async def list(self, collection: Collection, **filters: Any) -> list[Doc]:
        r = await self._client.get(self._url(), params=self._params(collection, **filters), headers=self._headers())
        r.raise_for_status()
        docs = [self._doc(row) or {} for row in r.json()]
        return [d for d in docs if self._local_match(d, filters)]

    async def insert(self, collection: Collection, doc: Doc) -> Doc:
        r = await self._client.post(self._url(), json=self._row(collection, doc), headers=self._headers("return=representation"))
        r.raise_for_status()
        return dict(doc)

    async def update(self, collection: Collection, doc_id: str, patch: Doc) -> Doc | None:
        cur = await self.get(collection, doc_id)
        if cur is None:
            return None
        updated = {**cur, **patch}
        r = await self._client.patch(
            self._url(),
            params={"collection": f"eq.{collection}", "id": f"eq.{doc_id}"},
            json=self._row(collection, updated),
            headers=self._headers("return=representation"),
        )
        r.raise_for_status()
        return updated

    async def delete(self, collection: Collection, doc_id: str) -> bool:
        before = await self.get(collection, doc_id)
        if before is None:
            return False
        r = await self._client.delete(self._url(), params={"collection": f"eq.{collection}", "id": f"eq.{doc_id}"}, headers=self._headers())
        r.raise_for_status()
        return True
