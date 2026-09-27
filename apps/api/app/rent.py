"""Comparable asking rents. Conditions inform matching, never arbitrary discounts."""
from __future__ import annotations

import math
import re
from datetime import date

from app.deps import AppContext
from app.dates import nyc_today
from app.housing_models import HousingProfile, RentalComparable, RentAssessment, RentRange, SpaceQuality
from app.integrations.housing import benchmarks, building_records, rental_candidates, source
from app.models import Layout, Room
from app.services import new_id, now_iso, validate_for_room

SQM_TO_SQFT = 10.7639104167


def polygon_area_sqft(poly: list[tuple[float, float]]) -> float:
    return round(abs(sum(x * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * z for i, (x, z) in enumerate(poly))) / 2 * SQM_TO_SQFT, 1)


def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a, b = math.radians(lat1), math.radians(lat2)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 3958.7613 * 2 * math.asin(min(1, math.sqrt(h)))


def eligible_comparables(profile: HousingProfile, candidates: list[RentalComparable], area: float, today: date | None = None) -> list[RentalComparable]:
    today = today or nyc_today()
    if not profile.measurementConfirmed or profile.latitude is None or profile.longitude is None:
        return []
    if profile.occupancyType in ("studio", "whole_apartment") and profile.scanCoverage != "whole_apartment":
        return []
    seen, seen_urls, results = set(), set(), []
    for c in sorted(candidates, key=lambda c: c.observedAt, reverse=True):
        key = re.sub(r"\s+", " ", c.unitKey.strip().casefold())
        url = str(c.sourceUrl).split("?")[0].rstrip("/")
        if key in seen or (url in seen_urls and c.provenance != "rentcast"):
            continue
        if c.provenance == "fixture" and profile.dataMode != "demo":
            continue
        if c.occupancyType != profile.occupancyType or not c.areaConfirmed or not .75 * area <= c.areaSqFt <= 1.25 * area:
            continue
        if not 0 <= (today - c.observedAt).days <= 90 or distance_miles(profile.latitude, profile.longitude, c.latitude, c.longitude) > 1:
            continue
        if (c.leaseMonths, c.furnished, c.utilitiesIncluded) != (profile.leaseMonths, profile.furnished, profile.utilitiesIncluded):
            continue
        if profile.occupancyType in ("studio", "whole_apartment"):
            if profile.bedrooms is None or profile.bathrooms is None or (c.bedrooms, c.bathrooms) != (profile.bedrooms, profile.bathrooms):
                continue
        seen.add(key)
        seen_urls.add(url)
        results.append(c)
        if len(results) == 25:
            break
    return results


def condition_signature(conditions: list, today: date | None = None) -> set[tuple[str, str]]:
    today = today or nyc_today()
    return {(c.category, c.severity) for c in conditions if c.scope == "unit" and c.status == "ongoing" and c.severity != "unknown" and 0 <= (today - c.observedAt).days <= 90}


def comparison_range(comps: list[RentalComparable]) -> RentRange | None:
    if len(comps) < 5:
        return None
    values = sorted(c.rentCents / 100 for c in comps)
    def quantile(p: float) -> int:
        pos = (len(values) - 1) * p
        low = math.floor(pos)
        return round(values[low] + (values[math.ceil(pos)] - values[low]) * (pos - low))
    return RentRange(low=quantile(.25), mid=quantile(.5), high=quantile(.75))


