"""Scan ingest: raw USDZ -> Blob (first, so a failed conversion never loses the scan) -> canonical skeleton -> scanned furniture
-> room with Base Layout + Current Room."""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

from app.catalog import PRESETS
from app.deps import AppContext
from app.models import Dims, FurnitureItem, Layout, LayoutItem, Room, RoomSkeleton
from app.services.blob import LOCAL_PREFIX
from app.services.rooms import create_room, new_id, now_iso
from app.services.usdz_convert import FURNITURE_CATEGORIES, ConversionError, ScannedObject, convert_usdz
from app.solver.grid import item_rect, rects_overlap
from app.solver.skeleton import room_bounds
from app.solver.validate import validate_layout

log = logging.getLogger(__name__)
USDZ_MIME = "model/vnd.usdz+zip"
NUDGE_M = 0.10  # scanned boxes often poke a few cm through the wall they stand against
PULL_OUT_GAP_M = 0.02  # a tucked chair is slid out until it just clears its table
FIXTURE_GLB = {"Refrigerator": "mini_fridge"}
_BLOB_HOST = re.compile(r"^[a-z0-9]+\.(public|private)\.blob\.vercel-storage\.com$")


class UsdUnavailable(RuntimeError):
    """usd-core is not installed (e.g. the slim Vercel runtime); only the Docker image ships it."""


def preset_for(o: ScannedObject) -> str | None:
    """Nearest catalog preset for a RoomPlan furniture category; None for fixed fixtures."""
    if o.category == "Bed":
        return "bed_double" if min(o.w, o.d) >= 1.2 else "bed_single"
    if o.category == "Table":
        return "desk" if min(o.w, o.d) <= 0.7 else "table"
    if o.category == "Storage":
        return "dresser" if o.h <= 1.2 else "bookshelf"
    return {"Chair": "chair", "Sofa": "sofa", "Television": "tv_stand"}.get(o.category)


def _fixture_name(category: str) -> str:
    return {"WasherDryer": "Washer/dryer"}.get(category, category)


def _nudge_inside(sk: RoomSkeleton, o: ScannedObject, dims: dict[str, float]) -> tuple[float, float]:
    """Shift an item back inside the room's bounding box when it overshoots a wall by at most NUDGE_M."""
    from app.models import Dims

    b = room_bounds(sk)
    r = item_rect(o.x, o.z, o.rotation, Dims(**dims))
    dx = (b.x0 - r.x0 if r.x0 < b.x0 else b.x1 - r.x1 if r.x1 > b.x1 else 0.0)
    dz = (b.z0 - r.z0 if r.z0 < b.z0 else b.z1 - r.z1 if r.z1 > b.z1 else 0.0)
    return (o.x + dx if abs(dx) <= NUDGE_M else o.x), (o.z + dz if abs(dz) <= NUDGE_M else o.z)


def scanned_furniture(objects: list[ScannedObject], sk: RoomSkeleton, user_id: str, room_id: str) -> tuple[list[dict], list[LayoutItem]]:
    """Catalog docs (`source: scan`, preset GLB scaled to the scanned dims) + Base Layout items. Fixtures are locked `other` items."""
    docs: list[dict] = []
    items: list[LayoutItem] = []
    for i, o in enumerate(objects):
        dims = {"w": max(o.w, 0.05), "d": max(o.d, 0.05), "h": max(o.h, 0.0)}
        fid = f"scan_{uuid.uuid4().hex[:8]}"
        preset_id = preset_for(o) if o.category in FURNITURE_CATEGORIES else None
        if preset_id:
            p = PRESETS[preset_id]
            item = FurnitureItem(
                id=fid, userId=user_id, name=p.name, category=p.category, kind=p.kind, dims=dims, glbUrl=p.glbUrl, thumbUrl=p.thumbUrl,  # type: ignore[arg-type]
                source="scan", color=p.color, frontAxis=p.frontAxis,
            )
        else:
            look = PRESETS.get(FIXTURE_GLB.get(o.category, ""))
            item = FurnitureItem(
                id=fid, userId=user_id, name=_fixture_name(o.category), category="other", kind="decor", dims=dims,  # type: ignore[arg-type]
                glbUrl=look.glbUrl if look else None, thumbUrl=look.thumbUrl if look else None, source="scan",
            )
        x, z = _nudge_inside(sk, o, dims)
        docs.append({**item.model_dump(), "roomId": room_id, "scanCategory": o.category, "presetId": preset_id, "createdAt": now_iso()})
        items.append(LayoutItem(id=f"{fid}_{i + 1}", furnitureId=fid, x=round(x, 3), z=round(z, 3), rotation=o.rotation, locked=preset_id is None))  # type: ignore[arg-type]
    return docs, items


