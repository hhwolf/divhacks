"""Turns an inbound request into (text, furnitureId): a link is imported first, a photo is imported via Gemini vision."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Any

from app.deps import AppContext
from app.imports import URL_RE, fetch_bytes, import_from_link, import_from_photo

DEFAULT_FIT_QUESTION = "Will this fit in my room?"


@dataclass
class RoutedRequest:
    text: str
    furniture_id: str | None
    attachments: list[dict[str, Any]] = field(default_factory=list)  # what was imported, for the agent_requests log


def _decode_data_uri(uri: str) -> tuple[bytes, str]:
    header, _, payload = uri.partition(",")
    mime = header[5:].split(";")[0] or "image/jpeg"
    try:
        return base64.b64decode(payload, validate=True), mime
    except binascii.Error as exc:
        raise ValueError("photo is not valid base64") from exc


async def route(ctx: AppContext, user_id: str, text: str, *, link: str | None = None, photo: str | None = None, furniture_id: str | None = None) -> RoutedRequest:
    """`link` (or a URL inside the text) and `photo` (an https URL or a data: URI) become catalog items before planning."""
    attachments: list[dict[str, Any]] = []
    urls = URL_RE.findall(text or "")
    link = link or (urls[0] if urls else None)
    if urls:
        text = URL_RE.sub("", text).strip()
    if link and furniture_id is None:
        item = await import_from_link(ctx.repo, ctx.gemini, link, user_id)
        furniture_id = item.id
        attachments.append({"type": "link", "url": link, "furnitureId": item.id})
    if photo and furniture_id is None:
        if photo.startswith("data:"):
            data, mime = _decode_data_uri(photo)
            source_url = None
        else:
            data, mime = await fetch_bytes(photo)
            source_url = photo
        item = await import_from_photo(ctx.repo, ctx.gemini, ctx.blob, data, mime if mime.startswith("image/") else "image/jpeg", user_id, source_url=source_url)
        furniture_id = item.id
        attachments.append({"type": "photo", "url": item.photoUrl, "furnitureId": item.id})
    return RoutedRequest(text=text.strip() or DEFAULT_FIT_QUESTION, furniture_id=furniture_id, attachments=attachments)
