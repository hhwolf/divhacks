"""MongoDB (motor) repository; selected when MONGODB_URI is set. `_id` mirrors our `id`; `_seq` (insert time, ns) keeps insertion order."""

from __future__ import annotations

import time
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from app.repo.base import Collection, Doc, Repository


class MongoStore(Repository):
    def __init__(self, uri: str, db_name: str) -> None:
        self._client: AsyncIOMotorClient[Doc] = AsyncIOMotorClient(uri)
        self._db = self._client[db_name]

    @staticmethod
    def _clean(doc: Doc | None) -> Doc | None:
        if doc is None:
            return None
        doc.pop("_id", None)
        doc.pop("_seq", None)
        return doc

    async def get(self, collection: Collection, doc_id: str) -> Doc | None:
        return self._clean(await self._db[collection].find_one({"_id": doc_id}))

    async def list(self, collection: Collection, **filters: Any) -> list[Doc]:
        cursor = self._db[collection].find(filters).sort("_seq", 1)
        return [self._clean(d) or {} for d in await cursor.to_list(length=None)]

    async def insert(self, collection: Collection, doc: Doc) -> Doc:
        await self._db[collection].insert_one({**doc, "_id": doc["id"], "_seq": time.time_ns()})
        return dict(doc)

    async def update(self, collection: Collection, doc_id: str, patch: Doc) -> Doc | None:
        res = await self._db[collection].find_one_and_update({"_id": doc_id}, {"$set": patch}, return_document=True)
        return self._clean(res)

    async def delete(self, collection: Collection, doc_id: str) -> bool:
        res = await self._db[collection].delete_one({"_id": doc_id})
        return res.deleted_count == 1
