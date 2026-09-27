"""Attributed housing sources. Live failures never fall back to fixtures."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.config import REPO_ROOT, Settings
from app.housing_models import BuildingRecord, HousingProfile, RentalComparable, SourceInfo

HPD_URL = "https://data.cityofnewyork.us/Housing-Development/Housing-Maintenance-Code-Violations/wvxf-dwi5"
RODENT_URL = "https://data.cityofnewyork.us/Health/Rodent-Inspection/p937-wjvj"
RENTCAST_URL = "https://developers.rentcast.io/reference/rental-listings-long-term"
GEO_URL = "https://geosearch.planninglabs.nyc/docs/"
_cache: dict[str, tuple[float, Any]] = {}


def source(name: str, status: str, url: str, note: str = "", observed: str | None = None) -> SourceInfo:
    return SourceInfo(source=name, status=status, url=url, retrievedAt=datetime.now(UTC), observedAt=observed, note=note)  # type: ignore[arg-type]


async def get_json(url: str, params: dict | None = None, headers: dict | None = None) -> Any:
    # Keys never include credentials. Providers here have fixed public hosts.
    key = url + json.dumps(params or {}, sort_keys=True)
    cached = _cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    if len(_cache) >= 256:
        _cache.clear()
    _cache[key] = (time.monotonic() + 3600, data)
    return data


async def addresses(query: str, demo: bool) -> dict:
    if demo:
        return {"candidates": [{"label": "Synthetic NYC demo address", "bbl": "1000010001", "bin": "1000001", "latitude": 40.811, "longitude": -73.954}],
                "source": source("NYC GeoSearch", "demo", GEO_URL, "Synthetic address; not a real property lookup.").model_dump(mode="json")}
    try:
        data = await get_json("https://geosearch.planninglabs.nyc/v2/search", {"text": query, "size": 5})
        candidates = []
        for item in data.get("features", []):
            props = item["properties"]
            pad = props.get("addendum", {}).get("pad", {})
            candidates.append({"label": props.get("label", query), "bbl": str(pad.get("bbl", "")) or None,
                               "bin": str(pad.get("bin", "")) or None, "longitude": item["geometry"]["coordinates"][0],
                               "latitude": item["geometry"]["coordinates"][1]})
        return {"candidates": candidates, "source": source("NYC GeoSearch", "available", GEO_URL).model_dump(mode="json")}
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return {"candidates": [], "source": source("NYC GeoSearch", "unavailable", GEO_URL, "Address service unavailable. No match was assumed.").model_dump(mode="json")}


def demo_comparables() -> list[RentalComparable]:
    data = json.loads((REPO_ROOT / "fixtures/housing/comparables.json").read_text())
    today = date.today()
    results = []
    for row in data["comparables"]:
        doc = dict(row)
        doc["observedAt"] = (today - timedelta(days=doc.pop("daysAgo"))).isoformat()
        doc["conditions"] = [{**c, "observedAt": doc["observedAt"]} for c in doc.get("conditions", [])]
        results.append(RentalComparable.model_validate(doc))
    return results


async def rental_candidates(settings: Settings, profile: HousingProfile) -> tuple[list[RentalComparable], SourceInfo]:
    if profile.dataMode == "demo":
        return demo_comparables(), source("Synthetic comparables", "demo", "https://example.invalid/synthetic-rentals", "Invented listings for demonstration. Dates are relative to the demo run; not market evidence.")
    if profile.occupancyType in ("private_room", "shared_room"):
        return [], source("RentCast", "not_applicable", RENTCAST_URL, "Private rooms require user-entered or authorized room-level comparables.")
    if not settings.rentcast_api_key:
        return [], source("RentCast", "unavailable", RENTCAST_URL, "RENTCAST_API_KEY is not configured. Add documented comparables manually.")
    if profile.latitude is None or profile.longitude is None:
        return [], source("RentCast", "unavailable", RENTCAST_URL, "Select an address before searching nearby listings.")
    try:
        rows = await get_json("https://api.rentcast.io/v1/listings/rental/long-term", {
            "latitude": profile.latitude, "longitude": profile.longitude, "radius": 1, "status": "Active", "limit": 100,
            "propertyType": "Apartment", "bedrooms": profile.bedrooms if profile.bedrooms is not None else 0,
        }, {"X-Api-Key": settings.rentcast_api_key})
        results = []
        for r in rows:
            if not all(r.get(k) is not None for k in ("price", "squareFootage", "latitude", "longitude", "lastSeenDate")):
                continue
            try:
                results.append(RentalComparable(
                    id=str(r["id"]), unitKey=str(r.get("formattedAddress") or r["id"]),
                    sourceUrl=r.get("listingUrl") or RENTCAST_URL, observedAt=r["lastSeenDate"][:10],
                    occupancyType="studio" if r.get("bedrooms") == 0 else "whole_apartment",
                    rentCents=round(r["price"] * 100), areaSqFt=r["squareFootage"], areaConfirmed=False,
                    latitude=r["latitude"], longitude=r["longitude"], bedrooms=r.get("bedrooms"), bathrooms=r.get("bathrooms"),
                    leaseMonths=None, furnished=None, utilitiesIncluded=None, provenance="rentcast",
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return results, source("RentCast", "available", RENTCAST_URL, "Confirm listing area, lease duration, furnishing and utilities individually before inclusion. Provider does not establish condition evidence.")
    except (httpx.HTTPError, TypeError, ValueError):
        return [], source("RentCast", "unavailable", RENTCAST_URL, "Rental provider unavailable. No demo data substituted.")


async def building_records(profile: HousingProfile) -> tuple[list[BuildingRecord], list[SourceInfo]]:
    if profile.dataMode == "demo":
        now = date.today().isoformat()
        return [BuildingRecord(id="demo-violation", kind="violation", scope="building", summary="Synthetic report: water leak in common hallway", status="Open", severity="B", observedAt=now, sourceUrl=HPD_URL, bbl="1000010001", demo=True),
                BuildingRecord(id="demo-rodent", kind="inspection", scope="building", summary="Synthetic rodent inspection: signs observed on property", status="Rat activity", severity="inspection finding", observedAt=now, sourceUrl=RODENT_URL, bbl="1000010001", demo=True)], [source("NYC records", "demo", HPD_URL, "Synthetic property records; no claim about a real building.")]
    if not profile.bbl:
        return [], [source("NYC records", "unavailable", HPD_URL, "Select a matched property with a BBL. ZIP codes cannot identify building conditions.")]

    async def fetch(dataset: str, label: str, url: str, order: str) -> tuple[list, SourceInfo]:
        try:
            # bbl is constrained to exactly 10 digits by the input contract.
            rows = await get_json(f"https://data.cityofnewyork.us/resource/{dataset}.json", {"$where": f"bbl='{profile.bbl}'", "$limit": 200, "$order": order})
            records = []
            for r in rows:
                if profile.bin and r.get("bin") and str(r["bin"]) != profile.bin:
                    continue
                apt = r.get("apartment")
                is_unit = bool(apt and profile.apartment and apt.strip().casefold() == profile.apartment.strip().casefold())
                if dataset == "wvxf-dwi5":
                    records.append(BuildingRecord(id=str(r["violationid"]), kind="violation", scope="unit" if is_unit else "building", summary=r.get("novdescription", "Housing violation"), status=r.get("violationstatus", "Unknown") + ": " + r.get("currentstatus", ""), severity=r.get("class", "Unknown"), observedAt=r.get("inspectiondate") or r.get("novissueddate", "Unknown"), sourceUrl=url, bbl=profile.bbl, apartment=apt))
                else:
                    records.append(BuildingRecord(id=str(r.get("job_id", "")) + str(r.get("inspection_date", "")), kind="inspection", scope="building", summary=r.get("result", "Inspection") + ": " + r.get("observations", ""), status=r.get("result", "Unknown"), severity="inspection finding", observedAt=r.get("inspection_date", "Unknown"), sourceUrl=url, bbl=profile.bbl))
            return records, source(label, "available", url, "Latest 200 records for this property. Missing records do not establish absence of problems.")
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return [], source(label, "unavailable", url, "Source unavailable; condition is unknown, not clear.")

    results = await asyncio.gather(fetch("wvxf-dwi5", "HPD violations", HPD_URL, "inspectiondate DESC"), fetch("p937-wjvj", "Rodent inspections", RODENT_URL, "inspection_date DESC"))
    return [r for rows, _ in results for r in rows], [s for _, s in results]


def benchmarks(profile: HousingProfile) -> tuple[list[dict], list[SourceInfo]]:
    """Curated snapshots, never a scraper or an undocumented valuation fallback."""
    values, sources = [], []
    for name, url in (("StreetEasy", "https://streeteasy.com/blog/data-dashboard/"), ("HUD SAFMR", "https://www.huduser.gov/portal/datasets/fmr/smallarea/index.html")):
        path = REPO_ROOT / "fixtures/housing/benchmarks.json"
        rows = json.loads(path.read_text()).get("benchmarks", []) if path.exists() else []
        rows = [r for r in rows if r.get("source") == name and r.get("zip") == profile.zip and r.get("mode") == profile.dataMode and r.get("permittedUse")]
        values.extend(rows)
        sources.append(source(name, "demo" if rows and profile.dataMode == "demo" else "available" if rows else "unavailable", url, "Context only, never a room valuation. " + ("Snapshot available." if rows else "No permitted snapshot loaded for this location.")))
    return values, sources
