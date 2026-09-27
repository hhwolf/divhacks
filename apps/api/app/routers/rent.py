from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.deps import AppContext, get_ctx
from app.models import HousingProfile, PaymentPurpose
from app.rent import assess_rent, guard_payment

router = APIRouter(tags=["rent"])


class RentAssessBody(HousingProfile):
    layoutId: str | None = None


class PaymentQuoteBody(BaseModel):
    purpose: PaymentPurpose
    amount: float = Field(gt=0)
    rentAmount: float | None = None
    roomId: str | None = None
    assessmentId: str | None = None


@router.post("/rent/assess", status_code=201)
async def rent_assess(body: RentAssessBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        profile = HousingProfile.model_validate(body.model_dump(exclude={"layoutId"}))
        out = await assess_rent(ctx, profile, layout_id=body.layoutId)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"assessment": out.model_dump()}


@router.get("/rooms/{room_id}/rent-assessment")
async def latest_rent_assessment(room_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    rows = await ctx.repo.list("rent_assessments", roomId=room_id)
    if not rows:
        raise HTTPException(404, "rent assessment not found")
    return {"assessment": rows[-1]}


@router.post("/payments/quote", status_code=201)
async def payment_quote(body: PaymentQuoteBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    q = guard_payment(ctx, purpose=body.purpose, amount=body.amount, rent_amount=body.rentAmount, room_id=body.roomId, assessment_id=body.assessmentId)
    await ctx.repo.insert("payment_quotes", q.model_dump())
    return {"quote": q.model_dump()}


@router.post("/payments/checkout")
async def payment_checkout(body: PaymentQuoteBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    q = guard_payment(ctx, purpose=body.purpose, amount=body.amount, rent_amount=body.rentAmount, room_id=body.roomId, assessment_id=body.assessmentId)
    if q.status == "blocked":
        raise HTTPException(409, {"message": "payment blocked by guardrails", "guardrails": q.guardrails})
    await ctx.repo.insert("payment_quotes", q.model_dump())
    outbox = ctx.settings.data_dir / "payment_outbox.jsonl"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    with outbox.open("a") as fh:
        fh.write(q.model_dump_json() + "\n")
    return {"quote": q.model_dump(), "url": q.stripeCheckoutUrl}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None), ctx: AppContext = Depends(get_ctx)) -> dict:
    """Acknowledges only; payments are a non-goal and nothing is processed. A configured secret still demands a signature header."""
    if ctx.settings.stripe_webhook_secret is not None and not stripe_signature:
        raise HTTPException(401, "missing Stripe signature")
    payload = await request.json()
    return {"status": "ok", "mode": "ignored", "type": payload.get("type", "unknown")}
