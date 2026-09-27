import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agent import pipeline
from app.agent.router import DEFAULT_FIT_QUESTION, route
from app.deps import AppContext, get_ctx
from app.imports import IMPERIAL_RE, METRIC_RE, URL_RE, import_from_link, parse_dims
from app.integrations.photon import Attachment
from app.models import Channel, HousingProfile
from app.rent import assess_rent
from app.solver.units import format_length_imperial

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
    room = await ctx.repo.get("rooms", body.roomId)
    base = await ctx.repo.get("layouts", body.baseLayoutId)
    if not room or not base or base["roomId"] != body.roomId:
        raise HTTPException(404, "Room or layout not found")
    if body.furnitureId:
        from app.catalog import PRESETS
        if body.furnitureId not in PRESETS and not await ctx.repo.get("furniture", body.furnitureId):
            raise HTTPException(404, "Furniture not found")
    # A pasted listing link is a fit question (checked before the rent keywords, which also match words like "current").
    if body.channel == "app" and body.furnitureId is None and URL_RE.search(body.text or ""):
        return await _link_fit(ctx, user.id, body)
    housing = await _maybe_housing_reply(ctx, body)
    if housing is not None:
        return housing
    attachments = [Attachment(url=body.imageUrl, mime_type="image/jpeg")] if body.imageUrl else []
    routed = await route(ctx, user.id, body.text, attachments, body.furnitureId)
    out = await pipeline.run(
        ctx, request_text=routed.text, user_id=user.id, room_id=body.roomId, base_layout_id=body.baseLayoutId, furniture_id=routed.furniture_id, channel=body.channel
    )
    return _response(out)


def _response(out: pipeline.PipelineResult, reply: str | None = None) -> dict:
    return {
        "plan": out.plan.model_dump(exclude_none=True) if out.plan else None,
        "layout": out.layout,
        "reply": reply or out.reply,
        "status": out.status,
        "links": out.links,
        "requestId": out.request_id,
        "violations": [v.model_dump() for v in out.violations],
    }


def _plain(reply: str, status: str = "clarify") -> dict:
    return {"plan": {"intent": "clarify", "reply": reply, "clarifyingQuestion": reply}, "layout": None, "reply": reply,
            "status": status, "links": [], "requestId": uuid.uuid4().hex[:12], "violations": []}


def _size(dims: dict[str, float]) -> str:
    return f"{format_length_imperial(dims['w'])} W × {format_length_imperial(dims['d'])} D × {format_length_imperial(dims['h'])} H"


async def _link_fit(ctx: AppContext, user_id: str, body: AgentRequestBody) -> dict:
    """Pasted listing link: read the item's size from the page, then answer yes/no by running the real fit check.

    Dimensions typed in the message ("48 x 24 x 30 in") win over the listing. If neither states a size, ask for it
    instead of guessing a verdict.
    """
    url = URL_RE.search(body.text or "").group(0)  # type: ignore[union-attr]
    question = URL_RE.sub("", body.text).strip()
    try:
        item = await import_from_link(ctx.repo, ctx.gemini, url, user_id)
    except Exception:  # unreachable host, blocked page, not HTML
        return _plain("I couldn't open that link. Paste the item's size instead, e.g. \"desk 48 x 24 x 30 in\", and I'll check the fit.")
    typed = parse_dims(question)
    # the size itself isn't part of the question ("48 x 24 x 30 in, will it fit?" -> "will it fit?")
    question = re.sub(r"^[\s,.;:-]+|[\s,;:-]+$", "", METRIC_RE.sub("", IMPERIAL_RE.sub("", question)))
    dims = typed or item.dims.model_dump()
    if item.estimated and not typed:
        return _plain(f"I opened “{item.name}” but the listing doesn't state its size. Send width × depth × height (e.g. 48 x 24 x 30 in) with the link and I'll check it.")
    await ctx.repo.update("furniture", item.id, {"dims": dims, "estimated": False, "dimensionsConfirmed": True})
    source = "you gave" if typed else "listed"
    out = await pipeline.run(ctx, request_text=question or DEFAULT_FIT_QUESTION, user_id=user_id, room_id=body.roomId,
                             base_layout_id=body.baseLayoutId, furniture_id=item.id, channel=body.channel)
    size = f"{item.name} is {_size(dims)} ({source})."
    if out.status == "ok":
        return _response(out, f"Yes, it fits. {size} {out.reply}")
    if out.status == "rejected":
        return _response(out, f"No, it won't fit as the room is now. {size} {out.reply}")
    return _response(out, f"{size} {out.reply}")


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
