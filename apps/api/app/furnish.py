"""Theme -> furnished layout. Gemini (or a canned kit in mock mode / on failure) picks catalog pieces, then each piece is
placed best-effort: companions (desk chair, nightstand, coffee table, rug) next to their anchor, everything else through the
wall solver. A piece that does not fit is skipped, never fatal, so any room gets a usable starting layout."""

from __future__ import annotations

import io
import logging
import re
import uuid
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from app.catalog import PRESETS
from app.deps import AppContext
from app.models import AgentPlan, FurnitureItem, Layout, LayoutItem, PlanAction, Room, Rotation, ValidationResult, Zone
from app.solver.grid import front_dir
from app.solver.placement import Solver, next_instance_id
from app.solver.validate import validate_layout

log = logging.getLogger(__name__)

Style = Literal["japandi", "industrial", "boho", "minimal", "cozy"]
Purpose = Literal["sleep", "work", "living", "wellness", "studio"]
STYLES: tuple[str, ...] = get_args(Style)
STYLE_LABEL = {"japandi": "Japandi", "industrial": "Industrial", "boho": "Boho", "minimal": "Minimal", "cozy": "Cozy"}
PURPOSE_LABEL = {"sleep": "bedroom", "work": "study", "living": "living room", "wellness": "wellness room", "studio": "studio"}

_STYLE_WORDS: list[tuple[str, Style]] = [
    ("japandi", "japandi"), ("japan", "japandi"), ("scandi", "japandi"), ("nordic", "japandi"), ("zen", "japandi"), ("wabi", "japandi"),
    ("industrial", "industrial"), ("loft", "industrial"), ("concrete", "industrial"), ("metal", "industrial"), ("urban", "industrial"),
    ("boho", "boho"), ("bohemian", "boho"), ("eclectic", "boho"), ("plant", "boho"), ("jungle", "boho"), ("rattan", "boho"),
    ("minimal", "minimal"), ("clean", "minimal"), ("simple", "minimal"), ("white", "minimal"), ("modern", "minimal"),
    ("cozy", "cozy"), ("cosy", "cozy"), ("warm", "cozy"), ("vintage", "cozy"), ("cottage", "cozy"), ("hygge", "cozy"),
]
_PURPOSE_WORDS: list[tuple[str, Purpose]] = [
    ("studio", "studio"),
    ("yoga", "wellness"), ("workout", "wellness"), ("gym", "wellness"), ("meditat", "wellness"), ("stretch", "wellness"),
    ("study", "work"), ("office", "work"), ("work", "work"), ("desk", "work"), ("wfh", "work"), ("homework", "work"),
    ("living", "living"), ("lounge", "living"), ("hang", "living"), ("tv", "living"), ("guest", "living"), ("movie", "living"),
    ("bedroom", "sleep"), ("sleep", "sleep"), ("bed", "sleep"), ("nursery", "sleep"),
]

