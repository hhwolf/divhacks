import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agent import pipeline
from app.agent.router import route
from app.deps import AppContext, get_ctx
from app.imports import URL_RE
from app.integrations.photon import Attachment
from app.models import Channel, HousingProfile
from app.rent import assess_rent

router = APIRouter(prefix="/agent", tags=["agent"])
APP_ASSISTANT_SPATIAL_ONLY = "Use iMessage/Photon to send new furniture links or photos. In the app, ask me to arrange the room: make space for yoga, create a reading corner, place the desk near the window, or don't move my bed."


class AgentRequestBody(BaseModel):
    text: str
    roomId: str
    baseLayoutId: str
    furnitureId: str | None = None
    imageUrl: str | None = None
    channel: Channel = "app"


@router.post("/request")
async def agent_request(body: AgentRequestBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    room = await ctx.repo.get("rooms", body.roomId)
    base = await ctx.repo.get("layouts", body.baseLayoutId)
    if not room or not base or base["roomId"] != body.roomId:
        raise HTTPException(404, "Room or layout not found")
    if body.furnitureId:
        from app.catalog import PRESETS
        if body.furnitureId not in PRESETS and not await ctx.repo.get("furniture", body.furnitureId):
            raise HTTPException(404, "Furniture not found")
    housing = await _maybe_housing_reply(ctx, body)
    if housing is not None:
        return housing
    if body.channel == "app" and body.furnitureId is None and (body.imageUrl or URL_RE.search(body.text or "")):
        return {
            "plan": {"intent": "clarify", "reply": APP_ASSISTANT_SPATIAL_ONLY, "clarifyingQuestion": APP_ASSISTANT_SPATIAL_ONLY},
            "layout": None,
            "reply": APP_ASSISTANT_SPATIAL_ONLY,
            "status": "clarify",
            "links": [],
            "requestId": uuid.uuid4().hex[:12],
            "violations": [],
        }
    attachments = [Attachment(url=body.imageUrl, mime_type="image/jpeg")] if body.imageUrl else []
    routed = await route(ctx, user.id, body.text, attachments, body.furnitureId)
    out = await pipeline.run(
        ctx, request_text=routed.text, user_id=user.id, room_id=body.roomId, base_layout_id=body.baseLayoutId, furniture_id=routed.furniture_id, channel=body.channel
    )
    return {
        "plan": out.plan.model_dump(exclude_none=True) if out.plan else None,
        "layout": out.layout,
        "reply": out.reply,
        "status": out.status,
        "links": out.links,
        "requestId": out.request_id,
        "violations": [v.model_dump() for v in out.violations],
    }


def _money(text: str) -> float | None:
    m = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text)
    return float(m.group(1).replace(",", "")) if m else None


def _zip(text: str) -> str | None:
    m = re.search(r"\b(10[0-2][0-9]{2}|11[0-6][0-9]{2})\b", text)
    return m.group(1) if m else None


def _issues(text: str) -> list[str]:
    out: list[str] = []
    low = text.lower()
    for word, label in (
        ("rat", "rats"),
        ("rodent", "rodents"),
        ("bug", "bugs"),
        ("roach", "bugs"),
        ("leak", "water leak"),
        ("faucet", "bad faucet"),
        ("plumbing", "plumbing problem"),
        ("floor", "floor damage"),
        ("voucher", "voucher / source of income concern"),
    ):
        if word in low and label not in out:
            out.append(label)
    return out


async def _maybe_housing_reply(ctx: AppContext, body: AgentRequestBody) -> dict | None:
    text = body.text.lower()
    payment = any(k in text for k in ("deposit", "application fee", "screening", "broker fee", "pay ", "send $", "checkout"))
    rent = any(k in text for k in ("rent", "fair", "overpriced", "price check"))
    if not payment and not rent:
        return None
    reply = "Open Rent → Review payment to review the recipient, documented tenancy amount and itemized fees. I cannot authorize a payment."
    assessment = None
    if rent and not payment:
        saved = await ctx.repo.get("housing_profiles", body.roomId)
        if saved:
            profile = HousingProfile.model_validate({k: v for k, v in saved.items() if k not in ("id", "userId")})
            assessment = await assess_rent(ctx, profile, body.baseLayoutId)
            if assessment.estimatedFairRange:
                r = assessment.estimatedFairRange
                reply = f"Comparable asking rents are ${r.low}–${r.high}/month. " + ("Demo data. " if assessment.status == "demo" else "") + "See the Rent panel for sources and condition matching; this is not legal regulated rent."
            else:
                reply = "Insufficient comparable data. Open Rent to confirm the space, rental terms and comparable listings."
        else:
            reply = "Open Rent to confirm your measurements, rental terms and any housing problems before comparing rent."
    return {"plan": {"intent": "payment_check" if payment else "rent_check", "reply": reply},
            "layout": None, "reply": reply, "status": "ok", "links": [], "requestId": uuid.uuid4().hex[:12],
            "violations": [], "assessment": assessment.model_dump(mode="json") if assessment else None}
