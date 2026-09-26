import re
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agent import pipeline
from app.agent.router import route
from app.deps import AppContext, get_ctx
from app.integrations.photon import Attachment
from app.models import Channel, HousingProfile
from app.rent import assess_rent, guard_payment

router = APIRouter(prefix="/agent", tags=["agent"])


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
    housing = await _maybe_housing_reply(ctx, body)
    if housing is not None:
        return housing
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
    request_id = uuid.uuid4().hex[:12]
    wants_payment = any(k in text for k in ("deposit", "application fee", "app fee", "pay ", "send $", "checkout"))
    wants_rent = any(k in text for k in ("rent", "fair", "overpriced", "price check", "rent check"))
    if not (wants_payment or wants_rent):
        return None

    amount = _money(body.text)
    latest = None
    rows = await ctx.repo.list("rent_assessments", roomId=body.roomId)
    if rows:
        latest = rows[-1]

    if wants_payment and ("deposit" in text or "application fee" in text or "app fee" in text):
        purpose = "deposit" if "deposit" in text else "application_fee"
        if amount is None:
            return {"plan": None, "layout": None, "reply": "What amount are they asking you to pay?", "status": "clarify", "links": [], "requestId": request_id, "violations": []}
        rent_amount = latest["askingRent"] if latest else None
        quote = guard_payment(ctx, purpose=purpose, amount=amount, rent_amount=rent_amount, room_id=body.roomId, assessment_id=latest["id"] if latest else None)  # type: ignore[arg-type]
        await ctx.repo.insert("payment_quotes", quote.model_dump())
        blocked = quote.status == "blocked"
        reply = ("I would not pay that: " if blocked else "That payment is within the current guardrails: ") + quote.guardrails[-1]
        return {
            "plan": {"intent": "payment_check", "reply": reply},
            "layout": None,
            "reply": reply,
            "status": "rejected" if blocked else "ok",
            "links": [quote.checkoutUrl] if quote.checkoutUrl else [],
            "requestId": request_id,
            "violations": [],
            "quote": quote.model_dump(),
        }

    if wants_rent:
        rent = amount or (latest["askingRent"] if latest else None)
        if rent is None:
            return {"plan": None, "layout": None, "reply": "What monthly rent should I check?", "status": "clarify", "links": [], "requestId": request_id, "violations": []}
        profile = HousingProfile(roomId=body.roomId, zip=_zip(body.text), askingRent=rent, occupancyType="private_room", declaredIssues=_issues(body.text))
        assessment = await assess_rent(ctx, profile, layout_id=body.baseLayoutId)
        delta = assessment.deltaVsMid
        direction = "above" if delta > 0 else "below"
        reply = f"${rent:.0f}/mo is ${abs(delta):.0f} {direction} the estimated midpoint; scanned area is {assessment.spaceQuality.floorAreaSqFt:.0f} sq ft with {assessment.confidence} confidence."
        return {
            "plan": {"intent": "rent_check", "reply": reply},
            "layout": None,
            "reply": reply,
            "status": "ok",
            "links": [f"roomplanner://layout/{body.baseLayoutId}", f"{ctx.settings.public_web_url}/layout/{body.baseLayoutId}"],
            "requestId": request_id,
            "violations": [],
            "assessment": assessment.model_dump(),
        }
    return None
