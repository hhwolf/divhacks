"""Housing profiles, explicit source selection, and comparable-rent assessments."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import AppContext, get_ctx
from app.housing_models import HousingProfile
from app.integrations.housing import addresses, benchmarks, rental_candidates
from app.rent import assess_rent

router = APIRouter(tags=["rent"])


class RentAssessBody(HousingProfile):
    layoutId: str | None = None


async def ensure_room(ctx: AppContext, room_id: str) -> dict:
    room = await ctx.repo.get("rooms", room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    return room


async def validate_photos(ctx: AppContext, profile: HousingProfile) -> None:
    for condition in profile.conditions:
        if condition.source == "public_record":
            raise HTTPException(422, "Your observations must be user reports or photos. Public records are fetched separately.")
        for photo_id in condition.photoIds:
            photo = await ctx.repo.get("evidence", photo_id)
            if not photo or photo["roomId"] != profile.roomId:
                raise HTTPException(422, "Photo must belong to this room")


@router.put("/rooms/{room_id}/housing-profile")
async def save_profile(room_id: str, body: HousingProfile, ctx: AppContext = Depends(get_ctx)) -> dict:
    await ensure_room(ctx, room_id)
    if body.roomId != room_id:
        raise HTTPException(422, "Profile room does not match")
    await validate_photos(ctx, body)
    doc = body.model_dump(mode="json")
    if await ctx.repo.get("housing_profiles", room_id):
        await ctx.repo.update("housing_profiles", room_id, {k: v for k, v in doc.items() if k != "roomId"})
    else:
        await ctx.repo.insert("housing_profiles", {**doc, "id": room_id})
    return {"profile": doc}


@router.get("/rooms/{room_id}/housing-profile")
async def get_profile(room_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    await ensure_room(ctx, room_id)
    doc = await ctx.repo.get("housing_profiles", room_id)
    return {"profile": {k: v for k, v in doc.items() if k not in ("id", "userId")} if doc else None}


@router.post("/rent/assess", status_code=201)
async def rent_assess(body: RentAssessBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    profile = HousingProfile.model_validate(body.model_dump(exclude={"layoutId"}))
    await validate_photos(ctx, profile)
    try:
        assessment = await assess_rent(ctx, profile, body.layoutId)
        context, _ = benchmarks(profile)
        return {"assessment": assessment.model_dump(mode="json"), "benchmarks": context}
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/rooms/{room_id}/rent-assessment")
async def latest_rent_assessment(room_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    await ensure_room(ctx, room_id)
    rows = await ctx.repo.list("rent_assessments", roomId=room_id)
    if not rows:
        raise HTTPException(404, "Rent assessment not found")
    latest = rows[-1]
    if not latest.get("methodVersion"):
        return {"assessment": None, "status": "legacy_demo", "message": "This saved assessment used legacy fixture deductions. Run a new comparison."}
    return {"assessment": latest}


@router.get("/housing/addresses")
async def address_search(q: str = Query(min_length=3, max_length=300), mode: str = "real", ctx: AppContext = Depends(get_ctx)) -> dict:
    if mode not in ("real", "demo"):
        raise HTTPException(422, "Mode must be real or demo")
    return await addresses(q, mode == "demo")


@router.post("/housing/comparables/search")
async def comparable_search(body: HousingProfile, ctx: AppContext = Depends(get_ctx)) -> dict:
    await ensure_room(ctx, body.roomId)
    rows, source = await rental_candidates(ctx.settings, body)
    return {"comparables": [c.model_dump(mode="json") for c in rows], "source": source.model_dump(mode="json")}