# (catalog id or "a|b" fallbacks tried in order, zone phrase for the wall solver). Order = priority: anchors first.
_KITS: dict[Purpose, list[tuple[str, str]]] = {
    "sleep": [("bed_double|bed_single", "opposite the door, centered or centered"), ("nightstand", ""), ("wardrobe|dresser", "corner"),
              ("rug", ""), ("dresser|bookshelf_low", ""), ("floor_lamp", "corner"), ("plant", "near window")],
    "work": [("desk", "window wall, beside window or near window"), ("chair_desk", ""), ("bookshelf", "corner"), ("bookshelf_low", ""),
             ("armchair", "corner"), ("floor_lamp", "corner"), ("plant", "near window")],
    "living": [("sofa", "opposite the door, centered or centered"), ("coffee_table", ""), ("rug", ""), ("side_table", ""),
               ("tv_stand|bookshelf_low", "centered"), ("armchair", "corner"), ("bookshelf", "corner"), ("floor_lamp", "corner"), ("plant", "near window")],
    "wellness": [("yoga_mat", ""), ("bookshelf_low", ""), ("bench", ""), ("plant", "near window"), ("floor_lamp", "corner"), ("plant", "corner")],
    "studio": [("bed_double|bed_single", "opposite the door, corner or corner"), ("nightstand", ""), ("desk", "near window"), ("chair_desk", ""),
               ("wardrobe|dresser", "corner"), ("armchair", "corner"), ("rug", ""), ("bookshelf_low", ""), ("floor_lamp", "corner"), ("plant", "near window")],
}
_STYLE_EXTRAS: dict[Style, list[tuple[str, str]]] = {
    "japandi": [("bench", ""), ("plant", "corner")],
    "industrial": [("bookshelf", ""), ("stool", "")],
    "boho": [("plant", "corner"), ("plant", ""), ("armchair", "corner")],
    "minimal": [],
    "cozy": [("armchair", "corner"), ("floor_lamp", "corner"), ("side_table", "")],
}
_MINIMAL_DROP = {"floor_lamp", "bookshelf_low", "side_table"}
PLACE_STEP = 0.3  # m between wall-solver candidates; 3x fewer validations than the 10 cm grid, plenty for a starting layout
SMALL_ROOM_M2 = 14.0
UNIQUE_KINDS = {"bed", "desk", "wardrobe"}
MAX_PLAN_ITEMS = 12


class FurnishPiece(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    item: str = Field(min_length=1, max_length=200)
    zone: str = Field(default="", max_length=300)


class FurnishPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    style: Style
    purpose: Purpose
    variantName: str = Field(min_length=1, max_length=30)
    reply: str = Field(max_length=500)
    items: list[FurnishPiece] = Field(min_length=1, max_length=MAX_PLAN_ITEMS)

FURNISH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["style", "purpose", "variantName", "reply", "items"],
    "properties": {
        "style": {"type": "string", "enum": list(STYLES)},
        "purpose": {"type": "string", "enum": list(get_args(Purpose))},
        "variantName": {"type": "string", "minLength": 1, "maxLength": 30},
        "reply": {"type": "string", "maxLength": 500},
        "items": {
            "type": "array",
            "minItems": 1, "maxItems": MAX_PLAN_ITEMS,
            "items": {"type": "object", "required": ["item"], "properties": {"item": {"type": "string", "minLength": 1, "maxLength": 200}, "zone": {"type": "string", "maxLength": 300}}},
        },
    },
}


@dataclass
class FurnishResult:
    layout: Layout
    style: Style
    placed: list[str]
    skipped: list[str] = field(default_factory=list)
    reply: str = ""


def detect(text: str, words: list[tuple[str, Any]], default: Any) -> Any:
    t = text.lower()
    hits = [(t.find(w), v) for w, v in words if w in t]
    return min(hits)[1] if hits else default


def canned_plan(theme: str, purpose_hint: str | None = None, floor_m2: float = 12.0) -> dict[str, Any]:
    """Deterministic plan from keywords (mock mode, and the fallback when Gemini fails)."""
    specific = [(w, s) for w, s in _STYLE_WORDS if s not in ("minimal", "cozy")]  # "cozy japandi" is japandi; mood words only break ties
    style: Style = detect(theme, specific, None) or detect(theme, _STYLE_WORDS, "minimal")
    purpose: Purpose = detect(theme, _PURPOSE_WORDS, None) or detect(purpose_hint or "", _PURPOSE_WORDS, "studio")
    kit = list(_KITS[purpose]) + _STYLE_EXTRAS[style]
    if style == "minimal":
        kit = [k for k in kit if k[0] not in _MINIMAL_DROP]
    if purpose == "studio" and floor_m2 < SMALL_ROOM_M2:
        kit = [("bed_single|bed_double", z) if i.startswith("bed_double") else (i, z) for i, z in kit]  # leave room for the desk
    name = f"{STYLE_LABEL[style]} {PURPOSE_LABEL[purpose]}"
    return {"style": style, "purpose": purpose, "variantName": name[:1].upper() + name[1:], "reply": "", "items": [{"item": i, "zone": z} for i, z in kit]}


