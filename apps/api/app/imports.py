"""Furniture import helpers shared by the /furniture routes and the agent router: fetch a listing, parse it, ask Gemini, store."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.catalog import FIXTURES_DIR, PRESETS
from app.safe_fetch import fetch_public
from app.integrations.gemini import GeminiAdapter
from app.models import FurnitureItem, FurnitureKind, FurnitureSource
from app.repo.base import Repository

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "testserver"}
URL_RE = re.compile(r"https?://[^\s<>\"']+")
_NUM = r"(\d+(?:\.\d+)?)"
_IN = r"\s*(?:in\.?|inches|\"|″|”)?\s*(?:[WDH]\b)?\s*"
IMPERIAL_RE = re.compile(_NUM + _IN + r"[x×]" + r"\s*" + _NUM + _IN + r"[x×]" + r"\s*" + _NUM + r"\s*(?:in\.?|inches|\"|″|”)\s*(?:[WDH]\b)?", re.I)
METRIC_RE = re.compile(_NUM + r"\s*(?:cm)?\s*[x×]\s*" + _NUM + r"\s*(?:cm)?\s*[x×]\s*" + _NUM + r"\s*cm", re.I)
PRICE_RE = re.compile(r"\$\s?(\d+(?:\.\d{2})?)")
KIND_WORDS: list[tuple[str, FurnitureKind]] = [
    ("bed", "bed"), ("desk", "desk"), ("wardrobe", "wardrobe"), ("armoire", "wardrobe"), ("dresser", "dresser"), ("chest", "dresser"),
    ("shelf", "storage"), ("bookcase", "storage"), ("cabinet", "storage"), ("nightstand", "storage"), ("fridge", "storage"),
    ("chair", "seating"), ("sofa", "seating"), ("couch", "seating"), ("stool", "seating"), ("bench", "seating"),
    ("table", "table"), ("rug", "floor"), ("mat", "floor"), ("lamp", "decor"), ("plant", "decor"),
]
CATEGORY_KIND: dict[str, FurnitureKind] = {"bed": "bed", "desk": "desk", "seating": "seating", "storage": "storage", "table": "table", "decor": "decor"}


def local_fixture_path(url: str) -> Path | None:
    """fixtures/listings/* served by this API resolve to the file so the demo works offline (and under TestClient)."""
    u = urlparse(url)
    if u.hostname in LOCAL_HOSTS and u.path.startswith("/fixtures/listings/"):
        name = u.path.rsplit("/", 1)[-1]
        if name not in {"desk", "desk.html", "desk.jpg"}:
            return None
        path = FIXTURES_DIR / "listings" / (name if "." in name else f"{name}.html")
        return path if path.exists() else None
    return None


async def fetch_bytes(url: str) -> tuple[bytes, str]:
    local = local_fixture_path(url)
    if local is not None:
        mime = "text/html" if local.suffix == ".html" else "image/jpeg" if local.suffix in (".jpg", ".jpeg") else "application/octet-stream"
        return local.read_bytes(), mime
    return await fetch_public(url)


def parse_dims(text: str) -> dict[str, float] | None:
    if m := IMPERIAL_RE.search(text):
        w, d, h = (round(float(v) * 0.0254, 3) for v in m.groups())
        return {"w": w, "d": d, "h": h}
    if m := METRIC_RE.search(text):
        w, d, h = (round(float(v) / 100, 3) for v in m.groups())
        return {"w": w, "d": d, "h": h}
    return None


def parse_listing(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    meta: dict[str, Any] = {"title": soup.title.string.strip() if soup.title and soup.title.string else None}
    for tag in soup.find_all("meta"):
        prop = tag.get("property") or tag.get("name")
        if prop and tag.get("content"):
            meta[prop] = tag["content"]
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and node.get("@type") == "Product":
                meta["jsonld"] = node
    text = soup.get_text(" ", strip=True)
    price = (meta.get("jsonld") or {}).get("offers", {}).get("price") or meta.get("product:price:amount")
    if price is None and (m := PRICE_RE.search(text)):
        price = m.group(1)
    meta["price"] = float(price) if price not in (None, "") else None
    meta["dims"] = parse_dims(text) or parse_dims(meta.get("og:description") or "")
    meta["color"] = (meta.get("jsonld") or {}).get("color")
    meta["text"] = text[:6000]
    return meta


def kind_for(category: str | None, name: str) -> FurnitureKind:
    lower = name.lower()
    for word, kind in KIND_WORDS:
        if word in lower:
            return kind
    return CATEGORY_KIND.get(category or "", "decor")


def _preset_for_kind(kind: FurnitureKind, name: str) -> FurnitureItem | None:
    lower = name.lower()
    for p in PRESETS.values():
        if p.kind == kind and any(w in lower for w in p.name.lower().split()):
            return p
    return next((p for p in PRESETS.values() if p.kind == kind), None)


def build_item(listing: dict[str, Any], *, user_id: str, source: FurnitureSource, source_url: str | None) -> FurnitureItem:
    name = str(listing.get("name") or "Imported item")
    kind = kind_for(listing.get("category"), name)
    preset = _preset_for_kind(kind, name)
    dims = listing.get("dims") or {"w": 0.5, "d": 0.5, "h": 0.5}
    return FurnitureItem(
        id=f"imp_{uuid.uuid4().hex[:8]}",
        userId=user_id,
        name=name,
        category="imported",
        kind=kind,
        dims=dims,
        glbUrl=preset.glbUrl if preset else None,
        thumbUrl=preset.thumbUrl if preset else None,
        source=source,
        sourceUrl=source_url,
        price=listing.get("price"),
        color=listing.get("color"),
        estimated=bool(listing.get("estimated", False)),
    )


async def import_from_link(repo: Repository, gemini: GeminiAdapter, url: str, user_id: str) -> FurnitureItem:
    raw, _ = await fetch_bytes(url)
    meta = parse_listing(raw.decode("utf-8", errors="replace"))
    listing = await gemini.extract_listing(meta.pop("text"), meta)
    if listing.get("price") is None:
        listing["price"] = meta.get("price")
    item = build_item(listing, user_id=user_id, source="link", source_url=url)
    await repo.insert("furniture", {**item.model_dump(), "createdAt": datetime.now(UTC).isoformat()})
    return item


async def import_from_photo(repo: Repository, gemini: GeminiAdapter, data: bytes, mime: str, user_id: str, source_url: str | None = None) -> FurnitureItem:
    listing = await gemini.estimate_from_photo(data, mime)
    listing["estimated"] = True
    item = build_item(listing, user_id=user_id, source="photo", source_url=source_url)
    await repo.insert("furniture", {**item.model_dump(), "createdAt": datetime.now(UTC).isoformat()})
    return item
