"""MongoDB (motor) repository; selected when MONGODB_URI is set. `_id` mirrors our `id`; `_seq` (insert time, ns) keeps insertion order."""

from __future__ import annotations

import logging
import time
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorClientSession
from pymongo.errors import OperationFailure

from app.repo.base import Collection, Doc, Op, Repository

log = logging.getLogger(__name__)
_NO_TRANSACTIONS = {20, 263}  # IllegalOperation (standalone mongod), OperationNotSupportedInTransaction


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

    async def ping(self) -> None:
        await self._db.command("ping")

    async def get(self, collection: Collection, doc_id: str) -> Doc | None:
        return self._clean(await self._db[collection].find_one({"_id": doc_id}))

    async def list(self, collection: Collection, **filters: Any) -> list[Doc]:
        cursor = self._db[collection].find(filters).sort("_seq", 1)
        return [self._clean(d) or {} for d in await cursor.to_list(length=None)]

    async def insert(self, collection: Collection, doc: Doc) -> Doc:
        await self._db[collection].insert_one({**doc, "_id": doc["id"], "_seq": time.time_ns()})
        return dict(doc)

    async def update(self, collection: Collection, doc_id: str, patch: Doc) -> Doc | None:
        return await self.update_if(collection, doc_id, {}, patch)

    async def update_if(self, collection: Collection, doc_id: str, expected: Doc, patch: Doc) -> Doc | None:
        res = await self._db[collection].find_one_and_update({**expected, "_id": doc_id}, {"$set": patch}, return_document=True)
        return self._clean(res)

    async def delete(self, collection: Collection, doc_id: str) -> bool:
        res = await self._db[collection].delete_one({"_id": doc_id})
        return res.deleted_count == 1

    async def _run(self, op: Op, session: AsyncIOMotorClientSession | None) -> None:
        kind, coll = op[0], self._db[op[1]]
        if kind == "insert":
            await coll.insert_one({**op[2], "_id": op[2]["id"], "_seq": time.time_ns()}, session=session)
        elif kind == "update":
            res = await coll.update_one({"_id": op[2]}, {"$set": op[3]}, session=session)
            if res.matched_count == 0:
                raise KeyError(f"{op[1]}/{op[2]} not found")
        elif kind == "delete":
            await coll.delete_one({"_id": op[2]}, session=session)
        elif kind == "delete_where":
            await coll.delete_many(op[2], session=session)
        else:
            raise ValueError(f"unknown op {kind}")

    async def apply(self, ops: list[Op]) -> None:
        """A transaction on Atlas (replica set). A standalone mongod (local dev, tests) cannot do transactions: run in order instead."""
        try:
            async with await self._client.start_session() as session:
                async with session.start_transaction():
                    for op in ops:
                        await self._run(op, session)
        except OperationFailure as exc:
            if exc.code not in _NO_TRANSACTIONS:
                raise
            log.warning("mongo transactions unavailable (%s); applying %d ops without one", exc.code, len(ops))
            for op in ops:
                await self._run(op, None)
