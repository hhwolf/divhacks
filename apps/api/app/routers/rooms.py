from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.agent.prompts import room_purpose
from app.catalog import all_furniture
from app.deps import AppContext, get_ctx
from app.furnish import Photo, check_photos, clean_theme, furnish_room
from app.models import Dimensions, Door, RoomSkeleton, Window
from app.services import SAMPLES, create_room, load_sample, now_iso, skeleton_from_dimensions

router = APIRouter(prefix="/rooms", tags=["rooms"])


class RoomProfile(BaseModel):
    """What the space is for (set in the app's post-scan setup): space types, wanted elements, and the catalog ids to suggest."""

    spaceTypes: list[str] = Field(default_factory=list, max_length=12)
    elements: list[str] = Field(default_factory=list, max_length=40)
    suggestedFurniture: list[str] = Field(default_factory=list, max_length=40)


class CreateRoomBody(RoomProfile):
    """One of: {sample}, {skeleton, objects, name} (RoomPlan export), {dimensions, doors, windows, name} (manual), plus an optional profile."""

    sample: Literal["nyc-bedroom", "studio", "l-shaped"] | None = None
    skeleton: RoomSkeleton | None = None
    objects: list[dict[str, Any]] = []
    dimensions: Dimensions | None = None
    doors: list[Door] = []
    windows: list[Window] = []
    name: str | None = None


class PatchRoomBody(BaseModel):
    """Name and profile only. The skeleton is immutable after creation, so any other field is rejected (422)."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=60)
    spaceTypes: list[str] | None = Field(default=None, max_length=12)
    elements: list[str] | None = Field(default=None, max_length=40)
    suggestedFurniture: list[str] | None = Field(default=None, max_length=40)


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
    profile = RoomProfile(spaceTypes=body.spaceTypes, elements=body.elements, suggestedFurniture=body.suggestedFurniture).model_dump()
    room, layout = await create_room(ctx, name=name, skeleton=skeleton, source=source, objects=objects, user_id=user.id, profile=profile)
    return {"room": room.model_dump(), "currentLayout": layout.model_dump(), "layouts": [layout.model_dump()]}


@router.get("")
async def list_rooms(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    rooms = await ctx.repo.list("rooms")
    counts: dict[str, int] = {}
    for layout in await ctx.repo.list("layouts"):
        counts[layout["roomId"]] = counts.get(layout["roomId"], 0) + 1
    return [{**r, "layoutCount": counts.get(r["id"], 0)} for r in rooms]


@router.delete("/{room_id}", status_code=204)
async def delete_room(room_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    """Deletes the room and all of its layouts (including the Current Room) — the user removing the whole room."""
    if await ctx.repo.get("rooms", room_id) is None:
        raise HTTPException(404, "room not found")
    for layout in await ctx.repo.list_by_room("layouts", room_id):
        await ctx.repo.delete("layouts", layout["id"])
    await ctx.repo.delete("rooms", room_id)


@router.patch("/{room_id}")
async def patch_room(room_id: str, body: PatchRoomBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    if await ctx.repo.get("rooms", room_id) is None:
        raise HTTPException(404, "room not found")
    patch = body.model_dump(exclude_none=True)
    if "name" in patch:
        patch["name"] = patch["name"].strip()
        if not patch["name"]:
            raise HTTPException(422, "name must not be blank")
    return {"room": await ctx.repo.update("rooms", room_id, {**patch, "updatedAt": now_iso()})}


class FurnishBody(BaseModel):
    theme: str = Field(min_length=1, max_length=300)
    baseLayoutId: str | None = None
    purposeHint: str | None = Field(default=None, max_length=300, description="e.g. the theme of the variant being restyled, so 'industrial' keeps it a bedroom")


@router.post("/{room_id}/furnish", status_code=201)
async def furnish(room_id: str, body: FurnishBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Theme ('cozy japandi study') -> a new furnished variant forked from the base (default: Current Room). Never fails on fit:
    pieces that don't fit are skipped and named in the reply."""
    theme = clean_theme(body.theme)
    if not theme:
        raise HTTPException(422, "theme must not be blank")
    return await _furnish(ctx, room_id, theme, body.baseLayoutId, body.purposeHint, None)


@router.post("/{room_id}/furnish/photos", status_code=201)
async def furnish_from_photos(
    room_id: str,
    images: list[UploadFile] = File(...),
    theme: str = Form(""),
    baseLayoutId: str | None = Form(None),  # noqa: N803 - wire name
    purposeHint: str | None = Form(None),  # noqa: N803
    ctx: AppContext = Depends(get_ctx),
) -> dict:
    """Same as /furnish, steered by 1-4 inspiration photos (style and the kinds of pieces in them); `theme` text is optional."""
    photos = [(await f.read(), f.content_type or "image/jpeg") for f in images]
    try:
        check_photos(photos)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _furnish(ctx, room_id, clean_theme(theme), baseLayoutId, purposeHint, photos)


async def _furnish(ctx: AppContext, room_id: str, theme: str, base_id: str | None, purpose_hint: str | None, photos: list[Photo] | None) -> dict:
    room = await ctx.repo.get("rooms", room_id)
    if room is None:
        raise HTTPException(404, "room not found")
    layouts = await ctx.repo.list_by_room("layouts", room_id)
    base = next((l for l in layouts if l["id"] == base_id), None) if base_id else next((l for l in layouts if l.get("isCurrent")), None)
    if base is None:
        raise HTTPException(404, "layout not found")
    purpose = "; ".join(p for p in (clean_theme(purpose_hint or ""), room_purpose(room)) if p) or None
    out = await furnish_room(ctx, room, base, theme, purpose, await all_furniture(ctx.repo), photos)
    return {"layout": out.layout.model_dump(), "style": out.style, "placed": out.placed, "skipped": out.skipped, "reply": out.reply}


@router.get("/{room_id}")
async def get_room(room_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    room = await ctx.repo.get("rooms", room_id)
    if room is None:
        raise HTTPException(404, "room not found")
    return {"room": room, "layouts": await ctx.repo.list_by_room("layouts", room_id)}
