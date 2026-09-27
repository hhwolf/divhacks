from fastapi import APIRouter, Depends, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from app.agent import pipeline
from app.agent.router import route
from app.deps import AppContext, get_ctx
from app.imports import BLOCKED_HINT, ListingBlocked
from app.models import Channel, Layout, Room

router = APIRouter(prefix="/agent", tags=["agent"])
NO_ROOM = "I don't have a room for you yet. Open the app and scan your room (or load the sample), then ask me again."


class AgentRequestBody(BaseModel):
    """From the app, or from the Photon agent relaying an iMessage (text, a listing link and/or a photo URL; no ids needed)."""

    text: str = Field(min_length=1, max_length=2000)
    roomId: str | None = Field(default=None, description="omit to use the user's most recently used room")
    layoutId: str | None = Field(default=None, validation_alias=AliasChoices("layoutId", "baseLayoutId"), description="source layout; default: that room's Current Room")
    furnitureId: str | None = None
    link: str | None = Field(default=None, description="listing URL to import first")
    photo: str | None = Field(default=None, validation_alias=AliasChoices("photo", "imageUrl"), description="https URL or data: URI of a photo")
    channel: Channel = "app"


async def _resolve(ctx: AppContext, body: AgentRequestBody, user_id: str) -> tuple[Room, Layout] | None:
    if body.roomId is None:
        if body.layoutId is not None:
            doc = await ctx.repo.get("layouts", body.layoutId)
            if doc is None:
                raise HTTPException(404, "layout not found")
            body.roomId = doc["roomId"]
        else:
            rooms = await ctx.repo.list("rooms", userId=user_id)
            if not rooms:
                return None
            body.roomId = max(rooms, key=lambda r: r.get("updatedAt") or r.get("createdAt") or "")["id"]
    room_doc = await ctx.repo.get("rooms", body.roomId)
    if room_doc is None:
        raise HTTPException(404, "room not found")
    room = Room.model_validate(room_doc)
    layout_id = body.layoutId or room.currentLayoutId or next((l["id"] for l in await ctx.repo.list_by_room("layouts", room.id) if l.get("isCurrent")), None)
    layout_doc = await ctx.repo.get("layouts", layout_id) if layout_id else None
    if layout_doc is None:
        raise HTTPException(404, "layout not found")
    source = Layout.model_validate(layout_doc)
    if source.roomId != room.id:
        raise HTTPException(422, "layoutId does not belong to roomId")
    return room, source


@router.post("/request", summary="Interior Designer: Gemini orchestrates -> solver / ranker / rent / payment tools -> named variants")
async def agent_request(body: AgentRequestBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    resolved = await _resolve(ctx, body, user.id)
    if resolved is None:
        return {"status": "clarify", "reply": NO_ROOM, "plan": None, "layoutId": None, "layout": None, "options": [], "links": [], "requestId": None, "violations": [], "ranking": []}
    room, source = resolved
    try:
        routed = await route(ctx, user.id, body.text, link=body.link, photo=body.photo, furniture_id=body.furnitureId)
    except ListingBlocked as exc:
        raise HTTPException(422, {"message": BLOCKED_HINT, "reason": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    out = await pipeline.run(
        ctx, request_text=routed.text, user_id=user.id, room=room, source=source, furniture_id=routed.furniture_id,
        attachments=routed.attachments, channel=body.channel,
    )
    return {
        "status": out.status,
        "reply": out.reply,
        "roomId": room.id,
        "sourceLayoutId": source.id,
        "plan": out.plan.model_dump(exclude_none=True) if out.plan else None,
        "options": [o.model_dump() for o in out.options],
        "recommended": out.recommended,
        "roomSummary": out.room_summary,
        "layoutId": out.layout["id"] if out.layout else None,
        "layout": out.layout,
        "links": out.links,
        "requestId": out.request_id,
        "violations": [v.model_dump() for v in out.violations],
        "ranking": [r.model_dump() for r in out.ranking],
        **out.extra,
    }
