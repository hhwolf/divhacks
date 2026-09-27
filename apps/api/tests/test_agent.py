import json
from typing import Any

import pytest
from app.integrations.gemini import PLAN_SCHEMA, RETRY_ALTERNATIVE, mock_plan_for
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

PLAN_OK = Draft202012Validator(PLAN_SCHEMA)
DESK_Q = "Will this fit beside my window without moving my bed? http://testserver/fixtures/listings/desk"
YOGA_Q = "make space for yoga, keep my dresser"


def _ask(client: TestClient, bedroom: dict, text: str, **extra: Any) -> dict:
    r = client.post("/agent/request", json={"text": text, "roomId": bedroom["roomId"], "baseLayoutId": bedroom["currentId"], "channel": "app", **extra})
    assert r.status_code == 200
    return r.json()


def _bed(layout: dict) -> dict:
    return next(i for i in layout["items"] if i["furnitureId"] == "bed_double")


def _import_desk(client: TestClient) -> dict:
    r = client.post("/furniture/from-link", json={"url": "http://testserver/fixtures/listings/desk"})
    assert r.status_code == 201
    item = r.json()
    confirmed = client.patch(
        f"/furniture/{item['id']}/details",
        json={
            "name": item["name"],
            "dims": item["dims"],
            "category": item["category"],
            "price": item["price"],
            "sourceUrl": item["sourceUrl"],
            "dimensionsConfirmed": True,
        },
    )
    assert confirmed.status_code == 200
    return confirmed.json()


def test_marketplace_desk_request(client: TestClient, bedroom: dict) -> None:
    item = _import_desk(client)
    out = _ask(client, bedroom, "Will this fit beside my window without moving my bed?", furnitureId=item["id"])
    assert out["status"] == "ok"
    PLAN_OK.validate(out["plan"])
    layout = out["layout"]
    assert layout["name"] == "Marketplace Desk" and layout["isCurrent"] is False and layout["parentLayoutId"] == bedroom["currentId"]
    assert layout["createdBy"] == "agent" and layout["requestText"].startswith("Will this fit")
    assert _bed(layout) == _bed(bedroom["current"])
    desk = next(i for i in layout["items"] if i["id"].startswith("imp_"))
    assert desk["rotation"] == 0 and desk["z"] == pytest.approx(0.3)
    assert layout["metrics"]["conflicts"] == 0
    assert "window" in out["reply"] and "to spare" in out["reply"]
    assert out["links"] == [f"roomplanner://layout/{layout['id']}", f"http://localhost:5173/layout/{layout['id']}"]
    names = [l["name"] for l in client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]]
    assert names == ["Current Room", "Marketplace Desk"]
    current = client.get(f"/layouts/{bedroom['currentId']}").json()["layout"]
    assert current["items"] == bedroom["current"]["items"]


def test_app_assistant_rejects_new_furniture_links(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, DESK_Q)
    assert out["status"] == "clarify" and out["layout"] is None
    assert "iMessage/Photon" in out["reply"]
    assert [l["name"] for l in client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]] == ["Current Room"]


def test_basic_addition_recommends_preset_item(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, "Can you add a small desk where it fits best?")
    assert out["status"] == "ok"
    PLAN_OK.validate(out["plan"])
    layout = out["layout"]
    assert layout["name"] == "Add desk" and layout["isCurrent"] is False
    assert _bed(layout) == _bed(bedroom["current"])
    desk = next(i for i in layout["items"] if i["furnitureId"] == "desk")
    assert desk["rotation"] in (0, 90, 180, 270)
    assert layout["metrics"]["conflicts"] == 0
    assert "desk" in out["reply"].lower() and "bed" in out["reply"].lower()


