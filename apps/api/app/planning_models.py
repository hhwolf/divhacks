"""Internal models for optional advanced geometry planning, separate from API/financial contracts.

These are solver inputs, not a replacement for the existing AgentPlan wire schema.
Only geometry intents are accepted. The solver (never model output) supplies coordinates.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import PlanConstraint, Rotation


class PlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    type: str = Field(min_length=1)
    name: str | None = None
    w_m: float | None = Field(default=None, gt=0, le=100)
    d_m: float | None = Field(default=None, gt=0, le=100)
    h_m: float | None = Field(default=None, ge=0, le=20)
    price_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def paired_dimensions(self) -> PlanItem:
        if (self.w_m is None) != (self.d_m is None):
            raise ValueError("width and depth must both be provided or both omitted")
        return self


class PlacementPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    intent: Literal["fit_item", "make_space", "keep_clear"]
    item: PlanItem | None = None
    constraints: list[PlanConstraint] = Field(default_factory=list)
    variantName: str | None = None
    explanation: str = ""
    # Explicit action semantics when adapting an existing AgentPlan. Otherwise an
    # existing matching item is moved, or a new catalog item is added.
    operation: Literal["add", "move"] | None = None

    @model_validator(mode="after")
    def finite_zones(self) -> PlacementPlan:
        import math

        for constraint in self.constraints:
            for value in (constraint.w_m, constraint.d_m):
                if value is not None and (not math.isfinite(value) or not 0 < value <= 100):
                    raise ValueError("clear-zone dimensions must be positive finite meters")
        return self


class Placement(BaseModel):
    item: str
    name: str
    furnitureId: str
    x: float
    z: float
    rotation: Rotation
