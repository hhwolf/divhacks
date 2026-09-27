"""Private, metadata-stripped condition photos. Never sent to a vision model."""
import io
import warnings

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.deps import AppContext, get_ctx
from app.routers.rent import ensure_room
from app.services import new_id, now_iso

router = APIRouter(tags=["condition evidence"])
MAX_BYTES = 5 * 1024 * 1024


def sanitize_image(raw: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ("JPEG", "PNG", "WEBP") or image.width * image.height > 20_000_000:
                    raise ValueError("Unsupported image or dimensions")
                image.load()
                image = ImageOps.exif_transpose(image)
                image.thumbnail((2000, 2000))
                # A new image strips EXIF, GPS, ICC and arbitrary embedded metadata.
                clean = Image.new("RGB", image.size, "white")
                if image.mode in ("RGBA", "LA"):
                    rgba = image.convert("RGBA")
                    clean.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    clean.paste(image.convert("RGB"))
                out = io.BytesIO()
                clean.save(out, format="JPEG", quality=85)
                return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, "Use a JPEG, PNG or WebP image below 20 megapixels") from exc


async def storage(ctx: AppContext, method: str, key: str, data: bytes | None = None) -> bytes:
    s = ctx.settings
    if s.supabase_live:
        headers = {"apikey": s.supabase_secret_key, "Content-Type": "image/jpeg"}
        if s.supabase_secret_key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {s.supabase_secret_key}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.request(method, f"{s.supabase_url}/storage/v1/object/{s.evidence_bucket}/{key}", content=data, headers=headers)
            if method == "DELETE" and response.status_code == 404:
                return b""
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            raise HTTPException(503, "Private photo storage unavailable. Configure the private evidence bucket.") from exc
    path = s.data_dir / "private-evidence" / key
    if method == "POST":
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(data or b"")
        path.chmod(0o600)
        return b""
    if method == "DELETE":
        path.unlink(missing_ok=True)
        return b""
    if not path.exists():
        raise HTTPException(404, "Photo not found")
    return path.read_bytes()


@router.post("/rooms/{room_id}/evidence", status_code=201)
async def upload(room_id: str, request: Request, image: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)) -> dict:
    await ensure_room(ctx, room_id)
    if not ctx.principal.authenticated and not request.headers.get("x-demo-session"):
        raise HTTPException(401, "A private browser session or sign-in is required for photos")
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(422, "Use a JPEG, PNG or WebP photo")
    raw = await image.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Photos must be at most 5 MB")
    data = sanitize_image(raw)
    photo_id = new_id()
    key = f"{ctx.principal.id}/{photo_id}.jpg"
    await storage(ctx, "POST", key, data)
    doc = {"id": photo_id, "roomId": room_id, "userId": ctx.principal.id, "storageKey": key,
           "createdAt": now_iso(), "mimeType": "image/jpeg", "size": len(data), "source": "user", "mode": "private" if ctx.principal.authenticated else "demo"}
    try:
        await ctx.repo.insert("evidence", doc)
    except Exception:
        await storage(ctx, "DELETE", key)
        raise
    return {"photo": {k: v for k, v in doc.items() if k != "storageKey"}}


@router.get("/rooms/{room_id}/evidence")
async def list_photos(room_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    await ensure_room(ctx, room_id)
    return {"photos": [{k: v for k, v in p.items() if k != "storageKey"} for p in await ctx.repo.list("evidence", roomId=room_id)]}


@router.get("/evidence/{photo_id}")
async def get_photo(photo_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    doc = await ctx.repo.get("evidence", photo_id)
    if not doc:
        raise HTTPException(404, "Photo not found")
    return Response(await storage(ctx, "GET", doc["storageKey"]), media_type="image/jpeg", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/evidence/{photo_id}", status_code=204)
async def delete_photo(photo_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    doc = await ctx.repo.get("evidence", photo_id)
    if not doc:
        raise HTTPException(404, "Photo not found")
    await storage(ctx, "DELETE", doc["storageKey"])
    await ctx.repo.delete("evidence", photo_id)
    # Remove references from the editable profile; historical assessments retain evidence IDs only.
    profile = await ctx.repo.get("housing_profiles", doc["roomId"])
    if profile:
        conditions = profile.get("conditions", [])
        for condition in conditions:
            condition["photoIds"] = [p for p in condition.get("photoIds", []) if p != photo_id]
        await ctx.repo.update("housing_profiles", profile["id"], {"conditions": conditions})
