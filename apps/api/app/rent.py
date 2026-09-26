"""Rent reality check and guarded payment helpers.

This is an explainable estimate for a renter, not a legal rent calculation or appraisal.
Fixtures keep the demo offline; live open-data adapters can replace the loaders without changing the API.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT
from app.deps import AppContext
from app.models import (
    Confidence,
    FloorMaterial,
    HousingProfile,
    Layout,
    PaymentPurpose,
    PaymentQuote,
    RentAssessment,
    RentRange,
    Room,
    SourceBreakdown,
    SpaceQuality,
)
from app.services import new_id, now_iso, validate_for_room

FIXTURES = REPO_ROOT / "fixtures" / "housing"
SQM_TO_SQFT = 10.7639
M_TO_FT = 3.28084


def _load_json(name: str) -> dict[str, Any]:
    path = FIXTURES / name
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def polygon_area_sqft(poly: list[tuple[float, float]]) -> float:
    area = 0.0
    for i, (x1, z1) in enumerate(poly):
        x2, z2 = poly[(i + 1) % len(poly)]
        area += x1 * z2 - x2 * z1
    return round(abs(area) / 2 * SQM_TO_SQFT, 1)


def normalize_issue(issue: str) -> str:
    return issue.strip().lower().replace("-", " ")


def infer_floor_material(profile: HousingProfile) -> FloorMaterial:
    words = " ".join(normalize_issue(i) for i in profile.declaredIssues)
    for material in ("hardwood", "engineered_wood", "tile", "laminate", "concrete", "carpet", "vinyl"):
        if material.replace("_", " ") in words:
            return material  # type: ignore[return-value]
    return "unknown"


def issue_penalty(issue: str) -> tuple[int, str]:
    s = normalize_issue(issue)
    if any(w in s for w in ("rat", "rodent", "mouse", "mice", "bug", "roach", "vermin")):
        return 12, "pest issue reported"
    if any(w in s for w in ("leak", "water", "mold", "hot water", "heat")):
        return 11, "water/heat habitability issue reported"
    if any(w in s for w in ("faucet", "plumbing", "toilet", "sink")):
        return 8, "plumbing fixture issue reported"
    if any(w in s for w in ("floor damage", "worn floor", "soft floor", "broken floor")):
        return 7, "floor condition issue reported"
    if any(w in s for w in ("noise", "dark", "windowless")):
        return 4, "livability issue reported"
    return 2, f"{issue.strip()} reported"


async def _layout_for_room(ctx: AppContext, room_id: str, layout_id: str | None) -> Layout | None:
    if layout_id:
        doc = await ctx.repo.get("layouts", layout_id)
        return Layout.model_validate(doc) if doc else None
    layouts = await ctx.repo.list_by_room("layouts", room_id)
    current = next((l for l in layouts if l.get("isCurrent")), layouts[0] if layouts else None)
    return Layout.model_validate(current) if current else None


def _market(profile: HousingProfile) -> tuple[dict[str, Any], dict[str, Any]]:
    rents = _load_json("market_rents.json")
    signals = _load_json("building_signals.json")
    key = profile.zip or "default"
    return dict(rents.get(key) or rents.get("default") or {}), dict(signals.get(key) or signals.get("default") or {})


def _base_market_rent(profile: HousingProfile, market: dict[str, Any]) -> float:
    if profile.occupancyType == "studio":
        return float(market.get("studioMid") or market.get("hudFmr0") or 2470)
    if profile.occupancyType == "whole_apartment":
        return float(market.get("oneBedroomMid") if profile.bedrooms else market.get("studioMid") or market.get("hudFmr0") or 2470)
    if profile.occupancyType == "shared_room":
        return float(market.get("sharedRoomMid") or 900)
    return float(market.get("privateRoomMid") or 1300)


def _space_adjustment(profile: HousingProfile, floor_sqft: float, market: dict[str, Any]) -> float:
    if profile.occupancyType in ("private_room", "shared_room"):
        baseline = float(market.get("baselinePrivateSqFt") or 115)
        return max(-180, min(220, (floor_sqft - baseline) * 4.2))
    return max(-350, min(450, (floor_sqft - 420) * 1.15))


def _condition_adjustment(score: int) -> float:
    return (score - 80) * 7.5


async def assess_rent(ctx: AppContext, profile: HousingProfile, layout_id: str | None = None) -> RentAssessment:
    room_doc = await ctx.repo.get("rooms", profile.roomId)
    if room_doc is None:
        raise KeyError("room not found")
    room = Room.model_validate(room_doc)
    layout = await _layout_for_room(ctx, profile.roomId, layout_id)
    validation = await validate_for_room(ctx, room, layout.items, layout.zones) if layout else None
    metrics = validation.metrics if validation else None
    open_floor = float(metrics.openFloor if metrics else 100)

    market, signals = _market(profile)
    material = infer_floor_material(profile)
    material_table = _load_json("material_quality.json")
    material_info = dict(material_table.get(material) or material_table.get("unknown") or {"score": 0, "confidence": "low"})

    penalties: list[str] = []
    penalty_points = 0
    seen_penalties: set[str] = set()
    for issue in profile.declaredIssues:
        pts, label = issue_penalty(issue)
        penalty_points += pts
        if label not in seen_penalties:
            penalties.append(label)
            seen_penalties.add(label)

    hpd = int(signals.get("openHpdViolations") or 0)
    class_c = int(signals.get("classCViolations") or 0)
    rodents = int(signals.get("rodentInspectionFailures") or 0)
    complaints = int(signals.get("recent311Housing") or 0)
    penalty_points += min(16, hpd * 2 + class_c * 4 + rodents * 5 + complaints)

    floor_area = polygon_area_sqft(room.skeleton.floorPolygon)
    usable_area = round(floor_area * max(0, min(100, open_floor)) / 100, 1)
    condition = max(20, min(100, 80 + int(material_info.get("score", 0)) - penalty_points))
    space = SpaceQuality(
        floorAreaSqFt=floor_area,
        usableAreaSqFt=usable_area,
        openFloorPct=round(open_floor, 1),
        ceilingHeightFt=round(room.skeleton.dimensions.h * M_TO_FT, 1),
        windowCount=len(room.skeleton.windows),
        floorMaterial=material,
        materialConfidence=material_info.get("confidence", "low"),
        conditionScore=condition,
        issuePenalties=penalties,
    )

    base = _base_market_rent(profile, market)
    mid = base + _space_adjustment(profile, floor_area, market) + _condition_adjustment(condition)
    if metrics and metrics.walkability == "Blocked":
        mid -= 90
    elif metrics and metrics.walkability == "Tight":
        mid -= 35
    mid = max(400, mid)
    spread = 0.11 if profile.zip and layout else 0.18
    fair = RentRange(low=round(mid * (1 - spread)), mid=round(mid), high=round(mid * (1 + spread)))

    legal_flags: list[str] = []
    if profile.depositRequested is not None and profile.depositRequested > profile.askingRent + 0.01:
        legal_flags.append("Security deposit is above one month of rent; block payment until corrected.")
    if profile.applicationFee is not None and profile.applicationFee > 20:
        legal_flags.append("Application fee is above the New York $20 cap; do not pay through the app.")
    if signals.get("rentStabilizedBuildingSignal"):
        legal_flags.append("Building-level rent-stabilization signal found; this does not prove your specific unit is stabilized. Request rent history from HCR.")
    if any("source of income" in normalize_issue(i) or "voucher" in normalize_issue(i) for i in profile.declaredIssues):
        legal_flags.append("Source-of-income/voucher language detected; review NYC fair-housing protections before proceeding.")

    health = list(signals.get("signals") or [])
    explanation = [
        f"Measured room area from the scanned floor polygon: {floor_area} sq ft, with {usable_area} sq ft currently usable.",
        f"Started from {market.get('neighborhood', 'NYC')} {profile.occupancyType.replace('_', ' ')} baseline ${round(base)}/mo.",
        f"Adjusted for room size, open floor, walkability and condition score {condition}/100.",
        "This is an estimated fair range, not a legal regulated rent or appraisal.",
    ]
    if penalties:
        explanation.append("Condition deductions: " + "; ".join(penalties) + ".")
    if profile.askingRent > fair.high:
        explanation.append("The asking rent is above the top of the estimated range.")
    elif profile.askingRent < fair.low:
        explanation.append("The asking rent is below the estimated range; verify fees and building condition.")
    else:
        explanation.append("The asking rent falls inside the estimated range.")

    sources = [
        SourceBreakdown(source="space", label="scanned floor area", value=f"{floor_area} sq ft"),
        SourceBreakdown(source="market", label=market.get("source", "market rent fixture"), value=f"${round(base)}/mo baseline"),
        SourceBreakdown(source="materials", label=material_info.get("label", material), value=f"condition {condition}/100"),
        SourceBreakdown(source="nyc_open_data", label="HPD/311/rodent signals", value=f"{hpd} HPD, {complaints} 311, {rodents} rodent"),
    ]
    confidence: Confidence = "high" if profile.address and profile.zip and layout else "medium" if profile.zip else "low"
    now = now_iso()
    out = RentAssessment(
        id=new_id(),
        roomId=profile.roomId,
        layoutId=layout.id if layout else layout_id,
        profile=profile,
        spaceQuality=space,
        estimatedFairRange=fair,
        askingRent=profile.askingRent,
        deltaVsMid=round(profile.askingRent - fair.mid, 2),
        pricePerSqFt=round(profile.askingRent / floor_area, 2) if floor_area else 0,
        confidence=confidence,
        explanation=explanation,
        sourceBreakdown=sources,
        legalFlags=legal_flags,
        buildingHealthSignals=health,
        createdAt=now,
        updatedAt=now,
    )
    await ctx.repo.insert("rent_assessments", out.model_dump())
    return out


def guard_payment(ctx: AppContext, *, purpose: PaymentPurpose, amount: float, rent_amount: float | None = None, room_id: str | None = None, assessment_id: str | None = None) -> PaymentQuote:
    guards: list[str] = ["Supabase records this guarded payment quote only; no card, bank, escrow, wire, crypto or cash transfer is processed here."]
    status = "mock"
    if amount <= 0:
        guards.append("Amount must be greater than $0.")
        status = "blocked"
    if purpose == "deposit":
        if rent_amount is None:
            guards.append("Enter monthly rent before paying a deposit so the one-month cap can be checked.")
            status = "blocked"
        elif amount > rent_amount + 0.01:
            guards.append("Blocked: New York security deposits cannot exceed one month of rent.")
            status = "blocked"
        else:
            guards.append("Deposit is within the one-month rent cap.")
    elif purpose == "application_fee":
        if amount > 20:
            guards.append("Blocked: New York apartment application/credit-check fees are capped at $20.")
            status = "blocked"
        else:
            guards.append("Application fee is at or below the $20 cap.")
    elif purpose == "rent_payment":
        guards.append("Rent payment record only: verify landlord identity and lease terms before paying outside the app.")
    else:
        guards.append("Furniture purchase prototype: no escrow or cash-transfer protection is provided.")

    now = now_iso()
    q = PaymentQuote(
        id=new_id(),
        roomId=room_id,
        assessmentId=assessment_id,
        purpose=purpose,
        amount=round(amount, 2),
        rentAmount=rent_amount,
        status=status,  # type: ignore[arg-type]
        guardrails=guards,
        checkoutUrl=None,
        paymentRecordId=None,
        createdAt=now,
        updatedAt=now,
    )
    if status == "mock":
        q.paymentRecordId = f"pay_mock_{q.id}"
        q.checkoutUrl = f"{ctx.settings.public_web_url}/payment/{q.id}?mode=record"
    return q