def test_yoga_request_creates_clear_zone(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, YOGA_Q)
    assert out["status"] == "ok"
    PLAN_OK.validate(out["plan"])
    layout = out["layout"]
    assert layout["name"] == "Yoga corner"
    assert _bed(layout) == _bed(bedroom["current"])
    dresser = next(i for i in layout["items"] if i["furnitureId"] == "dresser")
    assert dresser == next(i for i in bedroom["current"]["items"] if i["furnitureId"] == "dresser")
    zone = layout["zones"][0]
    assert zone["label"] == "Yoga" and sorted([zone["w"], zone["d"]]) == [1.2, 1.8]
    assert not [v for v in client.get(f"/layouts/{layout['id']}").json()["validation"]["violations"] if v["rule"] == "clear_zone"]
    assert "yoga" in out["reply"].lower() or "mat" in out["reply"].lower()


def test_variant_names_dedupe(client: TestClient, bedroom: dict) -> None:
    _ask(client, bedroom, YOGA_Q)
    assert _ask(client, bedroom, YOGA_Q)["layout"]["name"] == "Yoga corner (2)"


def test_unknown_request_clarifies(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, "what's the weather like")
    assert out["status"] == "clarify" and out["layout"] is None
    assert out["reply"].endswith("?")
    assert len(client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]) == 1


def test_mock_retry_appends_alternative_zone() -> None:
    plan = mock_plan_for(DESK_Q, retry=True)
    assert plan["actions"][0]["zone"].endswith(f" or {RETRY_ALTERNATIVE}")


def _bad_then(good: dict) -> list[dict]:
    bad = {"intent": "fit_item", "variantName": "Desk by door", "actions": [{"type": "add", "item": "desk_mkt", "zone": "door wall, centered"}], "reply": "Put it by the door."}
    return [bad, good]


def _patch_gemini(client: TestClient, plans: list[dict]) -> list[list[str] | None]:
    calls: list[list[str] | None] = []

    async def fake_plan(system_prompt: str, user_text: str, violations: list[str] | None = None) -> dict:
        calls.append(violations)
        return json.loads(json.dumps(plans[min(len(calls) - 1, len(plans) - 1)]))

    client.app.state.ctx.gemini.plan = fake_plan  # type: ignore[method-assign]
    return calls


def test_retry_after_violation_succeeds(client: TestClient, bedroom: dict) -> None:
    good = {"intent": "fit_item", "variantName": "Desk by window", "actions": [{"type": "add", "item": "desk_mkt", "zone": "window wall, beside window"}], "reply": "Beside the window it goes."}
    calls = _patch_gemini(client, _bad_then(good))
    item = _import_desk(client)
    out = _ask(client, bedroom, "Will this fit beside my window without moving my bed?", furnitureId=item["id"])
    assert out["status"] == "ok" and out["layout"]["name"] == "Desk by window"
    assert len(calls) == 2 and calls[1] and "door swing" in calls[1][0]


def test_two_bad_plans_reject_and_keep_layouts(client: TestClient, bedroom: dict) -> None:
    calls = _patch_gemini(client, _bad_then(_bad_then({})[0]))
    item = _import_desk(client)
    out = _ask(client, bedroom, "Will this fit beside my window without moving my bed?", furnitureId=item["id"])
    assert out["status"] == "rejected" and out["layout"] is None
    assert len(calls) == 2
    assert {v["rule"] for v in out["violations"]} == {"door_clearance"}
    assert "too wide for the door wall" in out["reply"] and out["reply"].endswith("?")
    assert [l["name"] for l in client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]] == ["Current Room"]


def test_plan_moving_locked_bed_is_rejected(client: TestClient, bedroom: dict) -> None:
    locked = {"intent": "fit_item", "variantName": "Nope", "actions": [{"type": "move", "item": "bed", "zone": "east wall"}], "reply": "Moved the bed."}
    _patch_gemini(client, [locked, locked])
    out = _ask(client, bedroom, "move my bed to the east wall")
    assert out["status"] == "rejected"
    assert out["violations"][0]["rule"] == "locked"


def test_agent_requests_are_logged(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, YOGA_Q)
    logs = [l for l in client.app.state.ctx.repo._db["agent_requests"] if l["id"] == out["requestId"]]  # type: ignore[attr-defined]
    assert logs and logs[0]["status"] == "ok" and logs[0]["layoutId"] == out["layout"]["id"] and logs[0]["channel"] == "app"
