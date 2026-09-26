"""Single-file JSON repository (`<data_dir>/db.json`) with atomic writes; the default when shared storage is unset."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.repo.base import COLLECTIONS, Collection, Doc, Repository


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

    async def get(self, collection: Collection, doc_id: str) -> Doc | None:
        return next((dict(d) for d in self._db[collection] if d["id"] == doc_id), None)

    async def list(self, collection: Collection, **filters: Any) -> list[Doc]:
        return [dict(d) for d in self._db[collection] if all(d.get(k) == v for k, v in filters.items())]

    async def insert(self, collection: Collection, doc: Doc) -> Doc:
        self._db[collection].append(dict(doc))
        self._flush()
        return dict(doc)

    async def update(self, collection: Collection, doc_id: str, patch: Doc) -> Doc | None:
        for d in self._db[collection]:
            if d["id"] == doc_id:
                d.update(patch)
                self._flush()
                return dict(d)
        return None

    async def delete(self, collection: Collection, doc_id: str) -> bool:
        before = len(self._db[collection])
        self._db[collection] = [d for d in self._db[collection] if d["id"] != doc_id]
        if len(self._db[collection]) == before:
            return False
        self._flush()
        return True
