from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.catalog import all_furniture
from app.deps import AppContext, get_ctx
from app.models import Layout, LayoutItem, Room, Violation, Zone
from app.services.rooms import CURRENT_NAME, dedupe_name, new_id, now_iso, saved_metrics, taken_names, touch_room, validate_for_room

router = APIRouter(prefix="/layouts", tags=["layouts"])
BASE_READ_ONLY = "the Base Layout is read-only; fork it or use POST /rooms/{id}/restore"


class PutLayoutBody(BaseModel):
    items: list[LayoutItem] | None = None
    zones: list[Zone] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=60)
    version: int | None = Field(default=None, description="the version you edited; a stale one is a 409 (omit only for legacy clients)")
    source: str | None = Field(default=None, description="'editor' is required to save the Current Room")


class ForkBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)


class RenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)


def by_item(violations: list[Violation]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for v in violations:
        for item in v.items:
            out.setdefault(item, []).append(v.model_dump())
    return out


async def _load(ctx: AppContext, layout_id: str) -> tuple[Layout, Room, dict]:
    doc = await ctx.repo.get("layouts", layout_id)
    if doc is None:
        raise HTTPException(404, "layout not found")
    layout = Layout.model_validate(doc)
    room_doc = await ctx.repo.get("rooms", layout.roomId)
    if room_doc is None:
        raise HTTPException(404, "room not found")
    return layout, Room.model_validate(room_doc), doc


@router.get("/{layout_id}", summary="A layout with the catalog entries for its items")
async def get_layout(layout_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    layout, room, _ = await _load(ctx, layout_id)
    catalog = await all_furniture(ctx.repo)
    used = {it.furnitureId for it in layout.items}
    validation = await validate_for_room(ctx, room, layout.items, layout.zones)
    return {"layout": layout.model_dump(), "furniture": {k: v.model_dump() for k, v in catalog.items() if k in used}, "validation": validation.model_dump()}


@router.put("/{layout_id}", summary="Save items/zones (hard rules re-checked; optimistic versioning)")
async def put_layout(layout_id: str, body: PutLayoutBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    layout, room, raw = await _load(ctx, layout_id)
    if layout.kind == "base":
        raise HTTPException(403, BASE_READ_ONLY)
    if layout.isCurrent and body.source != "editor":
        raise HTTPException(403, "the Current Room can only be edited from the editor")
    if layout.isCurrent and body.name is not None and body.name != layout.name:
        raise HTTPException(409, "the Current Room cannot be renamed")
    if body.version is not None and body.version != layout.version:
        raise HTTPException(409, {"message": "stale version; refetch the layout", "version": layout.version})
    items = body.items if body.items is not None else layout.items
    zones = body.zones if body.zones is not None else layout.zones
    validation = await validate_for_room(ctx, room, items, zones)
    if validation.blocked:
        hard = [v for v in validation.violations if v.rule in ("bounds", "overlap")]
        raise HTTPException(422, {"message": "layout has blocking violations", "violations": [v.model_dump() for v in validation.violations], "byItem": by_item(hard)})
    patch = {
        "items": [i.model_dump() for i in items],
        "zones": [z.model_dump() for z in zones],
        "metrics": saved_metrics(validation).model_dump(),
        "version": layout.version + 1,
        "updatedAt": now_iso(),
    }
    if body.name is not None:
        patch["name"] = body.name
    # compare-and-set on the version we validated against; layouts saved before versioning have no field to compare
    saved = await ctx.repo.update_if("layouts", layout_id, {"version": layout.version} if "version" in raw else {}, patch)
    if saved is None:
        raise HTTPException(409, {"message": "the layout changed while saving; refetch it", "version": None})
    await touch_room(ctx, room.id)
    return {"layout": Layout.model_validate(saved).model_dump(), "validation": validation.model_dump()}


@router.patch("/{layout_id}", summary="Rename a variant")
async def rename_layout(layout_id: str, body: RenameBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    layout, room, _ = await _load(ctx, layout_id)
    if layout.kind == "base":
        raise HTTPException(403, BASE_READ_ONLY)
    if layout.isCurrent:
        raise HTTPException(409, "the Current Room cannot be renamed")
    name = body.name.strip()
    if name != layout.name and name in await taken_names(ctx, room.id):
        raise HTTPException(409, f"a layout named '{name}' already exists in this room")
    saved = await ctx.repo.update("layouts", layout_id, {"name": name, "updatedAt": now_iso()})
    return Layout.model_validate(saved).model_dump()


@router.post("/{layout_id}/fork", status_code=201, summary="Duplicate any layout as a new variant")
async def fork_layout(layout_id: str, body: ForkBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    layout, room, _ = await _load(ctx, layout_id)
    now = now_iso()
    name = dedupe_name(body.name or f"{layout.name} copy", await taken_names(ctx, room.id))
    copy = layout.model_copy(update={
        "id": new_id(), "name": name, "kind": "variant", "isCurrent": False, "parentLayoutId": layout.id, "createdBy": "user",
        "requestText": None, "version": 1, "createdAt": now, "updatedAt": now,
    })
    await ctx.repo.insert("layouts", copy.model_dump())
    await touch_room(ctx, room.id)
    return copy.model_dump()


@router.delete("/{layout_id}", status_code=204, summary="Delete a variant")
async def delete_layout(layout_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    layout, room, _ = await _load(ctx, layout_id)
    if layout.kind == "base":
        raise HTTPException(403, BASE_READ_ONLY)
    if layout.isCurrent:
        raise HTTPException(409, "the Current Room cannot be deleted; promote another layout first")
    await ctx.repo.delete("layouts", layout_id)
    await touch_room(ctx, room.id)


@router.post("/{layout_id}/promote", summary="Make a variant the Current Room; the old one stays as a variant")
async def promote(layout_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    layout, room, _ = await _load(ctx, layout_id)
    if layout.kind == "base":
        raise HTTPException(403, "the Base Layout cannot be promoted; restore it as a variant first")
    if layout.isCurrent:
        raise HTTPException(409, "this layout is already the Current Room")
    siblings = [Layout.model_validate(l) for l in await ctx.repo.list_by_room("layouts", room.id)]
    old = next((l for l in siblings if l.id == room.currentLayoutId), None) or next((l for l in siblings if l.isCurrent), None)
    now = datetime.now(UTC)
    ops: list[tuple] = []
    previous_name = None
    if old is not None:
        previous_name = dedupe_name(f"Previous Room, {now:%b} {now.day}", {l.name for l in siblings})
        ops.append(("update", "layouts", old.id, {"kind": "variant", "isCurrent": False, "name": previous_name, "updatedAt": now.isoformat()}))
    ops.append(("update", "layouts", layout.id, {
        "kind": "current", "isCurrent": True, "name": CURRENT_NAME, "promotedFromName": layout.name, "version": layout.version + 1, "updatedAt": now.isoformat(),
    }))
    ops.append(("update", "rooms", room.id, {"currentLayoutId": layout.id, "updatedAt": now.isoformat()}))
    await ctx.repo.apply(ops)
    current = Layout.model_validate(await ctx.repo.get("layouts", layout.id)).model_dump()
    prev = Layout.model_validate(await ctx.repo.get("layouts", old.id)).model_dump() if old else None
    return {"current": current, "previous": prev, "previousName": previous_name}


@router.get("/{a}/compare/{b}", summary="Metric deltas + items moved / added / removed")
async def compare(a: str, b: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    la, room, _ = await _load(ctx, a)
    lb, _, _ = await _load(ctx, b)
    if la.roomId != lb.roomId:
        raise HTTPException(422, "layouts belong to different rooms")
    catalog = await all_furniture(ctx.repo)
    va, vb = await validate_for_room(ctx, room, la.items, la.zones), await validate_for_room(ctx, room, lb.items, lb.zones)
    ma, mb = va.metrics, vb.metrics
    name = lambda it: catalog[it.furnitureId].name if it.furnitureId in catalog else it.furnitureId  # noqa: E731
    pose = lambda it: {"x": it.x, "z": it.z, "rotation": it.rotation}  # noqa: E731
    ia, ib = {i.id: i for i in la.items}, {i.id: i for i in lb.items}
    moved = [{"id": k, "name": name(ib[k]), "from": pose(ia[k]), "to": pose(ib[k])} for k in ia if k in ib and pose(ia[k]) != pose(ib[k])]
    return {
        "a": {**la.model_dump(), "metrics": ma.model_dump()},
        "b": {**lb.model_dump(), "metrics": mb.model_dump()},
        "deltas": {
            "openFloor": round(mb.openFloor - ma.openFloor, 1),
            "conflicts": mb.conflicts - ma.conflicts,
            "reachableStorage": round(mb.reachableStorage - ma.reachableStorage, 1),
            "largestFreeRectArea": round((mb.largestFreeRect.areaM2 if mb.largestFreeRect else 0) - (ma.largestFreeRect.areaM2 if ma.largestFreeRect else 0), 2),
        },
        "moved": moved,
        "added": [{"id": k, "name": name(ib[k]), **pose(ib[k])} for k in ib if k not in ia],
        "removed": [{"id": k, "name": name(ia[k]), **pose(ia[k])} for k in ia if k not in ib],
    }
