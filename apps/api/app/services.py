"""Room/layout helpers shared by routers: build skeletons, seed the Current Room, validate a layout against its room."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.catalog import FIXTURES_DIR, all_furniture
from app.deps import AppContext
from app.models import RoomElement, Dimensions, Door, Layout, LayoutItem, Room, RoomSkeleton, ValidationResult, WallSegment, Window, Zone
from app.solver.validate import validate_layout

SAMPLES = {"nyc-bedroom": "sample-nyc-bedroom.json", "studio": "sample-studio.json", "l-shaped": "sample-l-shaped.json"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def load_sample(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "rooms" / SAMPLES[name]).read_text())


def skeleton_from_dimensions(dims: Dimensions, doors: list[Door], windows: list[Window]) -> RoomSkeleton:
    """Rectangular room: wall 0 along +x at z=0 (north), then clockwise on screen like the sample fixtures."""
    l, w, h = dims.l, dims.w, dims.h
    corners = [(0.0, 0.0), (l, 0.0), (l, w), (0.0, w)]
    walls = [WallSegment(x1=a[0], z1=a[1], x2=b[0], z2=b[1], height=h) for a, b in zip(corners, corners[1:] + corners[:1], strict=True)]
    return RoomSkeleton(walls=walls, doors=doors, windows=windows, floorPolygon=corners, dimensions=dims)


def seed_items(objects: list[dict[str, Any]]) -> list[LayoutItem]:
    """Instance ids are `<furnitureId>_<n>` with n = 1-based position, matching packages/geometry/bench/gen_expectations.ts seed()."""
    return [LayoutItem(id=f"{o['furnitureId']}_{i + 1}", **o) for i, o in enumerate(objects)]


async def validate_for_room(ctx: AppContext, room: Room, items: list[LayoutItem], zones: list[Zone], base: Layout | None = None) -> ValidationResult:
    catalog = await all_furniture(ctx.repo)
    return validate_layout(room.skeleton, catalog, items, zones, base.items if base else None)


async def create_room(
    ctx: AppContext, *, name: str, skeleton: RoomSkeleton, source: str, objects: list[dict[str, Any]], user_id: str,
    seed: bool = True, space_types: list[str] | None = None, elements: list[RoomElement] | None = None,
) -> tuple[Room, Layout]:
    """`seed=False` creates a clean base room (empty Current Room); detected objects are kept on the room for later."""
    room = Room(  # type: ignore[arg-type]
        id=new_id(), userId=user_id, name=name, skeleton=skeleton, source=source, createdAt=now_iso(),
        spaceTypes=space_types or [], elements=elements or [], detectedObjects=[] if seed else objects,
    )
    items = seed_items(objects) if seed else []
    validation = await validate_for_room(ctx, room, items, [])
    layout = Layout(
        id=new_id(), roomId=room.id, name="Current Room", isCurrent=True, parentLayoutId=None, items=items, zones=[],
        metrics=validation.metrics, createdBy="system", requestText=None, createdAt=now_iso(), updatedAt=now_iso(),
    )
    await ctx.repo.insert("rooms", room.model_dump())
    await ctx.repo.insert("layouts", layout.model_dump())
    return room, layout
