import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl

from app.catalog import all_furniture
from app.config import LINK_IMPORT_TIMEOUT_S, MAX_PHOTO_BYTES
from app.deps import AppContext, get_ctx
from app.imports import BLOCKED_HINT, ListingBlocked, build_item, import_from_link, import_from_photo
from app.models import Dims, FurnitureCategory

router = APIRouter(prefix="/furniture", tags=["furniture"])


class FromLinkBody(BaseModel):
    url: HttpUrl


class ManualBody(BaseModel):
    name: str
    dims: Dims
    category: FurnitureCategory | None = None
    price: float | None = None


@router.get("", summary="Presets + the user's imported items")
async def list_furniture(category: str | None = None, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Seeded presets (Mongo) override the bundled manifest by id. Scanned items belong to their room's layouts, not the palette."""
    user = await ctx.demo_user()
    items = [f for f in (await all_furniture(ctx.repo)).values() if f.userId in (None, user.id) and f.source != "scan"]
    if category:
        items = [f for f in items if category in (f.category, f.kind)]
    return {"items": [f.model_dump() for f in items]}


@router.post("/from-link", status_code=201, summary="Import from a listing URL (< 10 s)")
async def from_link(body: FromLinkBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    try:
        item = await asyncio.wait_for(import_from_link(ctx.repo, ctx.gemini, str(body.url), user.id), LINK_IMPORT_TIMEOUT_S)
    except (ListingBlocked, TimeoutError) as exc:
        raise HTTPException(422, {"message": BLOCKED_HINT, "reason": str(exc) or "timed out"}) from exc
    return item.model_dump()


@router.post("/from-photo", status_code=201, summary="Import from a photo (Gemini vision; dims estimated)")
async def from_photo(image: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    data = await image.read(MAX_PHOTO_BYTES + 1)
    if not data:
        raise HTTPException(422, "empty image")
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, f"photo larger than {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    item = await import_from_photo(ctx.repo, ctx.gemini, ctx.blob, data, image.content_type or "image/jpeg", user.id)
    return item.model_dump()


async def _manual(body: ManualBody, ctx: AppContext) -> dict:
    user = await ctx.demo_user()
    item = build_item({"name": body.name, "category": body.category, "dims": body.dims.model_dump(), "price": body.price}, user_id=user.id, source="manual", source_url=None)
    await ctx.repo.insert("furniture", {**item.model_dump(), "createdAt": datetime.now(UTC).isoformat()})
    return item.model_dump()


@router.post("", status_code=201, summary="Add an item from manual dimensions")
async def create_manual(body: ManualBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    return await _manual(body, ctx)


@router.post("/manual", status_code=201, include_in_schema=False)
async def manual(body: ManualBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Alias kept for the existing web/mobile clients."""
    return await _manual(body, ctx)