async def assess_rent(ctx: AppContext, profile: HousingProfile, layout_id: str | None = None) -> RentAssessment:
    doc = await ctx.repo.get("rooms", profile.roomId)
    if not doc:
        raise KeyError("Room not found")
    room = Room.model_validate(doc)
    layouts = await ctx.repo.list_by_room("layouts", room.id)
    layout_doc = next((l for l in layouts if l["id"] == layout_id), None) if layout_id else next((l for l in layouts if l.get("isCurrent")), None)
    if layout_id and not layout_doc:
        raise KeyError("Layout does not belong to this room")
    metrics = None
    if layout_doc:
        layout = Layout.model_validate(layout_doc)
        metrics = (await validate_for_room(ctx, room, layout.items, layout.zones)).metrics
    scanned = polygon_area_sqft(room.skeleton.floorPolygon)
    area = profile.confirmedAreaSqFt or scanned
    candidates, market_source = await rental_candidates(ctx.settings, profile)
    # The synthetic sample has an explicit synthetic location, never a real ZIP-centroid match.
    if profile.dataMode == "demo" and profile.latitude is None:
        profile = profile.model_copy(update={"latitude": 40.811, "longitude": -73.954})
    comps = eligible_comparables(profile, profile.comparables + candidates, area)
    signature = condition_signature(profile.conditions)
    def sufficient(conditions):
        ongoing = [c for c in conditions if c.scope == "unit" and c.status != "resolved"]
        return all(c.status == "ongoing" and c.severity != "unknown" and 0 <= (nyc_today() - c.observedAt).days <= 90 for c in ongoing)
    matched = [c for c in comps if c.conditionsDocumented and signature and sufficient(profile.conditions) and sufficient(c.conditions) and condition_signature(c.conditions) == signature]
    base, condition = comparison_range(comps), comparison_range(matched)
    records, sources = await building_records(profile)
    _, context_sources = benchmarks(profile)
    sources = [market_source, *sources, *context_sources]
    if profile.comparables:
        sources.append(source("User-entered comparables", "available", "https://example.invalid/user-entered", "User-reported listing details; not independently verified."))
    notices = ["Missing public records do not prove that an apartment is problem-free."]
    ongoing = [c for c in profile.conditions if c.status == "ongoing"]
    if ongoing:
        notices.append("Reported housing problems need attention regardless of rent. A lower price does not repair a leak or resolve pests. Contact the owner and NYC 311 for repair/reporting guidance.")
    explanations = [
        "Comparable asking-rent range is the middle half (25th–75th percentiles) of qualifying listings, not a confidence interval, appraisal, or legal rent.",
        "Matching defaults: same occupancy and rental terms; observed within 90 days, within one mile, area within ±25%; up to 25 distinct units.",
        "Furniture placement and free floor area never affect the rent comparison.",
        f"{len(comps)} qualifying comparables; {len(matched)} with similar documented ongoing unit-level conditions.",
    ]
    if not profile.measurementConfirmed:
        explanations.append("Confirm the floor-area measurement before comparing rent.")
    if profile.occupancyType in ("studio", "whole_apartment") and profile.scanCoverage != "whole_apartment":
        explanations.append("A partial-room scan cannot value an entire apartment. Supply confirmed whole-apartment area and coverage.")
    if not base:
        explanations.append("Insufficient comparable data: at least five matching listings are needed for a range.")
    if ongoing and not condition:
        explanations.append("These problems may affect value, but we do not have enough comparable evidence to quantify the effect.")
    if condition:
        explanations.append("Condition difference is an observed difference between comparable medians, not a proven causal discount.")
    if profile.dataMode == "demo":
        notices.insert(0, "Demo data: all rental and building examples are synthetic, not evidence about this address.")
    user = await ctx.demo_user()
    now = now_iso()
    out = RentAssessment(
        id=new_id(), userId=user.id, roomId=room.id, layoutId=layout_doc["id"] if layout_doc else None,
        profile=profile, spaceQuality=SpaceQuality(floorAreaSqFt=area, usableAreaSqFt=round(scanned * (metrics.openFloor if metrics else 100) / 100, 1), openFloorPct=metrics.openFloor if metrics else 100, ceilingHeightFt=round(room.skeleton.dimensions.h * 3.28084, 1), windowCount=len(room.skeleton.windows)),
        status="demo" if profile.dataMode == "demo" else "estimated" if base else "insufficient_data",
        estimatedFairRange=base, conditionMatchedRange=condition, conditionDifference=condition.mid - base.mid if condition and base else None,
        askingRent=profile.askingRent, deltaVsMid=round(profile.askingRent - base.mid, 2) if base else None,
        pricePerSqFt=round(profile.askingRent / area, 2), comparables=comps, conditionComparableIds=[c.id for c in matched],
        explanation=explanations, sources=sources, buildingRecords=records, notices=notices, createdAt=now, updatedAt=now,
    )
    await ctx.repo.insert("rent_assessments", out.model_dump(mode="json"))
    return out
