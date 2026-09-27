"""Pydantic models mirroring packages/contracts/schemas/*.json. Field names are camelCase to match the wire shape."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Rotation = Literal[0, 90, 180, 270]
FurnitureCategory = Literal["bed", "desk", "seating", "storage", "table", "decor", "imported", "other"]
FurnitureKind = Literal["bed", "desk", "wardrobe", "dresser", "storage", "seating", "table", "decor", "floor"]
FurnitureSource = Literal["preset", "link", "photo", "manual", "scan"]
RoomSource = Literal["scan", "manual", "sample"]
LayoutKind = Literal["base", "current", "variant"]
Walkability = Literal["Good", "Tight", "Blocked"]
Severity = Literal["error", "warning"]
RuleId = Literal["bounds", "overlap", "locked", "door_clearance", "window_keep_clear", "access_edge", "clear_zone", "walkable_path"]
PlanIntent = Literal["fit_item", "make_space", "keep_clear", "rank_variants", "rent_check", "payment_check", "clarify"]
PlanFeature = Literal["window", "door", "wall", "outlet"]
AgentStatus = Literal["ok", "rejected", "clarify"]
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


# ---- skeleton (immutable after the room is created) ------------------------------------------------------------------------


class WallSegment(Strict):
    """A wall as a floor segment (x1,z1)->(x2,z2). `id`/`thickness` are filled at ingest (thickness only when scanned)."""

    x1: float
    z1: float
    x2: float
    z2: float
    height: float = Field(ge=1.5, le=6)
    id: str | None = None
    thickness: float | None = Field(default=None, ge=0)


class Door(Strict):
    """`wall` is the wall index and `offset` the distance from (x1,z1) along it; `wallId`/`center` are the same fact by id/point.
    Openings (RoomPlan `Opening*`) are doors with `opening: true` and `swing: "out"`, so they keep the clearance but no swing arc."""

    wall: int = Field(ge=0)
    offset: float = Field(ge=0)
    width: float = Field(ge=0.5, le=2.5)
    height: float = 2.0
    swing: Literal["in", "out"]
    hinge: Literal["left", "right"]
    id: str | None = None
    wallId: str | None = None
    center: tuple[float, float] | None = None
    opening: bool | None = None


class Window(Strict):
    wall: int = Field(ge=0)
    offset: float = Field(ge=0)
    width: float = Field(ge=0.3)
    sillHeight: float = Field(ge=0)
    height: float = Field(ge=0.3)
    id: str | None = None
    wallId: str | None = None
    center: tuple[float, float] | None = None


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
    ceilingHeight: float | None = None


class Room(Loose):
    id: str
    userId: str | None = None
    name: str
    skeleton: RoomSkeleton
    source: RoomSource
    usdzUrl: str | None = None
    thumbnailUrl: str | None = None
    baseLayoutId: str | None = None
    currentLayoutId: str | None = None
    conversion: dict[str, Any] | None = None
    createdAt: str
    updatedAt: str | None = None

    def to_doc(self) -> dict[str, Any]:
        """Stored/wire shape: optional skeleton fields that were never filled are omitted rather than null."""
        doc = self.model_dump()
        doc["skeleton"] = self.skeleton.model_dump(exclude_none=True)
        return doc


# ---- furniture catalog -------------------------------------------------------------------------------------------------------


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
    photoUrl: str | None = None
    source: FurnitureSource
    sourceUrl: str | None = None
    price: float | None = None
    color: str | None = None
    estimated: bool = False
    frontAxis: Literal["+z", "-z", "+x", "-x"] = "+z"


# ---- layouts -----------------------------------------------------------------------------------------------------------------


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
    type: Literal["clear", "keep_clear"] = "clear"


class FreeRect(BaseModel):
    x: float
    z: float
    w: float
    d: float
    areaM2: float
    fits: str


class LayoutMetrics(BaseModel):
    """Exactly what the TS validator computes (parity-tested)."""

    openFloor: float
    conflicts: int
    walkability: Walkability
    reachableStorage: float
    largestFreeRect: FreeRect | None


class SavedMetrics(LayoutMetrics):
    """What is stored on a layout: the validator metrics plus the v2 names (`openFloorPct`) and soft-rule warning messages."""

    openFloorPct: float | None = None
    warnings: list[str] = []


class Layout(Loose):
    """`kind` is the source of truth; `isCurrent` (kind == "current") is kept for the web and mobile clients."""

    id: str
    roomId: str
    name: str = Field(min_length=1, max_length=60)
    kind: LayoutKind = "variant"
    isCurrent: bool = False
    parentLayoutId: str | None = None
    items: list[LayoutItem]
    zones: list[Zone] = []
    metrics: SavedMetrics | None = None
    createdBy: Literal["user", "agent", "system"] = "user"
    requestText: str | None = None
    version: int = Field(default=1, ge=1)
    createdAt: str
    updatedAt: str

    @model_validator(mode="before")
    @classmethod
    def _legacy_kind(cls, data: Any) -> Any:
        """Layouts saved before `kind` existed: isCurrent -> current, everything else -> variant."""
        if isinstance(data, dict) and "kind" not in data:
            return {**data, "kind": "current" if data.get("isCurrent") else "variant"}
        return data

    @model_validator(mode="after")
    def _sync_is_current(self) -> Layout:
        self.isCurrent = self.kind == "current"
        return self


class Violation(BaseModel):
    rule: RuleId
    severity: Severity
    items: list[str]
    message: str


class ValidationResult(BaseModel):
    violations: list[Violation]
    metrics: LayoutMetrics
    blocked: bool


# ---- agent -------------------------------------------------------------------------------------------------------------------


class PlanItem(BaseModel):
    """The item being fitted, as Gemini read it from the request/listing. Dimensions in meters; never a position."""

    type: str = Field(description="furniture word: bed, desk, chair, dresser, nightstand, shelf, sofa, table, rug, yoga_mat, ...")
    name: str | None = None
    w_m: float | None = None
    d_m: float | None = None
    h_m: float | None = None
    price_usd: float | None = None


class PlanConstraint(BaseModel):
    type: Literal["lock", "adjacent", "keep_clear", "clear_zone"]
    item: str | None = Field(default=None, description="plain-language item ('bed', 'desk') or an instance id from the layout")
    feature: PlanFeature | None = None
    w_m: float | None = None
    d_m: float | None = None
    label: str | None = None


class VariantRank(BaseModel):
    layoutId: str
    rank: int
    reason: str


class RentAsk(BaseModel):
    """rent_check: what the user said about their rent (the math is done by app/rent.py, never by Gemini)."""

    askingRent: float | None = None
    zip: str | None = None
    occupancyType: OccupancyType | None = None
    issues: list[str] = Field(default_factory=list, description="condition problems the user mentioned: rats, leak, bad faucet, ...")
    depositRequested: float | None = None
    applicationFee: float | None = None


class PaymentAsk(BaseModel):
    """payment_check: a payment the user is about to make; app/rent.py applies the NYC guardrails."""

    purpose: PaymentPurpose
    amount: float | None = None


class GeminiPlan(BaseModel):
    """Stage 1 structured output. Gemini is the orchestrator: it picks the intent (and so the tool) and extracts its inputs.
    There is deliberately no coordinate field anywhere in this schema: the solver places, the validator checks."""

    intent: PlanIntent
    item: PlanItem | None = None
    constraints: list[PlanConstraint] = []
    variantName: str | None = None
    explanation: str
    question: str | None = Field(default=None, description="the one clarifying question when intent is clarify")
    ranking: list[VariantRank] = Field(default_factory=list, description="rank_variants only: existing layouts, best first")
    preferences: list[str] = Field(default_factory=list, description="durable facts the user just stated, e.g. 'never move the bed'")
    rent: RentAsk | None = None
    payment: PaymentAsk | None = None


class Placement(BaseModel):
    item: str  # instance id in the new variant
    name: str
    furnitureId: str
    x: float
    z: float
    rotation: Rotation


class PlanOut(GeminiPlan):
    """The plan returned to clients: Gemini's plan plus what the solver wrote (`placement`, `moves`, `zones`)."""

    placement: Placement | None = None
    moves: list[Placement] = []
    zones: list[Zone] = []


