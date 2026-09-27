"""Pydantic models mirroring packages/contracts/schemas/*.json. Field names are camelCase to match the wire shape."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Rotation = Literal[0, 90, 180, 270]
FurnitureCategory = Literal["bed", "desk", "seating", "storage", "table", "decor", "divider", "imported"]
FurnitureKind = Literal["bed", "desk", "wardrobe", "dresser", "storage", "seating", "table", "decor", "floor"]
FurnitureSource = Literal["preset", "link", "photo", "manual", "scan"]
Walkability = Literal["Good", "Tight", "Blocked"]
Severity = Literal["error", "warning"]
RuleId = Literal["bounds", "overlap", "locked", "door_clearance", "window_keep_clear", "access_edge", "clear_zone", "walkable_path"]
Intent = Literal["fit_item", "make_space", "keep_clear", "compare", "redesign", "answer", "rent_check", "payment_check", "housing_quality", "clarify"]
Channel = Literal["app", "imessage"]
OccupancyType = Literal["whole_apartment", "studio", "private_room", "shared_room"]
FloorMaterial = Literal["hardwood", "engineered_wood", "tile", "laminate", "concrete", "carpet", "vinyl", "unknown"]
Confidence = Literal["high", "medium", "low"]
PaymentPurpose = Literal["rent_payment", "deposit", "application_fee", "furniture_purchase"]
PaymentStatus = Literal["mock", "ready", "blocked", "paid_test"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class WallSegment(Strict):
    x1: float
    z1: float
    x2: float
    z2: float
    height: float = Field(ge=1.5, le=6)


class Door(Strict):
    wall: int = Field(ge=0)
    offset: float = Field(ge=0)
    width: float = Field(ge=0.5, le=2.5)
    height: float = 2.0
    swing: Literal["in", "out"]
    hinge: Literal["left", "right"]


class Window(Strict):
    wall: int = Field(ge=0)
    offset: float = Field(ge=0)
    width: float = Field(ge=0.3)
    sillHeight: float = Field(ge=0)
    height: float = Field(ge=0.3)


class Outlet(Loose):
    wall: int
    offset: float


class Dimensions(Strict):
    l: float
    w: float
    h: float


class RoomSkeleton(Strict):
    walls: list[WallSegment] = Field(min_length=3)
    doors: list[Door]
    windows: list[Window]
    floorPolygon: list[tuple[float, float]] = Field(min_length=3)
    dimensions: Dimensions
    outlets: list[Outlet] = []


class RoomElement(Loose):
    """Something the user says the space needs (bed, desk, yoga zone…); `furnitureIds` are the catalog items that satisfy it."""

    id: str
    label: str
    furnitureIds: list[str] = []
    custom: bool = False
    zone: dict[str, float] | None = None  # e.g. {"w": 1.8, "d": 1.2} for clear-floor elements like a yoga zone


class Room(Loose):
    id: str
    userId: str | None = None
    name: str
    skeleton: RoomSkeleton
    source: Literal["scan", "manual", "sample"]
    supersedesRoomId: str | None = None
    createdAt: str
    spaceTypes: list[str] = []
    elements: list[RoomElement] = []
    detectedObjects: list[dict[str, Any]] = []  # RoomPlan-detected furniture kept aside when the room is created clean


class Dims(Strict):
    w: float = Field(gt=0)
    d: float = Field(gt=0)
    h: float = Field(ge=0)


class FurnitureRef(Loose):
    """The subset of FurnitureItem the validator needs (matches fixtures/validation furniture entries)."""

    id: str
    name: str
    kind: FurnitureKind
    dims: Dims


class FurnitureItem(FurnitureRef):
    userId: str | None = None
    category: FurnitureCategory
    glbUrl: str | None = None
    thumbUrl: str | None = None
    source: FurnitureSource
    sourceUrl: str | None = None
    price: float | None = None
    color: str | None = None
    estimated: bool = False
    dimensionsConfirmed: bool = False
    deliveryCost: float = Field(default=0, ge=0)
    frontAxis: Literal["+z", "-z", "+x", "-x"] = "+z"


class LayoutItem(Loose):
    id: str
    furnitureId: str
    x: float
    z: float
    rotation: Rotation
    locked: bool
    color: str | None = None


class Zone(Loose):
    label: str
    x: float
    z: float
    w: float
    d: float


class FreeRect(BaseModel):
    x: float
    z: float
    w: float
    d: float
    areaM2: float
    fits: str


class LayoutMetrics(BaseModel):
    openFloor: float
    conflicts: int
    walkability: Walkability
    reachableStorage: float
    largestFreeRect: FreeRect | None


class Layout(Loose):
    id: str
    roomId: str
    name: str = Field(min_length=1, max_length=60)
    isCurrent: bool
    parentLayoutId: str | None = None
    items: list[LayoutItem]
    zones: list[Zone] = []
    metrics: LayoutMetrics | None = None
    createdBy: Literal["user", "agent", "system"] = "user"
    requestText: str | None = None
    style: str | None = None
    createdAt: str
    updatedAt: str


class Violation(BaseModel):
    rule: RuleId
    severity: Severity
    items: list[str]
    message: str


class ValidationResult(BaseModel):
    violations: list[Violation]
    metrics: LayoutMetrics
    blocked: bool


class PlanConstraint(Strict):
    type: Literal["lock", "adjacent", "keep_clear", "clear_zone"]
    item: str | None = None
    feature: Literal["window", "door", "outlet", "wall"] | None = None
    w_m: float | None = None
    d_m: float | None = None
    label: str | None = None
    optional: bool | None = None


class PlanAction(Strict):
    type: Literal["add", "move", "remove", "rotate"]
    item: str
    zone: str | None = None
    rotation: float | None = None


class PlanOption(Strict):
    """One arrangement from the interior-designer skill's options (references/options-output.md), zone-level like the plan itself."""

    variantName: str
    actions: list[PlanAction]
    constraints: list[PlanConstraint] = []
    explanation: str | None = None
    tradeoff: str | None = None


class AgentPlan(Strict):
    intent: Intent
    variantName: str | None = None
    theme: str | None = None
    constraints: list[PlanConstraint] = []
    actions: list[PlanAction] = []
    roomSummary: str | None = None
    options: list[PlanOption] = Field(default=[], max_length=3)
    recommended: str | None = None
    reply: str
    clarifyingQuestion: str | None = None
    preferencesLearned: list[str] = []


class User(Loose):
    id: str
    phone: str
    memories: list[str] = []
    backboardAssistantId: str | None = None
    createdAt: str


class AgentRequestLog(Loose):
    id: str
    userId: str
    roomId: str | None
    baseLayoutId: str | None
    channel: Channel
    text: str
    status: Literal["ok", "rejected", "clarify", "error"]
    plan: AgentPlan | None = None
    layoutId: str | None = None
    reply: str
    violations: list[Violation] = []
    layoutIds: list[str] = []
    createdAt: str


# Financial and housing contracts are strict and versioned independently of geometry.
from app.housing_models import (  # noqa: E402,F401
    HousingProfile, ConditionObservation, RentalComparable, SourceInfo, BuildingRecord,
    RentRange, RentAssessment, PaymentQuote, PaymentRecord, Tenancy, QuoteRequest,
)
