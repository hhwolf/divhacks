"""Repository interface shared by the JSON-file store and the Mongo store. Documents are plain dicts with an `id` key."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

Collection = Literal["rooms", "furniture", "layouts", "users", "agent_requests", "rent_assessments", "payment_quotes"]
COLLECTIONS: tuple[Collection, ...] = ("rooms", "furniture", "layouts", "users", "agent_requests", "rent_assessments", "payment_quotes")
Doc = dict[str, Any]
# Batch operations for `apply`: ("insert", coll, doc) | ("update", coll, id, patch) | ("delete", coll, id) | ("delete_where", coll, filters)
Op = tuple[Any, ...]


def matches(doc: Doc, filters: Doc) -> bool:
    return all(doc.get(k) == v for k, v in filters.items())


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
    async def update_if(self, collection: Collection, doc_id: str, expected: Doc, patch: Doc) -> Doc | None:
        """Compare-and-set: merge `patch` only if every `expected` field still matches. None when missing or stale."""

    @abstractmethod
    async def delete(self, collection: Collection, doc_id: str) -> bool: ...

    @abstractmethod
    async def apply(self, ops: list[Op]) -> None:
        """Run every op or none of them (one atomic flush for the JSON store, a transaction on Mongo replica sets)."""

    async def list_by_room(self, collection: Collection, room_id: str) -> list[Doc]:
        return await self.list(collection, roomId=room_id)
