"""The advanced search may recover a fit, but cannot weaken original plan constraints."""
from __future__ import annotations

import pytest

from app.agent import pipeline
from app.catalog import PRESETS
from app.models import AgentPlan, Dimensions, FurnitureItem, Layout, LayoutItem, Room, Zone
from app.services import skeleton_from_dimensions
from app.solver.placement import Solver


def _case():
    sk = skeleton_from_dimensions(Dimensions(l=4, w=4, h=2.6), [], [])
    furniture = {
        **PRESETS,
        "long_wall": FurnitureItem(id="long_wall", name="Long wall shelf", category="decor", kind="decor", dims={"w": 4, "d": .4, "h": 1}, source="manual"),
        "short_wall": FurnitureItem(id="short_wall", name="Short wall shelf", category="decor", kind="decor", dims={"w": 3.2, "d": .4, "h": 1}, source="manual"),
    }
    items = [LayoutItem(id="north", furnitureId="long_wall", x=2, z=.2, rotation=0, locked=True),
             LayoutItem(id="south", furnitureId="long_wall", x=2, z=3.8, rotation=180, locked=True),
             LayoutItem(id="west", furnitureId="short_wall", x=.2, z=2, rotation=90, locked=True),
             LayoutItem(id="east", furnitureId="short_wall", x=3.8, z=2, rotation=270, locked=True)]
    room = Room(id="r", name="Room", skeleton=sk, source="manual", createdAt="2026-09-26T00:00:00Z")
    base = Layout(id="l", roomId="r", name="Current Room", isCurrent=True, items=items,
                  createdAt="2026-09-26T00:00:00Z", updatedAt="2026-09-26T00:00:00Z")
    plan = AgentPlan(intent="fit_item", actions=[{"type": "add", "item": "floor_lamp"}], reply="I found a spot for the lamp.")
    return room, base, furniture, plan


def test_real_open_floor_fallback_when_every_wall_is_occupied():
    room, base, catalog, plan = _case()
    original = Solver(room.skeleton, catalog, base.items).solve(plan)
    assert not original.ok
    fallback = pipeline._advanced_fallback(plan, room, base, catalog, None, [])
    assert fallback is not None
    result, new_furniture = fallback
    assert result.ok and not result.validation.blocked and result.validation.metrics.conflicts == 0
    assert result.items[:4] == base.items and len(result.items) == 5
    assert new_furniture is None


@pytest.mark.parametrize("change", [
    {"actions": [{"type": "add", "item": "floor_lamp", "zone": "west wall"}]},
    {"actions": [{"type": "add", "item": "floor_lamp", "zone": "window wall or east wall"}]},
    {"actions": [{"type": "add", "item": "floor_lamp", "zone": "corner"}]},
    {"actions": [{"type": "add", "item": "floor_lamp", "rotation": 90}]},
    {"actions": [{"type": "add", "item": "floor_lamp"}, {"type": "remove", "item": "north"}]},
    {"actions": [{"type": "remove", "item": "north"}]},
    {"constraints": [{"type": "clear_zone", "w_m": 1, "d_m": 1}]},
    {"constraints": [{"type": "keep_clear", "feature": "wall"}]},
])
def test_unsupported_plan_semantics_skip_fallback(change):
    room, base, catalog, plan = _case()
    plan = AgentPlan.model_validate({**plan.model_dump(), **change})
    assert pipeline._advanced_fallback(plan, room, base, catalog, None, []) is None


def test_locked_move_and_unconfirmed_import_cannot_bypass_rejection():
    room, base, catalog, plan = _case()
    locked = AgentPlan(intent="fit_item", actions=[{"type": "move", "item": "north"}], reply="Move it")
    assert pipeline._advanced_fallback(locked, room, base, catalog, None, []) is None
    photo = PRESETS["floor_lamp"].model_copy(update={"id": "photo", "source": "photo", "dimensionsConfirmed": False})
    catalog[photo.id] = photo
    assert pipeline._advanced_fallback(plan, room, base, catalog, photo.id, []) is None


def test_plan_and_memory_locks_survive_mapping():
    room, base, catalog, _ = _case()
    base.items[0].locked = False
    plan = AgentPlan(intent="fit_item", actions=[{"type": "move", "item": "north"}], reply="Move it",
                     constraints=[{"type": "lock", "item": "north"}])
    assert pipeline._advanced_fallback(plan, room, base, catalog, None, []) is None
    plan.constraints = []
    assert pipeline._advanced_fallback(plan, room, base, catalog, None, ["never move the north"]) is None
    assert pipeline._advanced_fallback(plan, room, base, catalog, None, ["Keep the shelf on the north wall"]) is None


def test_base_zones_are_preserved_and_cannot_be_newly_occupied():
    room, base, catalog, plan = _case()
    base.zones = [Zone(label="Exercise", x=1.5, z=1.5, w=1, d=1)]
    result, _ = pipeline._advanced_fallback(plan, room, base, catalog, None, [])
    assert result.zones == base.zones
    base.zones = [Zone(label="Keep free", x=.4, z=.4, w=3.2, d=3.2)]
    assert pipeline._advanced_fallback(plan, room, base, catalog, None, []) is None


def test_pipeline_saves_fallback_without_mutating_current_room(client):
    room, base, catalog, plan = _case()
    body = client.post("/rooms", json={"dimensions": {"l": 4, "w": 4, "h": 2.6}}).json()
    room_id, layout_id = body["room"]["id"], body["currentLayout"]["id"]
    owner = body["room"]["userId"]
    # Seed this catalog through the same store used by the request-scoped repository.
    for key in ("long_wall", "short_wall"):
        client.app.state.ctx.repo._db["furniture"].append({**catalog[key].model_dump(), "userId": owner})
    saved = client.put(f"/layouts/{layout_id}", json={"items": [i.model_dump() for i in base.items], "source": "editor"})
    assert saved.status_code == 200, saved.text
    calls = []

    async def answer(*args, **kwargs):
        calls.append(1)
        return plan.model_dump(exclude_none=True)

    client.app.state.ctx.gemini.plan = answer
    response = client.post("/agent/request", json={"text": "Place a lamp where it fits", "roomId": room_id, "baseLayoutId": layout_id})
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "ok" and len(out["layout"]["items"]) == 5, out
    assert len(calls) == 1  # fallback recovered before asking Gemini to change the request
    current = client.get(f"/layouts/{layout_id}").json()["layout"]
    assert current["items"] == [item.model_dump() for item in base.items]
    assert out["layout"]["parentLayoutId"] == layout_id


def test_primary_success_never_invokes_fallback(client, bedroom, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("primary success must remain unchanged")
    monkeypatch.setattr(pipeline, "_advanced_fallback", forbidden)
    out = client.post("/agent/request", json={"text": "add a desk", "roomId": bedroom["roomId"], "baseLayoutId": bedroom["currentId"]})
    assert out.status_code == 200 and out.json()["status"] == "ok"
