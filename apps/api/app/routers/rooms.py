import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError
from starlette.datastructures import UploadFile

from app.config import MAX_USDZ_BYTES
from app.deps import AppContext, get_ctx
from app.models import Dimensions, Door, Layout, Room, RoomSkeleton, Window
from app.services.ingest import UsdUnavailable, ingest_usdz, is_own_blob
from app.services.rooms import (
    DEFAULT_SAMPLE,
    SAMPLES,
    create_room,
    dedupe_name,
    load_sample,
    make_layout,
    now_iso,
    seed_items,
    skeleton_from_dimensions,
    taken_names,
    validate_for_room,
)
from app.services.usdz_convert import ConversionError

router = APIRouter(prefix="/rooms", tags=["rooms"])
log = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}
_JSON_FIELDS = ("dimensions", "doors", "windows", "objects", "skeleton")
CREATE_DOC = (
    "Create a room + read-only Base Layout + Current Room (a fork of Base). One of: a RoomPlan `.usdz` (multipart field `usdz`, "
    "converted server-side; the raw file is stored in Blob first), `usdzUrl` (re-convert a stored scan), `sample` (`true` or a "
    "sample name), manual `dimensions` (+ `doors`/`windows`), or a legacy `skeleton` + `objects` JSON export. Multipart fields "
    "holding objects (`dimensions`, `doors`, `windows`) are JSON strings. A failed conversion is a 422 with `conversionReport`."
)


class CreateRoomBody(BaseModel):
    sample: bool | Literal["nyc-bedroom", "studio"] | None = None
    usdzUrl: str | None = None
    skeleton: RoomSkeleton | None = None
    objects: list[dict[str, Any]] = []
    dimensions: Dimensions | None = None
    doors: list[Door] = []
    windows: list[Window] = []
    name: str | None = Field(default=None, max_length=80)


class RenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class RestoreBody(BaseModel):
    target: Literal["base", "empty"]
    name: str | None = Field(default=None, min_length=1, max_length=60)


def _created(room: Room, base: Layout, current: Layout) -> dict:
    b, c = base.model_dump(), current.model_dump()
    return {"room": room.to_doc(), "baseLayout": b, "currentLayout": c, "layouts": [b, c]}


async def _read_body(request: Request) -> tuple[CreateRoomBody, bytes | None]:
    usdz: bytes | None = None
    try:
        if request.headers.get("content-type", "").startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
            form = await request.form()
            raw: dict[str, Any] = {}
            for key, value in form.multi_items():
                if isinstance(value, UploadFile):
                    if key in ("usdz", "file"):
                        usdz = await value.read(MAX_USDZ_BYTES + 1)
                elif key in _JSON_FIELDS:
                    raw[key] = json.loads(value)
                elif key == "sample":
                    raw[key] = True if value.lower() in _TRUE else value
                else:
                    raw[key] = value
            body = CreateRoomBody.model_validate(raw)
        else:
            body = CreateRoomBody.model_validate(await request.json())
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"invalid JSON: {exc.msg}") from exc
    return body, usdz


async def _get_room(ctx: AppContext, room_id: str) -> Room:
    doc = await ctx.repo.get("rooms", room_id)
    if doc is None:
        raise HTTPException(404, "room not found")
    return Room.model_validate(doc)