class OptionValidation(BaseModel):
    ok: bool
    warnings: int
    open_floor_pct: float


class DesignOption(BaseModel):
    """One arrangement from the Interior Designer (interior-designer skill format), saved as its own named variant."""

    variantName: str
    layoutId: str | None = None
    explanation: str
    tradeoff: str
    moved: list[str] = []
    placement: Placement | None = None
    moves: list[Placement] = []
    zones: list[Zone] = []
    validation: OptionValidation
    relaxed: list[str] = Field(default_factory=list, description="constraints this option gives up (e.g. 'beside the window')")


class OptionText(BaseModel):
    index: int
    variantName: str = Field(description="1 to 3 plain words a person would say out loud, e.g. 'Window Desk'")
    explanation: str = Field(description="1-2 plain sentences: why this arrangement is good for this person")
    tradeoff: str = Field(description="1 sentence: the honest downside")


class Narration(BaseModel):
    """Stage 4 structured output: Gemini, as the Interior Designer, words the result. It cannot change what was placed."""

    room_summary: str
    options: list[OptionText] = []
    recommended_index: int = 0
    reply: str = Field(description="one sentence for iMessage/app, the answer first")


class User(Loose):
    id: str
    displayName: str
    memories: list[str] = []
    backboardAssistantId: str | None = None
    createdAt: str


