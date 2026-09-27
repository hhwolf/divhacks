"""Request-scoped ownership checks, including paths using the privileged Supabase key."""
from typing import Any

from fastapi import HTTPException

from app.repo.base import Collection, Doc, Repository


class ScopedRepository(Repository):
    def __init__(self, repo: Repository, user_id: str):
        self.inner = repo
        self.user_id = user_id

    async def _owns(self, collection: Collection, doc: Doc) -> bool:
        if doc.get("userId") is not None:
            return doc["userId"] == self.user_id
        # Old layouts/assessments inherited ownership from their room.
        if doc.get("roomId"):
            room = await self.inner.get("rooms", doc["roomId"])
            return bool(room and room.get("userId") == self.user_id)
        return collection == "users" and doc.get("id") == self.user_id

    async def get(self, collection: Collection, doc_id: str) -> Doc | None:
        doc = await self.inner.get(collection, doc_id)
        return doc if doc and await self._owns(collection, doc) else None

    async def list(self, collection: Collection, **filters: Any) -> list[Doc]:
        return [d for d in await self.inner.list(collection, **filters) if await self._owns(collection, d)]

    async def insert(self, collection: Collection, doc: Doc) -> Doc:
        if doc.get("userId") not in (None, self.user_id):
            raise HTTPException(403, "Document owner does not match signed-in user")
        if doc.get("roomId") and not await self.get("rooms", doc["roomId"]):
            raise HTTPException(404, "Room not found")
        if await self.inner.get(collection, doc["id"]):
            raise HTTPException(409, "Document already exists")
        return await self.inner.insert(collection, {**doc, "userId": self.user_id})

    async def update(self, collection: Collection, doc_id: str, patch: Doc) -> Doc | None:
        if not await self.get(collection, doc_id):
            return None
        if any(k in patch for k in ("id", "userId", "roomId")):
            raise HTTPException(403, "Ownership cannot be changed")
        return await self.inner.update(collection, doc_id, patch)

    async def delete(self, collection: Collection, doc_id: str) -> bool:
        return await self.inner.delete(collection, doc_id) if await self.get(collection, doc_id) else False
