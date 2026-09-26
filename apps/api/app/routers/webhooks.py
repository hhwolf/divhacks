"""POST /webhooks/photon: always answers 200 quickly; unknown shapes get a clarifying reply instead of an error."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.agent import pipeline
from app.agent.router import route
from app.deps import AppContext, get_ctx
from app.integrations.photon import normalize_inbound, verify_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)
CLARIFY = "I can help fit furniture into your room. Could you send a listing link or photo, or ask me something like: will this fit beside my window?"
NO_ROOM = "I don't have a room for you yet. Open the app and load or scan a room first, then ask me again."


@router.post("/photon")
async def photon_webhook(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict:
    raw = await request.body()
    if ctx.photon.secret and not verify_signature(ctx.photon.secret, raw, request.headers):
        raise HTTPException(401, "bad signature")
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        body = None
    inbound = normalize_inbound(body)
    if inbound is None:
        return {"ok": True, "reply": CLARIFY, "layoutId": None, "outbound": None}

    user = await ctx.user_by_phone(inbound.sender)
    rooms = await ctx.repo.list("rooms", userId=user.id) or await ctx.repo.list("rooms")
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
        routed = await route(ctx, user.id, inbound.text, inbound.attachments)
        out = await pipeline.run(ctx, request_text=routed.text, user_id=user.id, room_id=room["id"], base_layout_id=base["id"], furniture_id=routed.furniture_id, channel="imessage")
        reply, links, layout_id = out.reply, out.links, out.layout["id"] if out.layout else None
    except Exception as exc:
        log.exception("photon webhook failed: %s", exc)
        reply, links, layout_id = CLARIFY, [], None
    outbound = await ctx.photon.send_text(inbound.sender, reply, links)
    return {"ok": True, "reply": reply, "layoutId": layout_id, "outbound": outbound}