@router.post("", status_code=201, summary="Create a room", description=CREATE_DOC, openapi_extra={
    "requestBody": {"content": {
        "multipart/form-data": {"schema": {"type": "object", "properties": {
            "usdz": {"type": "string", "format": "binary"}, "usdzUrl": {"type": "string"}, "sample": {"type": "string"}, "name": {"type": "string"},
            "dimensions": {"type": "string", "description": "JSON {l, w, h}"}, "doors": {"type": "string"}, "windows": {"type": "string"},
        }}},
        "application/json": {"schema": CreateRoomBody.model_json_schema(ref_template="#/components/schemas/{model}")},
    }},
})
async def post_room(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict:
    body, usdz = await _read_body(request)
    user = await ctx.demo_user()
    try:
        if usdz is not None or body.usdzUrl:
            if usdz is not None and len(usdz) > MAX_USDZ_BYTES:
                raise HTTPException(413, f"USDZ larger than {MAX_USDZ_BYTES // (1024 * 1024)} MB")
            if usdz is not None and not usdz:
                raise HTTPException(422, "empty USDZ upload")
            if usdz is None and not is_own_blob(body.usdzUrl or ""):
                raise HTTPException(422, "usdzUrl must point at a scan stored by this service")
            room, base, current = await ingest_usdz(ctx, data=usdz, usdz_url=None if usdz is not None else body.usdzUrl, name=body.name or "Scanned room", user_id=user.id)
            return _created(room, base, current)
        if body.sample:
            data = load_sample(DEFAULT_SAMPLE if body.sample is True else body.sample)
            skeleton, items, name, source = RoomSkeleton.model_validate(data["skeleton"]), seed_items(data["objects"]), body.name or data["name"], "sample"
        elif body.skeleton is not None:
            skeleton, items, name, source = body.skeleton, seed_items(body.objects), body.name or "Scanned room", "scan"
        elif body.dimensions is not None:
            skeleton, items, name, source = skeleton_from_dimensions(body.dimensions, body.doors, body.windows), seed_items(body.objects), body.name or "My room", "manual"
        else:
            raise HTTPException(422, f"Provide a RoomPlan 'usdz' file, 'usdzUrl', 'sample' (true or {', '.join(SAMPLES)}), 'dimensions' or 'skeleton'")
        room, base, current = await create_room(ctx, name=name, skeleton=skeleton, source=source, items=items, user_id=user.id)  # type: ignore[arg-type]
        return _created(room, base, current)
    except ConversionError as exc:
        raise HTTPException(422, {"message": f"Could not convert the scan: {exc}. Use the sample room or enter dimensions.", "conversionReport": exc.report}) from exc
    except UsdUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:  # a door/window that doesn't fit its wall
        raise HTTPException(422, str(exc)) from exc


@router.get("", summary="List saved rooms")
async def list_rooms(userId: str | None = None, ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    rows = await ctx.repo.list("rooms", **({"userId": userId} if userId else {}))
    return [{"thumbnailUrl": None, "updatedAt": r.get("createdAt"), **r} for r in rows]


@router.get("/{room_id}", summary="Skeleton + layouts")
async def get_room(room_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    room = await _get_room(ctx, room_id)
    return {"room": room.to_doc(), "layouts": [Layout.model_validate(l).model_dump() for l in await ctx.repo.list_by_room("layouts", room_id)]}


@router.patch("/{room_id}", summary="Rename a room")
async def rename_room(room_id: str, body: RenameBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    await _get_room(ctx, room_id)
    return await ctx.repo.update("rooms", room_id, {"name": body.name.strip(), "updatedAt": now_iso()}) or {}


@router.delete("/{room_id}", status_code=204, summary="Delete a room and everything that belongs to it")
async def delete_room(room_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    """Layouts, agent requests, rent checks, payment quotes and scanned furniture go in one atomic batch (a Mongo transaction on
    Atlas). Blob files are deleted after the commit: if that fails the files are orphaned (logged), never the room half-deleted."""
    room = await _get_room(ctx, room_id)
    await ctx.repo.apply([
        ("delete_where", "layouts", {"roomId": room_id}),
        ("delete_where", "agent_requests", {"roomId": room_id}),
        ("delete_where", "rent_assessments", {"roomId": room_id}),
        ("delete_where", "payment_quotes", {"roomId": room_id}),
        ("delete_where", "furniture", {"roomId": room_id}),
        ("delete", "rooms", room_id),
    ])
    urls = [u for u in (room.usdzUrl, room.thumbnailUrl) if u]
    try:
        await ctx.blob.delete(urls)
    except Exception as exc:  # the room is already gone; don't resurrect it over a storage hiccup
        log.error("room %s deleted but blob cleanup failed for %s: %s", room_id, urls, exc)


@router.post("/{room_id}/restore", status_code=201, summary="Back to the original room, as a new variant")
async def restore(room_id: str, body: RestoreBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    room = await _get_room(ctx, room_id)
    base_doc = await ctx.repo.get("layouts", room.baseLayoutId) if room.baseLayoutId else None
    if base_doc is None:
        raise HTTPException(409, "this room was created before Base Layouts existed; there is nothing to restore")
    base = Layout.model_validate(base_doc)
    items = base.items if body.target == "base" else []
    default = "Original Room (restored)" if body.target == "base" else "Empty room"
    validation = await validate_for_room(ctx, room, items, [])
    layout = make_layout(
        room_id, dedupe_name(body.name or default, await taken_names(ctx, room_id)), "variant", items, [], validation,
        parent=base.id if body.target == "base" else None,
    )
    await ctx.repo.insert("layouts", layout.model_dump())
    await ctx.repo.update("rooms", room_id, {"updatedAt": now_iso()})
    return layout.model_dump()
