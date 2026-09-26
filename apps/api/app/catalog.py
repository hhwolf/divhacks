"""Furniture catalog: the preset manifest (assets/furniture/manifest.json) merged with user-imported items from the store."""

from __future__ import annotations

import json

from app.config import REPO_ROOT
from app.models import FurnitureItem
from app.repo.base import Repository

MANIFEST_PATH = REPO_ROOT / "assets" / "furniture" / "manifest.json"
FIXTURES_DIR = REPO_ROOT / "fixtures"


def load_presets() -> dict[str, FurnitureItem]:
    data = json.loads(MANIFEST_PATH.read_text())
    return {m["id"]: FurnitureItem.model_validate(m) for m in data["items"]}


PRESETS = load_presets()


async def all_furniture(repo: Repository) -> dict[str, FurnitureItem]:
    """Presets first, then imported items (an import may shadow a preset id only by accident; ids are generated)."""
    out = dict(PRESETS)
    for doc in await repo.list("furniture"):
        item = FurnitureItem.model_validate(doc)
        out[item.id] = item
    return out
