#!/usr/bin/env python3
"""Upload furniture GLBs, thumbnails and manifest metadata to Supabase.

Apply migrations/003_furniture_assets.sql first. The script needs SUPABASE_URL and
SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY in .env.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.config import Settings  # noqa: E402

DEFAULT_BUCKET = "furniture-assets"
DEFAULT_TABLE = "arp_furniture_assets"
MANIFEST_PATH = ROOT / "assets" / "furniture" / "manifest.json"


@dataclass(frozen=True)
class AssetUpload:
    local_path: Path
    asset_path: str
    furniture_id: str | None
    asset_kind: str
    storage_path: str
    content_type: str
    metadata: dict[str, Any]

    @property
    def byte_size(self) -> int:
        return self.local_path.stat().st_size

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.local_path.read_bytes()).hexdigest()

    def row(self, supabase_url: str, bucket: str) -> dict[str, Any]:
        public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket}/{self.storage_path}"
        return {
            "asset_path": self.asset_path,
            "furniture_id": self.furniture_id,
            "asset_kind": self.asset_kind,
            "storage_bucket": bucket,
            "storage_path": self.storage_path,
            "content_type": self.content_type,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "public_url": public_url,
            "metadata": self.metadata,
            "updated_at": datetime.now(UTC).isoformat(),
        }


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _content_type(path: Path) -> str:
    if path.suffix == ".glb":
        return "model/gltf-binary"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _path_from_manifest_url(url: str) -> Path:
    if not url.startswith("/assets/furniture/"):
        raise ValueError(f"Only bundled furniture assets are supported, got {url!r}")
    path = ROOT / url.lstrip("/")
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def discover_assets(manifest_path: Path = MANIFEST_PATH) -> list[AssetUpload]:
    manifest = json.loads(manifest_path.read_text())
    assets: list[AssetUpload] = [
        AssetUpload(
            local_path=manifest_path,
            asset_path=_rel(manifest_path),
            furniture_id=None,
            asset_kind="manifest",
            storage_path="manifest/manifest.json",
            content_type="application/json",
            metadata={
                "license": manifest.get("license"),
                "units": manifest.get("units"),
                "itemCount": len(manifest.get("items", [])),
            },
        )
    ]
    for item in manifest["items"]:
        furniture_id = item["id"]
        for key, kind, prefix in (("glbUrl", "glb", "glb"), ("thumbUrl", "thumbnail", "thumbs")):
            if key not in item:
                continue
            local_path = _path_from_manifest_url(item[key])
            assets.append(
                AssetUpload(
                    local_path=local_path,
                    asset_path=_rel(local_path),
                    furniture_id=furniture_id,
                    asset_kind=kind,
                    storage_path=f"{prefix}/{local_path.name}",
                    content_type=_content_type(local_path),
                    metadata={
                        "name": item.get("name"),
                        "category": item.get("category"),
                        "kind": item.get("kind"),
                        "dims": item.get("dims"),
                        "source": item.get("source"),
                    },
                )
            )
    return assets


def _headers(key: str, content_type: str = "application/json") -> dict[str, str]:
    return {"apikey": key, "authorization": f"Bearer {key}", "content-type": content_type}


def ensure_bucket(client: httpx.Client, url: str, key: str, bucket: str) -> None:
    response = client.post(
        f"{url}/storage/v1/bucket",
        headers=_headers(key),
        json={
            "id": bucket,
            "name": bucket,
            "public": True,
            "file_size_limit": 20 * 1024 * 1024,
            "allowed_mime_types": ["model/gltf-binary", "image/png", "application/json"],
        },
    )
    if response.status_code not in {200, 201, 409}:
        response.raise_for_status()


def upload_asset(client: httpx.Client, url: str, key: str, bucket: str, asset: AssetUpload) -> None:
    response = client.post(
        f"{url}/storage/v1/object/{bucket}/{asset.storage_path}",
        headers={**_headers(key, asset.content_type), "x-upsert": "true"},
        content=asset.local_path.read_bytes(),
    )
    response.raise_for_status()


def upsert_rows(client: httpx.Client, url: str, key: str, table: str, rows: list[dict[str, Any]]) -> None:
    response = client.post(
        f"{url}/rest/v1/{table}",
        params={"on_conflict": "asset_path"},
        headers={**_headers(key), "prefer": "resolution=merge-duplicates,return=minimal"},
        json=rows,
    )
    response.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload bundled furniture assets to Supabase Storage and metadata table.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be uploaded without touching Supabase.")
    parser.add_argument("--bucket", default=os.environ.get("SUPABASE_FURNITURE_BUCKET", DEFAULT_BUCKET), help=f"Storage bucket name, default {DEFAULT_BUCKET}.")
    parser.add_argument("--table", default=os.environ.get("SUPABASE_FURNITURE_ASSETS_TABLE", DEFAULT_TABLE), help=f"Metadata table name, default {DEFAULT_TABLE}.")
    args = parser.parse_args()

    settings = Settings.from_env()
    assets = discover_assets()
    print(f"discovered {len(assets)} assets: {sum(a.asset_kind == 'glb' for a in assets)} glb, {sum(a.asset_kind == 'thumbnail' for a in assets)} thumbnails, 1 manifest")
    if args.dry_run:
        for asset in assets:
            print(f"{asset.asset_kind:9} {asset.asset_path} -> {args.bucket}/{asset.storage_path} ({asset.byte_size} bytes)")
        return 0
    if not settings.supabase_url or not settings.supabase_secret_key:
        print("SUPABASE_URL and SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY are required.", file=sys.stderr)
        return 2

    with httpx.Client(timeout=30.0) as client:
        ensure_bucket(client, settings.supabase_url, settings.supabase_secret_key, args.bucket)
        for asset in assets:
            upload_asset(client, settings.supabase_url, settings.supabase_secret_key, args.bucket, asset)
        upsert_rows(client, settings.supabase_url, settings.supabase_secret_key, args.table, [a.row(settings.supabase_url, args.bucket) for a in assets])
    print(f"uploaded {len(assets)} assets to bucket {args.bucket} and table {args.table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
