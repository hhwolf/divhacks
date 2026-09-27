"""Seed the preset furniture catalog: upload the low-poly GLBs + thumbnails to Vercel Blob and upsert ownerless preset docs into MongoDB.

    cd apps/api && ../../.venv/bin/python seed_presets.py            # the nine core presets
    cd apps/api && ../../.venv/bin/python seed_presets.py --all      # every item in assets/furniture/manifest.json
    cd apps/api && ../../.venv/bin/python seed_presets.py --dry-run  # print what would be written

Needs MONGODB_URI and BLOB_READ_WRITE_TOKEN (from the environment or the repo's .env). Idempotent: uploads overwrite
`presets/<id>.glb` and docs are replaced by id. Seeded docs override the bundled manifest entry with the same id (GET /furniture).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from app.catalog import MANIFEST_PATH, PRESETS
from app.config import MONGODB_DB, REPO_ROOT, Settings
from app.repo.mongo_store import MongoStore
from app.services.blob import VercelBlob

# twin bed, full bed, desk, chair, dresser, nightstand, bookshelf, rug, yoga mat
CORE = ("bed_single", "bed_double", "desk", "chair", "dresser", "nightstand", "bookshelf", "rug", "yoga_mat")


async def seed(ids: list[str], dry_run: bool) -> int:
    settings = Settings.from_env()
    if not dry_run and not (settings.mongo_live and settings.blob_live):
        print("MONGODB_URI and BLOB_READ_WRITE_TOKEN must both be set (or use --dry-run).", file=sys.stderr)
        return 2
    repo = None if dry_run else MongoStore(Settings.reveal(settings.mongodb_uri), MONGODB_DB)
    blob = None if dry_run else VercelBlob(Settings.reveal(settings.blob_read_write_token))
    for pid in ids:
        preset = PRESETS[pid]
        doc = {**preset.model_dump(), "userId": None, "source": "preset", "createdAt": datetime.now(UTC).isoformat()}
        for field, name, mime in (("glbUrl", f"presets/{pid}.glb", "model/gltf-binary"), ("thumbUrl", f"presets/thumbs/{pid}.png", "image/png")):
            local = getattr(preset, field)
            if not local:
                continue
            path = REPO_ROOT / local.lstrip("/")
            if blob is not None:
                doc[field] = await blob.put(name, path.read_bytes(), mime, overwrite=True)
            else:
                doc[field] = f"<blob>/{name}"
        if repo is not None:
            await repo.apply([("delete", "furniture", pid), ("insert", "furniture", doc)])
        print(f"{pid:<14} {preset.name:<20} {doc['glbUrl']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help=f"seed every item in {MANIFEST_PATH.name}, not just the core nine")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return asyncio.run(seed(list(PRESETS) if args.all else list(CORE), args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
