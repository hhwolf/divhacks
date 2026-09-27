"""Placement solver behaviour that the API tests don't pin down: honest nearest misses and genuinely different options."""

import math

from app.catalog import PRESETS
from app.models import Dimensions, Door, LayoutItem, RoomSkeleton, Window
from app.planning_models import PlacementPlan as GeminiPlan
from app.services import load_sample, seed_items, skeleton_from_dimensions
from app.solver.advanced_placement import DISTINCT_M, Solver

BLOCKED_WINDOW_WALL = skeleton_from_dimensions(
    Dimensions(l=4.0, w=2.5, h=2.6), [Door(wall=2, offset=0.2, width=0.8, swing="in", hinge="left")], [Window(wall=0, offset=1.0, width=1.0, sillHeight=0.9, height=1.2)],
)
WARDROBES = [LayoutItem(id=f"wardrobe_{i}", furnitureId="wardrobe", x=0.5 + i, z=0.3, rotation=0, locked=True) for i in range(3)]


def _desk_plan(width: float) -> GeminiPlan:
    return GeminiPlan(intent="fit_item", item={"type": "desk", "w_m": width, "d_m": 0.6, "h_m": 0.75},
                      constraints=[{"type": "adjacent", "item": "desk", "feature": "window"}], explanation="x")


def test_rejection_suggests_a_wall_only_when_the_item_fits_there() -> None:
    miss = Solver(BLOCKED_WINDOW_WALL, PRESETS, WARDROBES).solve(_desk_plan(2.0)).nearest_miss
    assert miss == "it's 3' 3\" too wide for the window wall; it would fit on the door wall; want me to try that?"


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


def test_internal_plan_rejects_coordinates_and_invalid_dimensions() -> None:
    import pytest
    from pydantic import ValidationError

    for item in ({"type": "desk", "x": 1}, {"type": "desk", "w_m": -1, "d_m": 1},
                 {"type": "desk", "w_m": 1}, {"type": "desk", "w_m": float("nan"), "d_m": 1}):
        with pytest.raises(ValidationError):
            GeminiPlan(intent="fit_item", item=item)
    with pytest.raises(ValidationError):
        GeminiPlan(intent="payment_check")
    with pytest.raises(ValidationError):
        GeminiPlan(intent="make_space", constraints=[{"type": "clear_zone", "w_m": float("inf"), "d_m": 1}])


def test_existing_hard_errors_are_never_reported_as_success() -> None:
    data = load_sample("studio")
    sk = RoomSkeleton.model_validate(data["skeleton"])
    items = [LayoutItem(id="outside", furnitureId="wardrobe", x=-5, z=-5, rotation=0, locked=True)]
    result = Solver(sk, PRESETS, items).solve(GeminiPlan(intent="fit_item", item={"type": "desk"}))
    assert not result.ok
    unchanged = Solver(sk, PRESETS, items).solve(GeminiPlan(intent="keep_clear"))
    assert not unchanged.ok and any(v.rule == "bounds" for v in unchanged.violations)


def test_locked_and_import_dimension_guards_are_enforced() -> None:
    data = load_sample("studio")
    sk = RoomSkeleton.model_validate(data["skeleton"])
    items = [LayoutItem(id="my_desk", furnitureId="desk", x=2, z=2, rotation=0, locked=True)]
    result = Solver(sk, PRESETS, items).solve(GeminiPlan(intent="fit_item", item={"type": "desk"}, operation="move"))
    assert not result.ok and any(v.rule == "locked" for v in result.violations)
    photo = PRESETS["desk"].model_copy(update={"id": "imported_photo", "source": "photo", "dimensionsConfirmed": False})
    result = Solver(sk, {**PRESETS, photo.id: photo}, [], photo.id).solve(GeminiPlan(intent="fit_item", item={"type": "desk"}))
    assert not result.ok and "confirm" in result.nearest_miss


def test_add_and_move_operations_do_not_change_meaning() -> None:
    data = load_sample("studio")
    sk = RoomSkeleton.model_validate(data["skeleton"])
    items = [LayoutItem(id="desk_existing", furnitureId="desk", x=1, z=0.3, rotation=0, locked=True)]
    added = Solver(sk, PRESETS, items).solve(GeminiPlan(intent="fit_item", item={"type": "desk"}, operation="add"))
    assert added.ok and len(added.items) == 2
    assert added.items[0] == items[0]
    moved = Solver(sk, PRESETS, []).solve(GeminiPlan(intent="fit_item", item={"type": "desk"}, operation="move"))
    assert not moved.ok and moved.new_furniture is None


def test_required_adjacency_is_never_relaxed_in_alternatives() -> None:
    data = load_sample("studio")
    sk = RoomSkeleton.model_validate(data["skeleton"])
    plan = _desk_plan(1.2)
    results = Solver(sk, PRESETS, seed_items(data["objects"]), "desk").design(plan)
    assert all(not result.relaxed for result in results)


def test_extra_memory_locks_preserve_the_item() -> None:
    data = load_sample("studio")
    sk = RoomSkeleton.model_validate(data["skeleton"])
    items = [LayoutItem(id="my_desk", furnitureId="desk", x=2, z=2, rotation=0, locked=False)]
    result = Solver(sk, PRESETS, items, extra_locks=["desk"]).solve(GeminiPlan(intent="fit_item", item={"type": "desk"}, operation="move"))
    assert not result.ok and "locked" in result.nearest_miss
