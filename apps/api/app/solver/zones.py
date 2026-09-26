"""Zone phrases from the agent plan ("window wall, beside window", "east wall, centered", ...) -> placement specs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, get_args

from app.models import RoomSkeleton
from app.solver.skeleton import Compass, wall_by_compass

Feature = Literal["window", "door", "outlet"]
_COMPASS_WALL = re.compile(r"\b(north|south|east|west)(?:ern)?\s+wall\b")
_NEAR = r"(?:beside|near|by|next to|close to|nearest|adjacent to)\s+(?:the\s+|my\s+|a\s+)?"


@dataclass(frozen=True)
class ZoneSpec:
    """Where an item may go: flush against `wall` (None = any wall), scored by closeness to `feature` / the wall center / a corner."""

    wall: int | None = None
    feature: Feature | None = None
    centered: bool = False
    corner: bool = False
    label: str = ""


def wall_label(sk: RoomSkeleton, wall: int) -> str:
    if any(w.wall == wall for w in sk.windows):
        return "window wall"
    if any(d.wall == wall for d in sk.doors):
        return "door wall"
    for word in get_args(Compass):
        if wall_by_compass(sk, word) == wall:
            return f"{word} wall"
    return f"wall {wall}"


def opposite_wall(sk: RoomSkeleton, wall: int) -> int:
    """The wall whose midpoint is farthest from `wall`'s midpoint."""
    w = sk.walls[wall]
    mx, mz = (w.x1 + w.x2) / 2, (w.z1 + w.z2) / 2
    return max(range(len(sk.walls)), key=lambda i: ((sk.walls[i].x1 + sk.walls[i].x2) / 2 - mx) ** 2 + ((sk.walls[i].z1 + sk.walls[i].z2) / 2 - mz) ** 2)


def parse_zone(sk: RoomSkeleton, phrase: str | None) -> list[ZoneSpec]:
    """Alternatives separated by ' or ' / ';' are tried in order by the solver."""
    parts = [p.strip() for p in re.split(r"\s+or\s+|;", phrase or "") if p.strip()] or [""]
    return [_parse_one(sk, p) for p in parts]


def _parse_one(sk: RoomSkeleton, phrase: str) -> ZoneSpec:
    p = phrase.lower()
    wall: int | None = None
    feature: Feature | None = None
    if "window wall" in p and sk.windows:
        wall = sk.windows[0].wall
    elif "door wall" in p and sk.doors:
        wall = sk.doors[0].wall
    elif m := _COMPASS_WALL.search(p):
        wall = wall_by_compass(sk, m.group(1))  # type: ignore[arg-type]
    elif re.search(r"opposite\s+(?:the\s+|my\s+)?door", p) and sk.doors:
        wall = opposite_wall(sk, sk.doors[0].wall)
    elif re.search(r"opposite\s+(?:the\s+|my\s+)?window", p) and sk.windows:
        wall = opposite_wall(sk, sk.windows[0].wall)

    if re.search(_NEAR + r"window", p) and sk.windows:
        feature = "window"
    elif re.search(_NEAR + r"door", p) and sk.doors:
        feature = "door"
    elif "outlet" in p and sk.outlets:
        feature = "outlet"
    corner = "corner" in p
    if feature == "window" and wall is None and not corner:
        wall = sk.windows[0].wall
    return ZoneSpec(wall=wall, feature=feature, centered="center" in p or "centred" in p, corner=corner, label=phrase.strip())
