"""Classifies an inbound request: link -> import first; image -> photo import; then it becomes a layout request."""

from __future__ import annotations

from dataclasses import dataclass

from app.deps import AppContext
from app.imports import URL_RE, fetch_bytes, import_from_link, import_from_photo
from app.integrations.photon import Attachment

DEFAULT_FIT_QUESTION = "Will this fit in my room?"


@dataclass
class RoutedRequest:
    text: str
    furniture_id: str | None


async def route(ctx: AppContext, user_id: str, text: str, attachments: list[Attachment] | None = None, furniture_id: str | None = None) -> RoutedRequest:
    urls = URL_RE.findall(text or "")
    if urls and furniture_id is None:
        item = await import_from_link(ctx.repo, ctx.gemini, urls[0], user_id)
        furniture_id = item.id
        text = URL_RE.sub("", text).strip() or DEFAULT_FIT_QUESTION
    image = next((a for a in attachments or [] if a.url and ((a.mime_type or "").startswith("image/") or a.url.lower().endswith((".jpg", ".jpeg", ".png", ".heic")))), None)
    if image and furniture_id is None and image.url:
        data, mime = await fetch_bytes(image.url)
        item = await import_from_photo(ctx.repo, ctx.gemini, data, image.mime_type or mime, user_id, source_url=image.url)
        furniture_id = item.id
        text = text.strip() or DEFAULT_FIT_QUESTION
    return RoutedRequest(text=text, furniture_id=furniture_id)
