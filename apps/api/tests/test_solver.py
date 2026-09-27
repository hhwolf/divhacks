"""Placement solver behaviour that the API tests don't pin down: honest nearest misses and genuinely different options."""

import math

from app.catalog import PRESETS
from app.models import Dimensions, Door, GeminiPlan, LayoutItem, RoomSkeleton, Window
from app.services.rooms import load_sample, seed_items, skeleton_from_dimensions
from app.solver.placement import DISTINCT_M, Solver

BLOCKED_WINDOW_WALL = skeleton_from_dimensions(
    Dimensions(l=4.0, w=2.5, h=2.6), [Door(wall=2, offset=0.2, width=0.8, swing="in", hinge="left")], [Window(wall=0, offset=1.0, width=1.0, sillHeight=0.9, height=1.2)],
)
WARDROBES = [LayoutItem(id=f"wardrobe_{i}", furnitureId="wardrobe", x=0.5 + i, z=0.3, rotation=0, locked=True) for i in range(3)]


def _desk_plan(width: float) -> GeminiPlan:
    return GeminiPlan(intent="fit_item", item={"type": "desk", "w_m": width, "d_m": 0.6, "h_m": 0.75},
                      constraints=[{"type": "adjacent", "item": "desk", "feature": "window"}], explanation="x")


def test_rejection_suggests_a_wall_only_when_the_item_fits_there() -> None:
    miss = Solver(BLOCKED_WINDOW_WALL, PRESETS, WARDROBES).solve(_desk_plan(2.0)).nearest_miss
    assert miss == "it's 100 cm too wide for the window wall; it would fit on the door wall; want me to try that?"


def test_rejection_says_so_when_nothing_fits() -> None:
    miss = Solver(BLOCKED_WINDOW_WALL, PRESETS, WARDROBES).solve(_desk_plan(3.9)).nearest_miss
    assert miss is not None and "too wide for the window wall" in miss and "doesn't fit along any other wall either" in miss


def test_options_are_different_ideas() -> None:
    d = load_sample("studio")
    opts = Solver(RoomSkeleton.model_validate(d["skeleton"]), PRESETS, seed_items(d["objects"]), "desk").design(_desk_plan(1.2))
    assert 2 <= len(opts) <= 3 and all(o.ok for o in opts)
    spots = [(o.placement.x, o.placement.z, o.placement.rotation) for o in opts if o.placement]
    for i, a in enumerate(spots):
        for j, b in enumerate(spots[:i]):
            turned_twin_of_first = j == 0 and a[2] % 180 != b[2] % 180
            assert math.dist(a[:2], b[:2]) >= DISTINCT_M or turned_twin_of_first, (a, b)
