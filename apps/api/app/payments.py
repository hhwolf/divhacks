"""Versioned NYC rental checks and a test-only Stripe adapter. No AI authorizes payments."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import Settings
from app.housing_models import PaymentQuote, QuoteRequest, Tenancy
from app.services import new_id

RULE_SOURCES = [
    "https://ag.ny.gov/publications/residential-tenants-rights-guide",
    "https://www.nysenate.gov/legislation/laws/RPP/238-A",
    "https://www.nyc.gov/site/dca/about/FAQ-Broker-Fees.page",
]


def check_payment(t: Tenancy, request: QuoteRequest, totals: dict[str, int]) -> tuple[str, list[str]]:
    reasons, blocked, review = [], False, False
    if not t.recipientVerified or not t.supportedArrangement:
        review = True
        reasons.append("Recipient authority or rental arrangement needs review.")
    if request.purpose in ("rent_payment", "deposit") and not t.leaseDocumented:
        review = True
        reasons.append("Documented tenancy rent is required; an asking-rent estimate cannot authorize payment.")
    if request.purpose == "deposit":
        total = t.depositAlreadyPaidCents + totals.get("deposit", 0) + request.amountCents
        blocked = total > t.monthlyRentCents
        reasons.append("Deposit exceeds one month of documented rent, including previous and pending payments." if blocked else "Deposit fits within the one-month limit including recorded and pending payments.")
        reasons.append("Deposit trust-account and custody obligations are separate from payment processing.")
    elif request.purpose == "screening_fee":
        if t.recentScreeningReport:
            blocked = True
            reasons.append("A qualifying background/credit report from the past 30 days requires the screening fee to be waived.")
        elif t.screeningActualCostCents is None or not t.screeningDocumentsProvided:
            review = True
            reasons.append("Provide the screening report and vendor receipt/invoice before collecting reimbursement.")
        else:
            limit = min(2000, t.screeningActualCostCents)
            blocked = t.screeningAlreadyPaidCents + totals.get("screening_fee", 0) + request.amountCents > limit
            reasons.append("Screening charges exceed the lesser of documented actual cost or $20, including prior and pending payments." if blocked else "Screening reimbursement is within documented actual cost and the cumulative $20 cap.")
    elif request.purpose == "application_fee":
        blocked = True
        reasons.append("Generic application-processing fees are not permitted for supported ordinary residential rentals. A documented credit/background check is a separate purpose.")
    elif request.purpose == "broker_fee":
        if t.brokerHiredBy == "landlord":
            blocked = True
            reasons.append("NYC FARE Act: a landlord/listing agent's broker fee cannot be passed to the tenant.")
        else:
            review = True
            reasons.append("An independently hired tenant broker requires agreement and service review before payment.")
    elif request.purpose == "rent_payment":
        blocked = totals.get("rent_payment", 0) + request.amountCents > t.monthlyRentCents
        reasons.append("This amount exceeds the remaining recorded rent for this period." if blocked else "Rent amount is within the documented amount for this period; market and condition findings are advisory.")
    else:
        review = True
        reasons.append("Furniture purchases happen on the seller's site; unknown charges require review.")
    reasons.append("Passing these checks does not guarantee a legitimate recipient or transaction.")
    return "blocked" if blocked else "needs_review" if review else "ready", reasons


def make_quote(t: Tenancy, request: QuoteRequest, totals: dict[str, int]) -> PaymentQuote:
    decision, reasons = check_payment(t, request, totals)
    now = datetime.now(UTC)
    return PaymentQuote(**request.model_dump(), id=new_id(), userId=t.userId, roomId=t.roomId,
                        recipientId=t.recipientId, recipientName=t.recipientName, mode=t.mode,
                        decision=decision, reasons=reasons, ruleSources=RULE_SOURCES, contact=t.contact,
                        refundPolicy=t.refundPolicy, expiresAt=now + timedelta(minutes=30), createdAt=now)


class StripeTest:
    def __init__(self, settings: Settings):
        self.settings = settings

    def ensure_configured(self) -> None:
        s = self.settings
        if not s.stripe_secret_key.startswith("sk_test_"):
            raise HTTPException(503, "Stripe test key is required; live keys are never accepted")
        if not s.stripe_connected_account.startswith("acct_") or not s.payments_database_url:
            raise HTTPException(503, "Configure a connected test account and transactional Postgres ledger")

    async def request(self, method: str, path: str, data: dict | None = None, idempotency: str | None = None) -> dict[str, Any]:
        self.ensure_configured()
        headers = {"Stripe-Account": self.settings.stripe_connected_account}
        if idempotency:
            headers["Idempotency-Key"] = idempotency
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.request(method, "https://api.stripe.com/v1/" + path, data=data,
                                           auth=(self.settings.stripe_secret_key, ""), headers=headers)
            res.raise_for_status()
            result = res.json()
            if result.get("livemode") is True:
                raise HTTPException(409, "Live Stripe objects are not supported")
            return result
        except httpx.HTTPError as exc:
            raise HTTPException(503, "Stripe test service unavailable. Retry the same quote; do not create another payment.") from exc

    async def checkout(self, payment: dict, quote: dict) -> dict:
        data = {
            "mode": "payment", "payment_method_types[0]": "card",
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][unit_amount]": str(payment["amountCents"]),
            "line_items[0][price_data][product_data][name]": f"TEST {payment['purpose']} {payment['rentalPeriod']} — {quote['recipientName']}",
            "line_items[0][quantity]": "1", "client_reference_id": payment["id"],
            "metadata[payment_id]": payment["id"], "payment_intent_data[metadata][payment_id]": payment["id"],
            "success_url": f"{self.settings.public_web_url}/payment/{payment['id']}",
            "cancel_url": f"{self.settings.public_web_url}/payment/{payment['id']}?canceled=1",
        }
        return await self.request("POST", "checkout/sessions", data, "arp-test-" + payment["id"])