class SolverAttempt(BaseModel):
    attempt: int
    ok: bool
    violations: list[Violation] = []
    note: str | None = None


class AgentRequestLog(Loose):
    id: str
    userId: str
    roomId: str
    sourceLayoutId: str
    resultLayoutId: str | None = None
    requestText: str
    attachments: list[dict[str, Any]] = []
    channel: Channel = "app"
    geminiPlan: list[dict[str, Any]] = []  # raw Stage 1 output per attempt
    plan: PlanOut | None = None
    solverAttempts: list[SolverAttempt] = []
    validation: dict[str, Any] | None = None
    status: AgentStatus
    reply: str
    latencyMs: int
    createdAt: str


# ---- rent reality check + guarded payments (not part of the room-planner spec; kept for the web Rent tab) --------------------


class HousingProfile(Loose):
    roomId: str
    address: str | None = None
    zip: str | None = None
    borough: str | None = None
    neighborhood: str | None = None
    bbl: str | None = None
    source: Literal["user", "fixture", "open_data"] = "user"
    askingRent: float
    depositRequested: float | None = None
    applicationFee: float | None = None
    utilitiesIncluded: bool = False
    occupancyType: OccupancyType = "private_room"
    bedrooms: int | None = None
    declaredIssues: list[str] = []


class SpaceQuality(Loose):
    floorAreaSqFt: float
    usableAreaSqFt: float
    openFloorPct: float
    ceilingHeightFt: float
    windowCount: int
    floorMaterial: FloorMaterial = "unknown"
    materialConfidence: Confidence = "low"
    conditionScore: int
    issuePenalties: list[str] = []


class RentRange(Strict):
    low: int
    mid: int
    high: int


class SourceBreakdown(Strict):
    source: str
    label: str
    value: str


class RentAssessment(Loose):
    id: str
    roomId: str
    layoutId: str | None = None
    profile: HousingProfile
    spaceQuality: SpaceQuality
    estimatedFairRange: RentRange
    askingRent: float
    deltaVsMid: float
    pricePerSqFt: float
    confidence: Confidence
    explanation: list[str]
    sourceBreakdown: list[SourceBreakdown]
    legalFlags: list[str]
    buildingHealthSignals: list[str]
    createdAt: str
    updatedAt: str


class PaymentQuote(Loose):
    id: str
    roomId: str | None = None
    assessmentId: str | None = None
    purpose: PaymentPurpose
    amount: float
    rentAmount: float | None = None
    status: PaymentStatus
    guardrails: list[str]
    stripeCheckoutUrl: str | None = None
    stripeSessionId: str | None = None
    createdAt: str
    updatedAt: str