def furnish_prompt(room: Room, catalog: Mapping[str, FurnitureItem], purpose: str | None) -> str:
    sk = room.skeleton
    pieces = "\n".join(f"- {f.id}: {f.name}, {f.dims.w}x{f.dims.d}x{f.dims.h} m" for f in catalog.values())
    return (
        "You furnish an EMPTY small NYC room from a theme. Pick 5-12 pieces ONLY from this catalog (use the ids exactly; "
        "'a|b' means try a, fall back to b):\n" + pieces + "\n"
        f"Room {sk.dimensions.l} x {sk.dimensions.w} m, {len(sk.doors)} door(s), {len(sk.windows)} window(s)."
        + (f" The user said this space is for: {purpose}." if purpose else "") + "\n"
        "List pieces in priority order, anchors first (bed/desk/sofa), then their companions (nightstand, chair_desk, coffee_table, rug), then decor. "
        "Companions need no zone: they are placed next to their anchor automatically. For other pieces give a zone phrase such as "
        "'near window', 'corner', 'opposite the door, centered', 'window wall'. Keep total footprint realistic for the floor area; "
        "leave a walkway. style must be one of the enum values that best matches the theme. variantName <= 30 chars. "
        "reply is one friendly sentence describing the room you made."
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _ok(room: Room, catalog: Mapping[str, FurnitureItem], items: list[LayoutItem], zones: list[Zone]) -> bool:
    result = validate_layout(room.skeleton, catalog, items, zones, None)
    return result.metrics.conflicts == 0 and not any(v.rule == "clear_zone" for v in result.violations)


class _FurnishSolver(Solver):
    """Keep existing clear areas fixed while searching, rather than discarding a bad winner later."""

    def __init__(self, *args: Any, protected_zones: list[Zone], **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.protected_zones = protected_zones

    def _validate(self, items: list[LayoutItem], zones: list[Zone] | None = None) -> ValidationResult:
        result = super()._validate(items, [*self.protected_zones, *(zones or [])])
        blockers = sum(v.rule == "clear_zone" and v.severity != "error" for v in result.violations)
        if blockers:
            result.violations = [v.model_copy(update={"severity": "error"}) if v.rule == "clear_zone" else v for v in result.violations]
            result.metrics.conflicts += blockers
        return result


def _rot(r: float) -> Rotation:
    return int(round(r / 90) % 4 * 90)  # type: ignore[return-value]


# Companion placement relative to the most recent anchor instance: "front" = in front of it, "side" = beside it (backs aligned),
# "under" = floor piece centred in front of it. Tried before the wall solver.
_COMPANIONS: dict[str, list[tuple[str, str]]] = {
    "chair_desk": [("desk", "front")],
    "nightstand": [("bed_double", "side"), ("bed_single", "side")],
    "coffee_table": [("sofa", "front")],
    "side_table": [("sofa", "side"), ("armchair", "side"), ("bed_double", "side")],
    "rug": [("sofa", "under"), ("bed_double", "under"), ("bed_single", "under"), ("desk", "under")],
    "stool": [("desk", "side"), ("table", "front")],
}


def _companion_spots(anchor: LayoutItem, af: FurnitureItem, f: FurnitureItem, mode: str) -> list[tuple[float, float, Rotation]]:
    fx, fz = front_dir(anchor.rotation)
    rx, rz = -fz, fx  # right-hand lateral
    if mode == "front":
        gap = 0.05 if f.id == "chair_desk" else 0.35
        dist = af.dims.d / 2 + f.dims.d / 2 + gap
        rot = _rot(anchor.rotation + 180) if f.id == "chair_desk" else anchor.rotation
        return [(anchor.x + fx * dist, anchor.z + fz * dist, rot)]
    if mode == "under":
        dist = af.dims.d / 2 + (0.35 if af.kind == "bed" else 0.45)
        return [(anchor.x + fx * dist, anchor.z + fz * dist, anchor.rotation), (anchor.x + fx * dist * 0.6, anchor.z + fz * dist * 0.6, anchor.rotation)]
    # side: backs aligned, just past either end
    back = af.dims.d / 2 - f.dims.d / 2
    lat = af.dims.w / 2 + f.dims.w / 2 + 0.05
    return [(anchor.x - fx * back + s * rx * lat, anchor.z - fz * back + s * rz * lat, anchor.rotation) for s in (1, -1)]


def _place_companion(room: Room, catalog: Mapping[str, FurnitureItem], items: list[LayoutItem], f: FurnitureItem, zones: list[Zone]) -> LayoutItem | None:
    for anchor_id, mode in _COMPANIONS.get(f.id, []):
        anchor = next((it for it in reversed(items) if it.furnitureId == anchor_id), None)
        if anchor is None:
            continue
        for x, z, rot in _companion_spots(anchor, catalog[anchor_id], f, mode):
            cand = LayoutItem(id=next_instance_id(f.id, items), furnitureId=f.id, x=round(x, 4), z=round(z, 4), rotation=rot, locked=False)
            if _ok(room, catalog, [*items, cand], zones):
                return cand
    return None


def _place_center(room: Room, catalog: Mapping[str, FurnitureItem], items: list[LayoutItem], f: FurnitureItem, zones: list[Zone]) -> LayoutItem | None:
    """Floor pieces without an anchor (yoga mat, lone rug): centre of the largest free rectangle."""
    lfr = validate_layout(room.skeleton, catalog, items, zones, None).metrics.largestFreeRect
    if lfr is None:
        return None
    rot: Rotation = 90 if lfr.w > lfr.d and f.dims.d > f.dims.w else 0
    cand = LayoutItem(id=next_instance_id(f.id, items), furnitureId=f.id, x=round(lfr.x + lfr.w / 2, 4), z=round(lfr.z + lfr.d / 2, 4), rotation=rot, locked=False)
    return cand if _ok(room, catalog, [*items, cand], zones) else None


def place_pieces(room: Room, catalog: Mapping[str, FurnitureItem], base_items: list[LayoutItem], pieces: list[dict[str, Any]], zones: list[Zone] | None = None) -> tuple[list[LayoutItem], list[str], list[str]]:
    items = list(base_items)
    protected = zones or []
    coarse = _FurnishSolver(room.skeleton, catalog, items, step=PLACE_STEP, protected_zones=protected)
    fine = _FurnishSolver(room.skeleton, catalog, items, protected_zones=protected)
    existing = {catalog[it.furnitureId].kind for it in base_items if it.furnitureId in catalog}
    placed: list[str] = []
    skipped: list[str] = []
    for piece in pieces:
        options = [o.strip() for o in str(piece.get("item", "")).split("|") if o.strip() in catalog]
        if not options or catalog[options[0]].kind in existing & UNIQUE_KINDS:
            continue  # the room already has its bed / desk / wardrobe
        done = None
        for fid in options:
            f = catalog[fid]
            cand = _place_companion(room, catalog, items, f, protected)
            if cand is None and f.kind == "floor":
                cand = _place_center(room, catalog, items, f, protected)
            if cand is not None:
                done = [*items, cand]
                break
            if f.kind == "floor":
                continue
            plan = AgentPlan(intent="fit_item", actions=[PlanAction(type="add", item=fid, zone=piece.get("zone") or None)], reply="")
            for solver in (coarse, fine) if f.kind != "decor" else (coarse,):
                solver.base_items = items
                res = solver.solve(plan)
                if res.ok:
                    done = res.items
                    break
            if done is not None:
                break
        if done is None:
            if catalog[options[0]].kind not in ("decor", "floor"):
                skipped.append(catalog[options[0]].name)
        else:
            items = done
            placed.append(catalog[items[-1].furnitureId].name)
    return items, placed, skipped


def _join(names: list[str]) -> str:
    """['Potted plant', 'Sofa', 'Potted plant'] -> 'potted plant x2 and sofa' (first-seen order)."""
    counts: dict[str, int] = {}
    for n in names:
        counts[n.lower()] = counts.get(n.lower(), 0) + 1
    low = [f"{n} x{c}" if c > 1 else n for n, c in counts.items()]
    return low[0] if len(low) == 1 else ", ".join(low[:-1]) + f" and {low[-1]}"


def compose_reply(plan: dict[str, Any], placed: list[str], skipped: list[str]) -> str:
    label = plan["variantName"].lower()
    base = (plan.get("reply") or "").strip() or f"Here's {'an' if label[:1] in 'aeiou' else 'a'} {label} to start from."
    if not placed:
        return "I couldn't fit any furniture in this room; try a smaller theme or check the room size."
    reply = f"{base.rstrip('.')}: {_join(placed)}."
    missing = sorted({s for s in skipped if s not in placed})  # a second armchair that didn't fit isn't worth mentioning
    if missing:
        reply += f" Skipped the {_join(missing)} (not enough room)."
    return reply


def floor_area(room: Room) -> float:
    p = room.skeleton.floorPolygon
    return abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))) / 2


