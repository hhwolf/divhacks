from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl, ConfigDict, Field

from app.catalog import PRESETS
from app.deps import AppContext, get_ctx
from app.imports import build_item, import_from_link, import_from_photo
from app.models import Dims, FurnitureCategory

router = APIRouter(prefix="/furniture", tags=["furniture"])


class FromLinkBody(BaseModel):
    url: HttpUrl


class ManualBody(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=200)
    dims: Dims
    category: FurnitureCategory | None = None
    price: float | None = Field(default=None, ge=0)
    deliveryCost: float = Field(default=0, ge=0)
    sourceUrl: HttpUrl | None = None


class DetailsBody(ManualBody):
    dimensionsConfirmed: bool


@router.get("")
async def list_furniture(ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    imported = [d for d in await ctx.repo.list("furniture") if d.get("userId") in (None, user.id)]
    return {"items": [p.model_dump() for p in PRESETS.values()] + imported}


@router.post("/from-link", status_code=201)
async def from_link(body: FromLinkBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    try:
        item = await import_from_link(ctx.repo, ctx.gemini, str(body.url), user.id)
    except Exception as exc:  # unreachable host, timeout, non-HTML
        raise HTTPException(502, f"could not fetch listing: {exc}") from exc
    return item.model_dump()


@router.post("/from-photo", status_code=201)
async def from_photo(image: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    data = await image.read(5 * 1024 * 1024 + 1)
    if not data or len(data) > 5 * 1024 * 1024 or image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(422, "Use a JPEG, PNG or WebP screenshot up to 5 MB")
    item = await import_from_photo(ctx.repo, ctx.gemini, data, image.content_type or "image/jpeg", user.id)
    return item.model_dump()


@router.post("/manual", status_code=201)
async def manual(body: ManualBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    item = build_item({"name": body.name, "category": body.category, "dims": body.dims.model_dump(), "price": body.price}, user_id=user.id, source="manual", source_url=str(body.sourceUrl) if body.sourceUrl else None)
    item.dimensionsConfirmed = True
    item.deliveryCost = body.deliveryCost
    await ctx.repo.insert("furniture", {**item.model_dump(), "createdAt": datetime.now(UTC).isoformat()})
    return item.model_dump()


@router.patch("/{item_id}/details")
async def details(item_id: str, body: DetailsBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    item = await ctx.repo.get("furniture", item_id)
    if not item:
        raise HTTPException(404, "Imported furniture not found")
    if not body.dimensionsConfirmed:
        raise HTTPException(422, "Confirm dimensions before using fit recommendations")
    patch = body.model_dump(mode="json")
    patch["estimated"] = False
    updated = await ctx.repo.update("furniture", item_id, patch)
    return updated
