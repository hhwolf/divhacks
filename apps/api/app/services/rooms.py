"""Room/layout helpers shared by routers: build skeletons, create a room with its Base Layout + Current Room, validate layouts."""

from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime
from typing import Any

from app.catalog import FIXTURES_DIR, all_furniture
from app.deps import AppContext
from app.models import (
    Dimensions,
    Door,
    Layout,
    LayoutItem,
    LayoutKind,
    Room,
    RoomSkeleton,
    RoomSource,
    SavedMetrics,
    ValidationResult,
    WallSegment,
    Window,
    Zone,
)
from app.solver.skeleton import opening_span
from app.solver.validate import validate_layout

SAMPLES = {"nyc-bedroom": "sample-nyc-bedroom.json", "studio": "sample-studio.json"}
DEFAULT_SAMPLE = "nyc-bedroom"
BASE_NAME = "Original Room"
CURRENT_NAME = "Current Room"


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


def canonicalize(sk: RoomSkeleton) -> RoomSkeleton:
    """Fill the ids / wallIds / centers / ceilingHeight every canonical skeleton carries (scans already have them)."""
    walls = [w if w.id else w.model_copy(update={"id": f"w{i}"}) for i, w in enumerate(sk.walls)]
    fixed = sk.model_copy(update={"walls": walls})

    def center(o: Door | Window) -> tuple[float, float]:
        a, b = opening_span(fixed, o)
        return (round((a[0] + b[0]) / 2, 3), round((a[1] + b[1]) / 2, 3))

    doors = [d.model_copy(update={"id": d.id or f"d{i}", "wallId": walls[d.wall].id, "center": d.center or center(d)}) for i, d in enumerate(sk.doors)]
    windows = [w.model_copy(update={"id": w.id or f"win{i}", "wallId": walls[w.wall].id, "center": w.center or center(w)}) for i, w in enumerate(sk.windows)]
    ceiling = sk.ceilingHeight or max(w.height for w in walls)
    return RoomSkeleton.model_validate({**fixed.model_dump(), "doors": [d.model_dump() for d in doors], "windows": [w.model_dump() for w in windows], "ceilingHeight": ceiling})


def check_openings(sk: RoomSkeleton) -> None:
    """Doors/windows must reference an existing wall and fit on it (ValueError otherwise)."""
    for label, openings in (("door", sk.doors), ("window", sk.windows)):
        for i, o in enumerate(openings):
            if o.wall >= len(sk.walls):
                raise ValueError(f"{label} {i} references wall {o.wall}, but there are only {len(sk.walls)} walls")
            w = sk.walls[o.wall]
            if o.offset + o.width > math.hypot(w.x2 - w.x1, w.z2 - w.z1) + 1e-6:
                raise ValueError(f"{label} {i} runs past the end of wall {o.wall}")


def seed_items(objects: list[dict[str, Any]]) -> list[LayoutItem]:
    """Instance ids are `<furnitureId>_<n>` with n = 1-based position, matching packages/geometry/bench/gen_expectations.ts seed()."""
    return [LayoutItem(id=f"{o['furnitureId']}_{i + 1}", **o) for i, o in enumerate(objects)]


def saved_metrics(v: ValidationResult) -> SavedMetrics:
    return SavedMetrics(**v.metrics.model_dump(), openFloorPct=v.metrics.openFloor, warnings=[x.message for x in v.violations if x.severity == "warning"])


async def validate_for_room(ctx: AppContext, room: Room, items: list[LayoutItem], zones: list[Zone], base: Layout | None = None) -> ValidationResult:
    catalog = await all_furniture(ctx.repo)
    return validate_layout(room.skeleton, catalog, items, zones, base.items if base else None)


def make_layout(
    room_id: str,
    name: str,
    kind: LayoutKind,
    items: list[LayoutItem],
    zones: list[Zone],
    validation: ValidationResult,
    *,
    parent: str | None = None,
    created_by: str = "user",
    request_text: str | None = None,
) -> Layout:
    now = now_iso()
    return Layout(
        id=new_id(), roomId=room_id, name=name, kind=kind, parentLayoutId=parent, items=items, zones=zones, metrics=saved_metrics(validation),
        createdBy=created_by, requestText=request_text, version=1, createdAt=now, updatedAt=now,  # type: ignore[arg-type]
    )


def dedupe_name(name: str, taken: set[str]) -> str:
    name = name.strip()[:55] or "Variant"
    candidate, n = name, 2
    while candidate in taken:
        candidate = f"{name} ({n})"
        n += 1
    return candidate


async def taken_names(ctx: AppContext, room_id: str) -> set[str]:
    return {l["name"] for l in await ctx.repo.list_by_room("layouts", room_id)}


async def create_room(
    ctx: AppContext,
    *,
    name: str,
    skeleton: RoomSkeleton,
    source: RoomSource,
    items: list[LayoutItem],
    user_id: str,
    room_id: str | None = None,
    usdz_url: str | None = None,
    conversion: dict[str, Any] | None = None,
    furniture: list[dict[str, Any]] | None = None,
) -> tuple[Room, Layout, Layout]:
    """Room + read-only Base Layout + Current Room (a fork of Base), written together. `furniture` = catalog docs created by a scan."""
    check_openings(skeleton)
    skeleton = canonicalize(skeleton)
    now = now_iso()
    room = Room(id=room_id or new_id(), userId=user_id, name=name, skeleton=skeleton, source=source, usdzUrl=usdz_url, conversion=conversion, createdAt=now, updatedAt=now)
    for doc in furniture or []:
        await ctx.repo.insert("furniture", doc)  # before validation, so the catalog knows the scanned items
    validation = await validate_for_room(ctx, room, items, [])
    base = make_layout(room.id, BASE_NAME, "base", items, [], validation, created_by="system")
    current = make_layout(room.id, CURRENT_NAME, "current", items, [], validation, parent=base.id, created_by="system")
    room = room.model_copy(update={"baseLayoutId": base.id, "currentLayoutId": current.id})
    await ctx.repo.apply([("insert", "rooms", room.to_doc()), ("insert", "layouts", base.model_dump()), ("insert", "layouts", current.model_dump())])
    return room, base, current


async def touch_room(ctx: AppContext, room_id: str) -> None:
    await ctx.repo.update("rooms", room_id, {"updatedAt": now_iso()})
