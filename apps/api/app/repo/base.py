"""Repository interface shared by the JSON-file store and the Mongo store. Documents are plain dicts with an `id` key."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

Collection = Literal["rooms", "furniture", "layouts", "users", "agent_requests", "rent_assessments", "payment_quotes"]
COLLECTIONS: tuple[Collection, ...] = ("rooms", "furniture", "layouts", "users", "agent_requests", "rent_assessments", "payment_quotes")
Doc = dict[str, Any]


class Repository(ABC):
    @abstractmethod
    async def get(self, collection: Collection, doc_id: str) -> Doc | None: ...

    @abstractmethod
    async def list(self, collection: Collection, **filters: Any) -> list[Doc]:
        """All documents whose top-level fields equal every filter value, in insertion order."""

    @abstractmethod
    async def insert(self, collection: Collection, doc: Doc) -> Doc: ...

    @abstractmethod
    async def update(self, collection: Collection, doc_id: str, patch: Doc) -> Doc | None:
        """Shallow-merge `patch` into the document; returns the new document or None if missing."""

    @abstractmethod
    async def delete(self, collection: Collection, doc_id: str) -> bool: ...

    async def list_by_room(self, collection: Collection, room_id: str) -> list[Doc]:
        return await self.list(collection, roomId=room_id)