Photo = tuple[bytes, str]  # (data, mime)
MAX_PHOTOS = 4
MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
PHOTO_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


@dataclass
class PhotoMood:
    """Colour read of the inspiration photos, used when Gemini can't look at them (mock mode or a live failure)."""

    style: Style
    plants: bool
    light: float
    saturation: float
    warmth: float


def read_photos(photos: list[Photo]) -> PhotoMood:
    """Downscale each photo and average: lightness, saturation, warmth (red minus blue) and share of foliage-green pixels."""
    from PIL import Image

    check_photos(photos)
    n = light = sat = warm = green = 0.0
    for data, _ in photos:
        with Image.open(io.BytesIO(data)) as opened:
            img = opened.convert("RGB")
            img.thumbnail((64, 64))
            raw = img.tobytes()  # packed RGB; works on every Pillow version (getdata is deprecated in 12+)
        for r, g, b in zip(raw[0::3], raw[1::3], raw[2::3], strict=True):
            mx, mn = max(r, g, b), min(r, g, b)
            light += (mx + mn) / 510
            sat += (mx - mn) / mx if mx else 0
            warm += (r - b) / 255
            green += 1 if g > r + 12 and g > b + 12 else 0
            n += 1
    light, sat, warm, green = light / n, sat / n, warm / n, green / n
    style: Style
    if green > 0.12:
        style = "boho"
    elif light < 0.36:
        style = "industrial"
    elif light > 0.68 and sat < 0.16:
        style = "minimal"
    elif warm > 0.12 and sat > 0.28:
        style = "boho"
    elif warm > 0.06:
        style = "cozy" if light < 0.55 else "japandi"
    else:
        style = "minimal"
    return PhotoMood(style, green > 0.06, round(light, 3), round(sat, 3), round(warm, 3))


