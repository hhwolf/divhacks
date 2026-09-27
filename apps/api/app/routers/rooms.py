from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import AppContext, get_ctx
from app.models import Dimensions, Door, RoomElement, RoomSkeleton, Window
from app.setup import ELEMENTS, SPACE_TYPES, suggest_elements
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
    seed: bool = True  # False → clean base room: objects are kept as room.detectedObjects, Current Room starts empty
    spaceTypes: list[str] = []
    elements: list[RoomElement] = []


@router.post("", status_code=201)
async def post_room(body: CreateRoomBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    space_types, elements = body.spaceTypes, body.elements
    if body.sample:
        data = load_sample(body.sample)
        skeleton, objects, name, source = RoomSkeleton.model_validate(data["skeleton"]), data["objects"], body.name or data["name"], "sample"
        if not space_types:
            space_types = data.get("spaceTypes", [])
        if not elements:
            elements = [RoomElement.model_validate(e) for e in data.get("elements", [])]
    elif body.skeleton is not None:
        skeleton, objects, name, source = body.skeleton, body.objects, body.name or "Scanned room", "scan"
    elif body.dimensions is not None:
        skeleton, objects, name, source = skeleton_from_dimensions(body.dimensions, body.doors, body.windows), body.objects, body.name or "My room", "manual"
    else:
        raise HTTPException(422, f"Provide 'sample' ({', '.join(SAMPLES)}), 'skeleton' or 'dimensions'")
    room, layout = await create_room(ctx, name=name, skeleton=skeleton, source=source, objects=objects, user_id=user.id, seed=body.seed, space_types=space_types, elements=elements)
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


class SetupBody(BaseModel):
    spaceTypes: list[str] | None = None
    elements: list[RoomElement] | None = None


@router.patch("/{room_id}/setup")
async def patch_setup(room_id: str, body: SetupBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Update the room's space types / elements checklist. The skeleton is never touched here."""
    room = await ctx.repo.get("rooms", room_id)
    if room is None:
        raise HTTPException(404, "room not found")
    patch: dict[str, Any] = {}
    if body.spaceTypes is not None:
        patch["spaceTypes"] = body.spaceTypes
    if body.elements is not None:
        patch["elements"] = [e.model_dump() for e in body.elements]
    return await ctx.repo.update("rooms", room_id, patch) or room


setup_router = APIRouter(prefix="/setup", tags=["setup"])


@setup_router.get("/space-types")
async def space_types() -> list[dict[str, str]]:
    return SPACE_TYPES


@setup_router.get("/suggestions")
async def suggestions(types: str = "") -> dict:
    """`?types=bedroom,study` → the elements those spaces usually need, plus the full element vocabulary for custom picks."""
    picked = [t for t in types.split(",") if t]
    return {"suggested": [e.model_dump() for e in suggest_elements(picked)], "all": [e.model_dump() for e in ELEMENTS.values()]}
