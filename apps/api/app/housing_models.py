"""Housing evidence and payment contracts. Money in payment APIs is integer USD cents."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Occupancy = Literal["private_room", "shared_room", "studio", "whole_apartment"]
Purpose = Literal["rent_payment", "deposit", "application_fee", "screening_fee", "broker_fee", "other", "furniture_purchase"]


class ConditionObservation(Contract):
    category: Literal["insects", "rodents", "leaks", "plumbing", "heat_hot_water", "other"]
    status: Literal["ongoing", "resolved", "unknown"] = "ongoing"
    severity: Literal["minor", "moderate", "severe", "unknown"] = "unknown"
    observedAt: date
    source: Literal["user", "photo", "public_record"] = "user"
    scope: Literal["unit", "building", "area"] = "unit"
    note: str = Field(default="", max_length=1000)
    photoIds: list[str] = Field(default_factory=list, max_length=10)


class SourceInfo(Contract):
    source: str
    status: Literal["demo", "available", "unavailable", "not_applicable"]
    url: str
    retrievedAt: datetime
    observedAt: str | None = None
    note: str = ""
    permittedUse: str = "Display with attribution; review provider terms before redistribution."


class RentalComparable(Contract):
    id: str = Field(min_length=1, max_length=200)
    unitKey: str = Field(min_length=1, max_length=300)
    sourceUrl: HttpUrl
    observedAt: date
    occupancyType: Occupancy
    rentCents: int = Field(gt=0, le=100_000_000, strict=True)
    areaSqFt: float = Field(gt=0, le=100_000)
    areaConfirmed: bool = True
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    bathrooms: float | None = Field(default=None, ge=0, le=50)
    leaseMonths: int | None = Field(default=None, ge=1, le=120)
    furnished: bool | None = None
    utilitiesIncluded: bool | None = None
    sharedAmenities: str = Field(default="", max_length=500)
    conditionsDocumented: bool = False
    conditions: list[ConditionObservation] = Field(default_factory=list, max_length=30)
    provenance: Literal["user", "rentcast", "fixture"] = "user"


class HousingProfile(Contract):
    roomId: str
    address: str | None = Field(default=None, max_length=300)
    zip: str | None = Field(default=None, pattern=r"^\d{5}$")
    apartment: str | None = Field(default=None, max_length=30)
    bbl: str | None = Field(default=None, pattern=r"^\d{10}$")
    bin: str | None = Field(default=None, pattern=r"^\d{7}$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    askingRent: float = Field(gt=0, le=1_000_000)
    occupancyType: Occupancy = "private_room"
    scanCoverage: Literal["room", "whole_apartment"] = "room"
    measurementConfirmed: bool = False
    confirmedAreaSqFt: float | None = Field(default=None, gt=0, le=100_000)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    bathrooms: float | None = Field(default=None, ge=0, le=50)
    leaseMonths: int = Field(default=12, ge=1, le=120)
    utilitiesIncluded: bool = False
    furnished: bool = False
    conditions: list[ConditionObservation] = Field(default_factory=list, max_length=30)
    comparables: list[RentalComparable] = Field(default_factory=list, max_length=200)
    dataMode: Literal["demo", "real"] = "real"
    # Legacy inputs may be read, but never create price deductions or payment authorization.
    declaredIssues: list[str] = Field(default_factory=list, max_length=30)
    depositRequested: float | None = Field(default=None, ge=0)
    applicationFee: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together")
        return self


class BuildingRecord(Contract):
    id: str
    kind: Literal["violation", "inspection", "complaint"]
    scope: Literal["unit", "building", "area"]
    summary: str
    status: str
    severity: str
    observedAt: str
    sourceUrl: str
    bbl: str
    apartment: str | None = None
    demo: bool = False


class RentRange(Contract):
    low: int
    mid: int
    high: int


class SpaceQuality(Contract):
    floorAreaSqFt: float
    usableAreaSqFt: float
    openFloorPct: float
    ceilingHeightFt: float
    windowCount: int


class RentAssessment(Contract):
    id: str
    userId: str
    roomId: str
    layoutId: str | None = None
    profile: HousingProfile
    spaceQuality: SpaceQuality
    status: Literal["demo", "estimated", "insufficient_data", "legacy_demo"]
    methodVersion: str = "comparable-asking-rents-v1"
    estimatedFairRange: RentRange | None = None
    conditionMatchedRange: RentRange | None = None
    conditionDifference: int | None = None
    askingRent: float
    deltaVsMid: float | None = None
    pricePerSqFt: float
    comparables: list[RentalComparable]
    conditionComparableIds: list[str]
    explanation: list[str]
    sources: list[SourceInfo]
    buildingRecords: list[BuildingRecord]
    notices: list[str]
    createdAt: datetime
    updatedAt: datetime


class Tenancy(Contract):
    id: str
    userId: str
    roomId: str
    mode: Literal["demo", "test"]
    recipientId: str
    recipientName: str
    recipientVerified: bool = False
    supportedArrangement: bool = True
    leaseDocumented: bool = False
    monthlyRentCents: int = Field(gt=0, strict=True)
    screeningActualCostCents: int | None = Field(default=None, ge=0, strict=True)
    screeningDocumentsProvided: bool = False
    recentScreeningReport: bool = False
    depositAlreadyPaidCents: int = Field(default=0, ge=0, strict=True)
    screeningAlreadyPaidCents: int = Field(default=0, ge=0, strict=True)
    brokerHiredBy: Literal["landlord", "tenant", "unknown"] = "unknown"
    contact: str
    refundPolicy: str
    createdAt: datetime


class QuoteRequest(Contract):
    tenancyId: str
    purpose: Purpose
    amountCents: int = Field(gt=0, le=100_000_000, strict=True)
    rentalPeriod: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class PaymentQuote(QuoteRequest):
    id: str
    userId: str
    roomId: str
    recipientId: str
    recipientName: str
    currency: Literal["usd"] = "usd"
    mode: Literal["demo", "test"]
    decision: Literal["ready", "blocked", "needs_review"]
    reasons: list[str]
    ruleVersion: str = "nyc-residential-2026-09-26-v1"
    ruleSources: list[str]
    contact: str
    refundPolicy: str
    expiresAt: datetime
    createdAt: datetime


class PaymentRecord(Contract):
    id: str
    quoteId: str
    userId: str
    roomId: str
    tenancyId: str
    recipientId: str
    purpose: Purpose
    rentalPeriod: str
    amountCents: int
    currency: Literal["usd"] = "usd"
    mode: Literal["demo", "test"]
    status: Literal["created", "pending", "succeeded", "failed", "canceled", "expired", "refunded", "disputed"]
    sessionId: str | None = None
    paymentIntentId: str | None = None
    checkoutUrl: str | None = None
    refundedCents: int = 0
    createdAt: datetime
    updatedAt: datetime
