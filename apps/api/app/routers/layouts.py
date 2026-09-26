from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.catalog import all_furniture
from app.deps import AppContext, get_ctx
from app.models import Layout, LayoutItem, Room, Zone
from app.services import new_id, now_iso, validate_for_room

router = APIRouter(prefix="/layouts", tags=["layouts"])


class PutLayoutBody(BaseModel):
    items: list[LayoutItem] | None = None
    zones: list[Zone] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=60)
    source: str | None = None


class ForkBody(BaseModel):
    name: str | None = None


async def _load(ctx: AppContext, layout_id: str) -> tuple[Layout, Room]:
    doc = await ctx.repo.get("layouts", layout_id)
    if doc is None:
        raise HTTPException(404, "layout not found")
    layout = Layout.model_validate(doc)
    room_doc = await ctx.repo.get("rooms", layout.roomId)
    if room_doc is None:
        raise HTTPException(404, "room not found")
    return layout, Room.model_validate(room_doc)


@router.get("/{layout_id}")
async def get_layout(layout_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    layout, room = await _load(ctx, layout_id)
    catalog = await all_furniture(ctx.repo)
    used = {it.furnitureId for it in layout.items}
    validation = await validate_for_room(ctx, room, layout.items, layout.zones)
    return {"layout": layout.model_dump(), "furniture": {k: v.model_dump() for k, v in catalog.items() if k in used}, "validation": validation.model_dump()}


@router.put("/{layout_id}")
async def put_layout(layout_id: str, body: PutLayoutBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    layout, room = await _load(ctx, layout_id)
    if layout.isCurrent and body.source != "editor":
        raise HTTPException(403, "the Current Room can only be edited from the editor")
    if layout.isCurrent and body.name is not None and body.name != layout.name:
        raise HTTPException(409, "the Current Room cannot be renamed")
    items = body.items if body.items is not None else layout.items
    zones = body.zones if body.zones is not None else layout.zones
    validation = await validate_for_room(ctx, room, items, zones)
    if validation.blocked:
        raise HTTPException(422, {"message": "layout has blocking violations", "violations": [v.model_dump() for v in validation.violations]})
    patch = {"items": [i.model_dump() for i in items], "zones": [z.model_dump() for z in zones], "metrics": validation.metrics.model_dump(), "updatedAt": now_iso()}
    if body.name is not None:
        patch["name"] = body.name
    saved = await ctx.repo.update("layouts", layout_id, patch)
    return {"layout": saved, "validation": validation.model_dump()}


@router.post("/{layout_id}/fork", status_code=201)
async def fork_layout(layout_id: str, body: ForkBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    layout, _ = await _load(ctx, layout_id)
    copy = layout.model_copy(update={"id": new_id(), "name": body.name or f"{layout.name} copy", "isCurrent": False, "parentLayoutId": layout.id, "createdBy": "user", "createdAt": now_iso(), "updatedAt": now_iso()})
    await ctx.repo.insert("layouts", copy.model_dump())
    return copy.model_dump()


@router.delete("/{layout_id}", status_code=204)
async def delete_layout(layout_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    layout, _ = await _load(ctx, layout_id)
    if layout.isCurrent:
        raise HTTPException(409, "the Current Room cannot be deleted")
    await ctx.repo.delete("layouts", layout_id)


@router.get("/{a}/compare/{b}")
async def compare(a: str, b: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    la, room = await _load(ctx, a)
    lb, _ = await _load(ctx, b)
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
