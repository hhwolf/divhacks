"""Human labels for walls ("window wall", "door wall", "east wall"), used in solver replies and the Gemini prompt."""

from __future__ import annotations

from typing import get_args

from app.models import RoomSkeleton
from app.solver.skeleton import Compass, wall_by_compass


def wall_label(sk: RoomSkeleton, wall: int) -> str:
    if any(w.wall == wall for w in sk.windows):
        return "window wall"
    if any(d.wall == wall for d in sk.doors):
        return "door wall"
    for word in get_args(Compass):
        if wall_by_compass(sk, word) == wall:
            return f"{word} wall"
    return f"wall {wall}"
