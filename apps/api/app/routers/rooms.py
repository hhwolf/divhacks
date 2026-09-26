from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import AppContext, get_ctx
from app.models import Dimensions, Door, RoomSkeleton, Window
from app.services import SAMPLES, create_room, load_sample, skeleton_from_dimensions

router = APIRouter(prefix="/rooms", tags=["rooms"])


class CreateRoomBody(BaseModel):
    """One of: {sample}, {skeleton, objects, name} (RoomPlan export), {dimensions, doors, windows, name} (manual)."""

    sample: Literal["nyc-bedroom", "studio"] | None = None
    skeleton: RoomSkeleton | None = None
    objects: list[dict[str, Any]] = []
    dimensions: Dimensions | None = None
    doors: list[Door] = []
    windows: list[Window] = []
    name: str | None = None


@router.post("", status_code=201)
async def post_room(body: CreateRoomBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    if body.sample:
        data = load_sample(body.sample)
        skeleton, objects, name, source = RoomSkeleton.model_validate(data["skeleton"]), data["objects"], body.name or data["name"], "sample"
    elif body.skeleton is not None:
        skeleton, objects, name, source = body.skeleton, body.objects, body.name or "Scanned room", "scan"
    elif body.dimensions is not None:
        skeleton, objects, name, source = skeleton_from_dimensions(body.dimensions, body.doors, body.windows), body.objects, body.name or "My room", "manual"
    else:
        raise HTTPException(422, f"Provide 'sample' ({', '.join(SAMPLES)}), 'skeleton' or 'dimensions'")
    room, layout = await create_room(ctx, name=name, skeleton=skeleton, source=source, objects=objects, user_id=user.id)
    return {"room": room.model_dump(), "currentLayout": layout.model_dump(), "layouts": [layout.model_dump()]}


@router.get("")
async def list_rooms(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    return await ctx.repo.list("rooms")


@router.get("/{room_id}")
async def get_room(room_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    room = await ctx.repo.get("rooms", room_id)
    if room is None:
        raise HTTPException(404, "room not found")
    return {"room": room, "layouts": await ctx.repo.list_by_room("layouts", room_id)}