def untuck(sk: RoomSkeleton, docs: list[dict], items: list[LayoutItem]) -> tuple[list[LayoutItem], list[str]]:
    """RoomPlan scans chairs where they stand, often tucked under a table: that is an overlap, which would block every save. Slide
    each tucked seat straight out from its table (the way you'd pull it out) until it clears; report anything still overlapping."""
    dims = {d["id"]: Dims(**d["dims"]) for d in docs}
    kinds = {d["id"]: d["kind"] for d in docs}
    b = room_bounds(sk)
    notes: list[str] = []
    out = list(items)
    for k, chair in enumerate(out):
        if kinds.get(chair.furnitureId) != "seating":
            continue
        cr = item_rect(chair.x, chair.z, chair.rotation, dims[chair.furnitureId])
        for table in out:
            if table.id == chair.id or kinds.get(table.furnitureId) not in ("table", "desk"):
                continue
            tr = item_rect(table.x, table.z, table.rotation, dims[table.furnitureId])
            if not rects_overlap(cr, tr):
                continue
            dx, dz = chair.x - table.x, chair.z - table.z
            if abs(dx) >= abs(dz):
                x = tr.x1 + (cr.x1 - cr.x0) / 2 + PULL_OUT_GAP_M if dx >= 0 else tr.x0 - (cr.x1 - cr.x0) / 2 - PULL_OUT_GAP_M
                moved = chair.model_copy(update={"x": round(x, 3)})
            else:
                z = tr.z1 + (cr.z1 - cr.z0) / 2 + PULL_OUT_GAP_M if dz >= 0 else tr.z0 - (cr.z1 - cr.z0) / 2 - PULL_OUT_GAP_M
                moved = chair.model_copy(update={"z": round(z, 3)})
            mr = item_rect(moved.x, moved.z, moved.rotation, dims[moved.furnitureId])
            if b.x0 <= mr.x0 and mr.x1 <= b.x1 and b.z0 <= mr.z0 and mr.z1 <= b.z1:
                out[k] = chair = moved
                cr = mr
                notes.append(f"pulled a chair out from under the {'desk' if kinds[table.furnitureId] == 'desk' else 'table'}")
            break
    return out, notes


def base_layout_notes(sk: RoomSkeleton, docs: list[dict], items: list[LayoutItem]) -> list[str]:
    """Plain-language list of hard problems left in the scanned layout (the editor has to fix them before a save)."""
    catalog = {d["id"]: FurnitureItem.model_validate(d) for d in docs}
    res = validate_layout(sk, catalog, items, [], None)
    return [f"{v.message}: move it in the editor before saving" for v in res.violations if v.rule in ("bounds", "overlap")]


def is_own_blob(url: str) -> bool:
    """Only re-read scans from our own store (no fetching arbitrary URLs)."""
    if url.startswith(LOCAL_PREFIX):
        return True
    u = urlparse(url)
    return u.scheme == "https" and bool(u.hostname and _BLOB_HOST.match(u.hostname))


async def ingest_usdz(ctx: AppContext, *, data: bytes | None, usdz_url: str | None, name: str, user_id: str) -> tuple[Room, Layout, Layout]:
    """New upload (`data`) or re-conversion of a stored scan (`usdz_url`). Raises ConversionError (422) / UsdUnavailable (503)."""
    room_id = new_id()
    if data is not None:
        usdz_url = await ctx.blob.put(f"scans/{room_id}.usdz", data, USDZ_MIME)
    else:
        assert usdz_url is not None
        data = await ctx.blob.get(usdz_url)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.usdz"
            path.write_bytes(data)
            scan = await asyncio.to_thread(convert_usdz, path)
    except ConversionError as exc:
        exc.report["usdzUrl"] = usdz_url
        raise
    except ImportError as exc:
        raise UsdUnavailable("USDZ conversion needs usd-core, which this deployment does not include") from exc
    except Exception as exc:  # corrupt archive, unreadable layer (pxr raises Tf.ErrorException)
        log.warning("usdz conversion crashed: %s", exc)
        raise ConversionError(f"could not read the USDZ: {exc}", {"primCounts": {}, "warnings": [], "usdzUrl": usdz_url}) from exc
    docs, items = scanned_furniture(scan.objects, scan.skeleton, user_id, room_id)
    items, pulled = untuck(scan.skeleton, docs, items)
    scan.report["warnings"] += pulled + base_layout_notes(scan.skeleton, docs, items)
    return await create_room(
        ctx, name=name, skeleton=scan.skeleton, source="scan", items=items, user_id=user_id, room_id=room_id, usdz_url=usdz_url,
        conversion=scan.report, furniture=docs,
    )
