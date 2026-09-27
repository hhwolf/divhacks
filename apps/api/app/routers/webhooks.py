"""POST /webhooks/photon: always answers 200 quickly; unknown shapes get a clarifying reply instead of an error."""

from __future__ import annotations

import json
import logging
import base64
import binascii
import hashlib
import hmac
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.agent import pipeline
from app.agent.router import route
from app.deps import AppContext, raw_ctx
from app.auth import Principal, resolve_principal
from app.repo.scoped import ScopedRepository
from dataclasses import replace
from app.imports import URL_RE, create_pending_link_item, import_from_link, import_from_photo
from app.integrations.photon import normalize_inbound, verify_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)
CLARIFY = "I can help fit furniture into your room. Could you send a listing link or photo, or ask me something like: will this fit beside my window?"
NO_ROOM = "I don't have a room for you yet. Open the app and load or scan a room first, then ask me again."
FURNITURE_ONLY = "Text me a furniture listing link or photo, then ask if it fits. Use the in-app assistant for room changes like yoga space or reading corners."
RELAY_SKEW_S = 300


class NormalizedAttachment(BaseModel):
    model_config = ConfigDict(extra="allow")
    url: str | None = None
    mimeType: str | None = None
    fileName: str | None = None
    dataBase64: str | None = None


class NormalizedPhotonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messageId: str = Field(min_length=1, max_length=200)
    sender: str = Field(min_length=1, max_length=80)
    text: str = ""
    attachments: list[NormalizedAttachment] = []


def _relay_signature_ok(secret: str, raw: bytes, headers: dict[str, str]) -> bool:
    h = {k.lower(): v for k, v in headers.items()}
    ts = h.get("x-arp-relay-timestamp", "")
    sig = h.get("x-arp-relay-signature", "")
    try:
        if abs(time.time() - float(ts)) > RELAY_SKEW_S:
            return False
    except ValueError:
        return False
    expected = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


async def _ctx_for_sender(ctx: AppContext, sender: str) -> AppContext | None:
    if ctx.photon.live:
        links = await ctx.repo.list("phone_links", phone=sender)
        if not links:
            return None
        principal = Principal(links[0]["userId"], True, sender)
    else:
        principal = Principal("demo_" + hashlib.sha256(b"").hexdigest()[:32], False, ctx.settings.demo_phone)
    return replace(ctx, repo=ScopedRepository(ctx.repo, principal.id), principal=principal)