def check_photos(photos: list[Photo]) -> None:
    """Raise ValueError unless every photo is a decodable image within the size limit."""
    from PIL import Image, UnidentifiedImageError

    if not 1 <= len(photos) <= MAX_PHOTOS:
        raise ValueError(f"send 1 to {MAX_PHOTOS} photos")
    for data, mime in photos:
        if not data or len(data) > MAX_PHOTO_BYTES:
            raise ValueError("each photo must be under 8 MB")
        if mime not in PHOTO_FORMATS:
            raise ValueError("use JPEG, PNG or WebP photos")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.format != PHOTO_FORMATS[mime] or image.width * image.height > MAX_PHOTO_PIXELS:
                        raise ValueError("use matching JPEG, PNG or WebP photos below 20 megapixels")
                    image.verify()
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("that file isn't a supported, decodable image below 20 megapixels") from exc


def photo_plan(theme: str, purpose: str | None, floor_m2: float, photos: list[Photo]) -> dict[str, Any]:
    """Canned plan steered by the photos' colours; style words typed alongside the photos still win."""
    mood = read_photos(photos)
    typed = detect(theme, _STYLE_WORDS, None)
    plan = canned_plan(f"{theme} {mood.style if typed is None else ''}".strip(), purpose, floor_m2)
    if mood.plants and plan["style"] != "minimal":
        plan["items"] += [{"item": "plant", "zone": "corner"}, {"item": "plant", "zone": ""}]
    plan["variantName"] = f"{plan['variantName']} (from photos)" if len(plan["variantName"]) < 18 else plan["variantName"]
    return plan


