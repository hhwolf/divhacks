"""File storage for raw RoomPlan USDZ scans, furniture photos, preset GLBs and thumbnails.

Live (BLOB_READ_WRITE_TOKEN set): the Vercel Blob REST API, as used by @vercel/blob 2.x —
`PUT https://blob.vercel-storage.com/?pathname=<p>` with `x-api-version`, `x-vercel-blob-access`, `x-add-random-suffix: 0`,
`x-content-type`, returning `{url, downloadUrl, pathname, contentType}`; `POST /delete {urls}`. Private blobs are read with the
same bearer token on their URL.
Local (no token): files under `<data_dir>/blob/`, served by the API at `/blob/<pathname>`, so mock mode works offline.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from app.config import BLOB_ACCESS, Settings

log = logging.getLogger(__name__)
BLOB_API = "https://blob.vercel-storage.com"
LOCAL_PREFIX = "/blob/"
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _check(pathname: str) -> str:
    if not _SAFE.match(pathname) or ".." in pathname.split("/"):
        raise ValueError(f"unsafe blob pathname: {pathname!r}")
    return pathname


class BlobStorage(ABC):
    live: bool

    @abstractmethod
    async def put(self, pathname: str, data: bytes, content_type: str, *, overwrite: bool = False) -> str:
        """Store `data` at `pathname`; returns the URL to persist (absolute for Vercel Blob, `/blob/...` locally)."""

    @abstractmethod
    async def get(self, url: str) -> bytes: ...

    @abstractmethod
    async def delete(self, urls: list[str]) -> None: ...


class VercelBlob(BlobStorage):
    live = True

    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._client = client or httpx.AsyncClient(timeout=30.0)

    def _auth(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self._token}"}

    async def put(self, pathname: str, data: bytes, content_type: str, *, overwrite: bool = False) -> str:
        headers = {
            **self._auth(),
            "x-api-version": "12",
            "x-vercel-blob-access": BLOB_ACCESS,
            "x-add-random-suffix": "0",
            "x-content-type": content_type,
        }
        if overwrite:
            headers["x-allow-overwrite"] = "1"
        r = await self._client.put(f"{BLOB_API}/", params={"pathname": _check(pathname)}, content=data, headers=headers)
        r.raise_for_status()
        return str(r.json()["url"])

    async def get(self, url: str) -> bytes:
        r = await self._client.get(url, headers=self._auth())
        r.raise_for_status()
        return r.content

    async def delete(self, urls: list[str]) -> None:
        if urls:
            r = await self._client.post(f"{BLOB_API}/delete", json={"urls": urls}, headers={**self._auth(), "x-api-version": "12"})
            r.raise_for_status()


class LocalBlob(BlobStorage):
    live = False

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, url: str) -> Path:
        if not url.startswith(LOCAL_PREFIX):
            raise ValueError(f"not a local blob url: {url}")
        return self.root / _check(url[len(LOCAL_PREFIX):])

    async def put(self, pathname: str, data: bytes, content_type: str, *, overwrite: bool = False) -> str:
        path = self.root / _check(pathname)
        if path.exists() and not overwrite:
            raise FileExistsError(pathname)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"{LOCAL_PREFIX}{pathname}"

    async def get(self, url: str) -> bytes:
        return self._path(url).read_bytes()

    async def delete(self, urls: list[str]) -> None:
        for url in urls:
            try:
                self._path(url).unlink(missing_ok=True)
            except ValueError:
                log.warning("skipping non-local blob url %s", url)


def make_blob_storage(settings: Settings) -> BlobStorage:
    if settings.blob_live:
        return VercelBlob(Settings.reveal(settings.blob_read_write_token))
    return LocalBlob(settings.data_dir / "blob")