async def _latest_room_and_current(ctx: AppContext, user_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    rooms = await ctx.repo.list("rooms", userId=user_id)
    if not rooms:
        return None
    room = rooms[-1]
    layouts = await ctx.repo.list_by_room("layouts", room["id"])
    base = next((l for l in layouts if l.get("isCurrent")), layouts[-1] if layouts else None)
    return (room, base) if base else None


def _review_link(ctx: AppContext, layout_id: str, item_id: str) -> str:
    return f"{ctx.settings.public_web_url}/layout/{layout_id}?reviewFurniture={item_id}"


async def _import_from_normalized(ctx: AppContext, user_id: str, body: NormalizedPhotonBody) -> tuple[dict[str, Any], str]:
    urls = URL_RE.findall(body.text or "")
    if urls:
        url = urls[0]
        try:
            item = await import_from_link(ctx.repo, ctx.gemini, url, user_id)
        except Exception:
            item = await create_pending_link_item(ctx.repo, url, user_id)
            return item.model_dump(), "I couldn't read that Marketplace page directly, so I saved it as a pending item. Open the link and confirm the dimensions before testing it in your room."
        return item.model_dump(), "Imported the listing. Confirm the dimensions before testing it in your room."
    image = next((a for a in body.attachments if (a.mimeType or "").startswith("image/") and (a.dataBase64 or a.url)), None)
    if image and image.dataBase64:
        try:
            data = base64.b64decode(image.dataBase64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(422, "Invalid attachment data") from exc
        item = await import_from_photo(ctx.repo, ctx.gemini, data, image.mimeType or "image/jpeg", user_id, source_url=image.url)
        return item.model_dump(), "Imported the screenshot as an estimated item. Confirm the dimensions before testing it in your room."
    raise HTTPException(422, "Send a Facebook Marketplace link or furniture screenshot.")


@router.post("/photon")
async def photon_webhook(request: Request, ctx: AppContext = Depends(raw_ctx)) -> dict:
    raw = await request.body()
    if ctx.photon.live and not ctx.photon.secret:
        raise HTTPException(503, "Real Photon requires signature verification")
    if ctx.photon.secret and not verify_signature(ctx.photon.secret, raw, request.headers):
        raise HTTPException(401, "bad signature")
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        body = None
    inbound = normalize_inbound(body)
    if inbound is None:
        return {"ok": True, "reply": CLARIFY, "layoutId": None, "outbound": None}

    if ctx.photon.live:
        links = await ctx.repo.list("phone_links", phone=inbound.sender)
        if not links:
            return {"ok": True, "reply": NO_ROOM, "layoutId": None, "outbound": None}
        principal = Principal(links[0]["userId"], True, inbound.sender)
    else:
        principal = await resolve_principal(request)
    ctx = replace(ctx, repo=ScopedRepository(ctx.repo, principal.id), principal=principal)
    user = await ctx.demo_user()
    rooms = await ctx.repo.list("rooms", userId=user.id)
    if not rooms:
        outbound = await ctx.photon.send_text(inbound.sender, NO_ROOM, [])
        return {"ok": True, "reply": NO_ROOM, "layoutId": None, "outbound": outbound}
    room = rooms[-1]
    layouts = await ctx.repo.list_by_room("layouts", room["id"])
    base = next((l for l in layouts if l.get("isCurrent")), layouts[-1] if layouts else None)
    if base is None:
        outbound = await ctx.photon.send_text(inbound.sender, NO_ROOM, [])
        return {"ok": True, "reply": NO_ROOM, "layoutId": None, "outbound": outbound}

    try:
        has_furniture_input = bool(URL_RE.search(inbound.text or "")) or any(a.url for a in inbound.attachments)
        if not has_furniture_input:
            reply, links, layout_id = FURNITURE_ONLY, [], None
        else:
            routed = await route(ctx, user.id, inbound.text, inbound.attachments)
            if routed.furniture_id is None:
                reply, links, layout_id = FURNITURE_ONLY, [], None
            else:
                out = await pipeline.run(ctx, request_text=routed.text, user_id=user.id, room_id=room["id"], base_layout_id=base["id"], furniture_id=routed.furniture_id, channel="imessage")
                reply, links, layout_id = out.reply, out.links, out.layout["id"] if out.layout else None
    except Exception as exc:
        log.exception("photon webhook failed: %s", exc)
        reply, links, layout_id = CLARIFY, [], None
    outbound = await ctx.photon.send_text(inbound.sender, reply, links)
    return {"ok": True, "reply": reply, "layoutId": layout_id, "outbound": outbound}


@router.post("/photon/normalized")
async def photon_normalized(request: Request, ctx: AppContext = Depends(raw_ctx)) -> dict:
    raw = await request.body()
    if not ctx.settings.photon_relay_secret:
        raise HTTPException(503, "PHOTON_RELAY_SECRET is required for normalized Photon relay calls")
    if not _relay_signature_ok(ctx.settings.photon_relay_secret, raw, dict(request.headers)):
        raise HTTPException(401, "bad relay signature")
    try:
        body = NormalizedPhotonBody.model_validate_json(raw)
    except ValueError as exc:
        raise HTTPException(422, "Invalid normalized Photon payload") from exc

    existing = await ctx.repo.get("photon_messages", body.messageId)
    if existing:
        return existing["response"]

    scoped = await _ctx_for_sender(ctx, body.sender)
    if scoped is None:
        response = {"ok": True, "reply": NO_ROOM, "itemId": None, "layoutId": None, "links": []}
        await ctx.repo.insert("photon_messages", {"id": body.messageId, "sender": body.sender, "response": response})
        return response

    user = await scoped.demo_user()
    room_base = await _latest_room_and_current(scoped, user.id)
    if room_base is None:
        response = {"ok": True, "reply": NO_ROOM, "itemId": None, "layoutId": None, "links": []}
        await ctx.repo.insert("photon_messages", {"id": body.messageId, "sender": body.sender, "userId": user.id, "response": response})
        return response

    _, base = room_base
    item, import_note = await _import_from_normalized(scoped, user.id, body)
    link = _review_link(ctx, base["id"], item["id"])
    reply = f"{import_note} {link}"
    response = {"ok": True, "reply": reply, "itemId": item["id"], "layoutId": base["id"], "links": [link], "item": item}
    await ctx.repo.insert(
        "photon_messages",
        {"id": body.messageId, "sender": body.sender, "userId": user.id, "itemId": item["id"], "layoutId": base["id"], "response": response},
    )
    return response