async def plan_for(ctx: AppContext, room: Room, theme: str, purpose: str | None, photos: list[Photo] | None = None) -> dict[str, Any]:
    if not ctx.gemini.live:
        return photo_plan(theme, purpose, floor_area(room), photos) if photos else canned_plan(theme, purpose, floor_area(room))
    try:
        system = furnish_prompt(room, PRESETS, purpose) + (PHOTO_PROMPT if photos else "")
        raw = await ctx.gemini.furnish(system, theme or "Match the inspiration photos.", photos or [])
        plan = FurnishPlan.model_validate(raw).model_dump()
        items = []
        for piece in plan["items"]:
            options = [o.strip() for o in piece["item"].split("|") if o.strip() in PRESETS]
            if options:
                items.append({**piece, "item": "|".join(options)})
        if items:
            return {**plan, "items": items}
        log.warning("furnish: Gemini plan contains no catalog items, using canned kit")
    except Exception:  # noqa: BLE001 - any live failure falls back to the deterministic kit
        log.exception("furnish: Gemini failed, using canned kit")
    return photo_plan(theme, purpose, floor_area(room), photos) if photos else canned_plan(theme, purpose, floor_area(room))


PHOTO_PROMPT = (
    "\nThe user attached inspiration photos. Choose style from their materials and colours, and include the kinds of pieces you can "
    "see in them (mapped to the closest catalog id), scaled down to what this room can hold. Mention one thing you took from the photos in reply."
)


async def furnish_room(
    ctx: AppContext, room_doc: dict[str, Any], base_doc: dict[str, Any], theme: str, purpose: str | None, catalog: Mapping[str, FurnitureItem],
    photos: list[Photo] | None = None,
) -> FurnishResult:
    room, base = Room.model_validate(room_doc), Layout.model_validate(base_doc)
    plan = await plan_for(ctx, room, theme, purpose, photos)
    items, placed, skipped = place_pieces(room, catalog, base.items, plan["items"], base.zones)
    validation = validate_layout(room.skeleton, catalog, items, base.zones, base.items)
    taken = {l["name"] for l in await ctx.repo.list_by_room("layouts", room.id)}
    name, n = plan["variantName"], 2
    while name in taken:
        name, n = f"{plan['variantName']} ({n})", n + 1
    layout = Layout(
        id=uuid.uuid4().hex[:12], roomId=room.id, name=name, isCurrent=False, parentLayoutId=base.id, items=items, zones=base.zones,
        metrics=validation.metrics, createdBy="agent", requestText=theme or f"{len(photos or [])} inspiration photo(s)", createdAt=_now(), updatedAt=_now(), style=plan["style"],
    )
    await ctx.repo.insert("layouts", layout.model_dump())
    return FurnishResult(layout, plan["style"], placed, skipped, compose_reply(plan, placed, skipped))


THEME_MAX = 300
_WS = re.compile(r"\s+")


def clean_theme(text: str) -> str:
    return _WS.sub(" ", text).strip()[:THEME_MAX]
