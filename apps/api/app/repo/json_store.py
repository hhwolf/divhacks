"""Single-file JSON repository (`<data_dir>/db.json`) with atomic writes; the default when MONGODB_URI is unset (mock/dev)."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.repo.base import COLLECTIONS, Collection, Doc, Op, Repository, matches


class JsonStore(Repository):
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "db.json"
        self._db: dict[str, list[Doc]] = {c: [] for c in COLLECTIONS}
        if self.path.exists():
            loaded = json.loads(self.path.read_text() or "{}")
            for c in COLLECTIONS:
                self._db[c] = list(loaded.get(c, []))

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix="db.", suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(self._db, fh)
        os.replace(tmp, self.path)

    def _find(self, collection: Collection, doc_id: str) -> Doc | None:
        return next((d for d in self._db[collection] if d["id"] == doc_id), None)

    async def get(self, collection: Collection, doc_id: str) -> Doc | None:
        found = self._find(collection, doc_id)
        return dict(found) if found else None

    async def list(self, collection: Collection, **filters: Any) -> list[Doc]:
        return [dict(d) for d in self._db[collection] if matches(d, filters)]

    async def insert(self, collection: Collection, doc: Doc) -> Doc:
        self._db[collection].append(dict(doc))
        self._flush()
        return dict(doc)

    async def update(self, collection: Collection, doc_id: str, patch: Doc) -> Doc | None:
        return await self.update_if(collection, doc_id, {}, patch)

    async def update_if(self, collection: Collection, doc_id: str, expected: Doc, patch: Doc) -> Doc | None:
        d = self._find(collection, doc_id)
        if d is None or not matches(d, expected):
            return None
        d.update(patch)
        self._flush()
        return dict(d)

    async def delete(self, collection: Collection, doc_id: str) -> bool:
        before = len(self._db[collection])
        self._db[collection] = [d for d in self._db[collection] if d["id"] != doc_id]
        if len(self._db[collection]) == before:
            return False
        self._flush()
        return True

    async def apply(self, ops: list[Op]) -> None:
        staged = copy.deepcopy(self._db)
        for op in ops:
            kind, coll = op[0], op[1]
            if kind == "insert":
                staged[coll].append(dict(op[2]))
            elif kind == "update":
                doc = next((d for d in staged[coll] if d["id"] == op[2]), None)
                if doc is None:
                    raise KeyError(f"{coll}/{op[2]} not found")
                doc.update(op[3])
            elif kind == "delete":
                staged[coll] = [d for d in staged[coll] if d["id"] != op[2]]
            elif kind == "delete_where":
                staged[coll] = [d for d in staged[coll] if not matches(d, op[2])]
            else:
                raise ValueError(f"unknown op {kind}")
        self._db = staged
        self._flush()
