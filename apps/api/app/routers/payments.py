"""User-reviewed quotes, test checkout, authenticated receipts and signed webhooks."""
from datetime import UTC, datetime, timedelta
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from app.deps import AppContext, get_ctx, raw_ctx
from app.housing_models import Contract, QuoteRequest
from app.payment_ledger import PaymentLedger
from app.payments import StripeTest
from app.routers.rent import ensure_room

router = APIRouter(tags=["payments"])


def ledger(ctx: AppContext) -> PaymentLedger:
    mode = "test" if ctx.settings.payments_mode == "stripe_test" and ctx.principal and ctx.principal.authenticated else "demo"
    return PaymentLedger(ctx.settings, mode)


class SeedBody(Contract):
    roomId: str


class CheckoutBody(Contract):
    quoteId: str
    confirmed: bool


@router.post("/payments/test-tenancy", status_code=201)
async def seed_tenancy(body: SeedBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    await ensure_room(ctx, body.roomId)
    user = await ctx.demo_user()
    db = ledger(ctx)
    if db.mode == "test":
        StripeTest(ctx.settings).ensure_configured()
    tenancy = await run_in_threadpool(db.seed, user.id, body.roomId)
    return {"tenancy": tenancy.model_dump(mode="json"), "notice": "Fictional $1,600 tenancy and $18 documented screening cost. This does not verify a real lease or landlord."}


@router.post("/payments/quote", status_code=201)
async def quote(body: QuoteRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    q = await run_in_threadpool(ledger(ctx).quote, user.id, body)
    return {"quote": q.model_dump(mode="json")}


@router.post("/payments/checkout")
async def checkout(body: CheckoutBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    if not body.confirmed:
        raise HTTPException(409, "Review the itemized quote and explicitly continue")
    user = await ctx.demo_user()
    db = ledger(ctx)
    if db.mode == "test":
        StripeTest(ctx.settings).ensure_configured()
    payment = await run_in_threadpool(db.reserve, user.id, body.quoteId)
    if payment["status"] == "created":
        if datetime.fromisoformat(payment["createdAt"]) < datetime.now(UTC) - timedelta(hours=20):
            raise HTTPException(409, "This uncertain checkout needs reconciliation before retrying; no new charge was created")
        if db.mode == "test":
            q = await run_in_threadpool(db.get_quote, user.id, body.quoteId)
            session = await StripeTest(ctx.settings).checkout(payment, q)
        else:
            session = {"id": "demo_" + payment["id"], "url": f"{ctx.settings.public_web_url}/payment/{payment['id']}"}
        payment = await run_in_threadpool(db.attach_session, payment["id"], session)
    return {"payment": payment, "url": payment["checkoutUrl"] if payment["status"] == "pending" else None}


@router.get("/payments")
async def history(roomId: str | None = None, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    if roomId:
        await ensure_room(ctx, roomId)
    return {"payments": await run_in_threadpool(ledger(ctx).list, user.id, roomId)}


@router.get("/payments/{payment_id}")
async def payment_status(payment_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    user = await ctx.demo_user()
    return {"payment": await run_in_threadpool(ledger(ctx).get, payment_id, user.id)}


class DemoOutcome(Contract):
    outcome: str = Field(pattern="^(succeeded|failed|canceled|refunded|disputed)$")


@router.post("/payments/{payment_id}/simulate")
async def simulate(payment_id: str, body: DemoOutcome, ctx: AppContext = Depends(get_ctx)) -> dict:
    db = ledger(ctx)
    if db.mode != "demo":
        raise HTTPException(403, "Simulation cannot change Stripe test payments")
    user = await ctx.demo_user()
    p = await run_in_threadpool(db.get, payment_id, user.id)
    if p["mode"] != "demo" or p["status"] == "created":
        raise HTTPException(409, "Complete demo checkout review first")
    return {"payment": await run_in_threadpool(db.apply_event, f"demo-{payment_id}-{body.outcome}", payment_id, body.outcome, refunded=p["amountCents"] if body.outcome == "refunded" else 0)}


@router.post("/payments/supabase-sync", status_code=410)
async def old_sync() -> dict:
    return {"message": "Legacy record-only endpoint retired. Payment state comes from the transactional ledger."}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, ctx: AppContext = Depends(raw_ctx)) -> dict:
    import stripe
    secret = ctx.settings.stripe_webhook_secret
    if not secret or ctx.settings.payments_mode != "stripe_test":
        raise HTTPException(503, "Stripe test webhook is not configured")
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(413, "Event too large")
    try:
        event = stripe.Webhook.construct_event(raw, request.headers.get("stripe-signature", ""), secret, tolerance=300)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(400, "Invalid webhook signature") from exc
    if event.get("livemode") is not False or event.get("account") != ctx.settings.stripe_connected_account:
        raise HTTPException(400, "Unexpected account or live event")
    kind = event["type"]
    if not kind.startswith(("checkout.session.", "payment_intent.", "charge.")):
        return {"received": True, "ignored": True}
    obj = event["data"]["object"]
    adapter = StripeTest(ctx.settings)
    intent_id = obj.get("payment_intent") if not kind.startswith("payment_intent.") else obj.get("id")
    if kind.startswith("charge.dispute.") and not intent_id:
        charge = await adapter.request("GET", "charges/" + obj["charge"])
        intent_id = charge.get("payment_intent")
    payment_id = obj.get("metadata", {}).get("payment_id") or obj.get("client_reference_id")
    intent = None
    if intent_id:
        if not re.fullmatch(r"pi_[A-Za-z0-9]+", intent_id):
            raise HTTPException(400, "Invalid payment intent")
        intent = await adapter.request("GET", f"payment_intents/{intent_id}?expand[]=latest_charge")
        payment_id = intent.get("metadata", {}).get("payment_id")
    if not payment_id:
        return {"received": True, "ignored": True}
    db = PaymentLedger(ctx.settings, "test")
    p = await run_in_threadpool(db.get, payment_id)
    if p["recipientId"] != event["account"]:
        raise HTTPException(400, "Recipient mismatch")
    status, refunded = "pending", 0
    if intent:
        if intent["amount"] != p["amountCents"] or intent["currency"] != p["currency"]:
            raise HTTPException(400, "Payment amount or currency mismatch")
        state = intent["status"]
        status = {"succeeded": "succeeded", "canceled": "canceled"}.get(state, "pending")
        # A declined card is retryable within Checkout: keep its cap reservation until session expiration.
        charge = intent.get("latest_charge")
        if isinstance(charge, dict):
            refunded = charge.get("amount_refunded", 0)
            if refunded >= p["amountCents"]:
                status = "refunded"
            if charge.get("disputed") or kind.startswith("charge.dispute."):
                status = "disputed"
    if kind == "checkout.session.expired":
        session = await adapter.request("GET", "checkout/sessions/" + obj["id"])
        if session.get("client_reference_id") != p["id"] or session.get("amount_total") != p["amountCents"] or session.get("currency") != "usd":
            raise HTTPException(400, "Session mismatch")
        if session.get("status") == "expired" and status == "pending":
            status = "expired"
    result = await run_in_threadpool(db.apply_event, event["id"], p["id"], status, intent_id=intent_id, refunded=refunded)
    return {"received": True, "status": result["status"]}
