import json
from typing import Any

from app.agent.prompts import memory_locks, stated_preferences
from app.integrations.gemini import mock_plan_for
from app.models import GeminiPlan, PlanOut, RoomSkeleton
from app.solver.grid import item_rect
from app.solver.skeleton import door_clearance_rect, opening_span, window_band
from fastapi.testclient import TestClient

from tests.conftest import FIXTURES

DESK_Q = "Will this fit beside my window without moving my bed? http://testserver/fixtures/listings/desk"
YOGA_Q = "make space for yoga, keep my dresser"
DIMS = {"desk": (1.2, 0.6), "imp": (1.2, 0.6), "nightstand": (0.45, 0.4), "bookshelf_low": (0.8, 0.3), "plant": (0.4, 0.4)}


def _ask(client: TestClient, bedroom: dict, text: str, layout_id: str | None = None, **extra: Any) -> dict:
    r = client.post("/agent/request", json={"text": text, "roomId": bedroom["roomId"], "layoutId": layout_id or bedroom["currentId"], **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _item(layout: dict, prefix: str) -> dict:
    return next(i for i in layout["items"] if i["furnitureId"].startswith(prefix))


def _skeleton(client: TestClient, bedroom: dict) -> RoomSkeleton:
    return RoomSkeleton.model_validate(client.get(f"/rooms/{bedroom['roomId']}").json()["room"]["skeleton"])


def _names(client: TestClient, bedroom: dict) -> list[str]:
    return [l["name"] for l in client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]]


def _patch_gemini(client: TestClient, plans: list[dict]) -> list[list[str] | None]:
    calls: list[list[str] | None] = []

    async def fake_plan(system_prompt: str, user_text: str, violations: list[str] | None = None) -> dict:
        calls.append(violations)
        return json.loads(json.dumps(plans[min(len(calls) - 1, len(plans) - 1)]))

    client.app.state.ctx.gemini.plan = fake_plan  # type: ignore[method-assign]
    return calls


def test_mock_plans_are_valid_stage1_output() -> None:
    for f in (FIXTURES / "plans").glob("*.json"):
        plan = GeminiPlan.model_validate_json(f.read_text())
        assert "placement" not in json.loads(f.read_text()), f"{f.name}: Gemini never places"
        assert plan.explanation
    assert "x" not in GeminiPlan.model_json_schema()["properties"] and "placement" not in GeminiPlan.model_json_schema()["properties"]


def test_marketplace_desk_request(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, DESK_Q)
    assert out["status"] == "ok"
    plan = PlanOut.model_validate(out["plan"])
    layout = out["layout"]
    assert out["layoutId"] == layout["id"]
    assert layout["name"] == "Marketplace Desk" and layout["kind"] == "variant" and layout["parentLayoutId"] == bedroom["currentId"]
    assert layout["createdBy"] == "agent" and layout["requestText"].startswith("Will this fit")
    assert _item(layout, "bed_double") == _item(bedroom["current"], "bed_double")
    desk = _item(layout, "imp_")
    assert plan.placement is not None and (plan.placement.x, plan.placement.z, plan.placement.rotation) == (desk["x"], desk["z"], desk["rotation"])
    assert plan.item is not None and plan.item.type == "desk" and plan.item.price_usd == 80
    sk = _skeleton(client, bedroom)
    rect = item_rect(desk["x"], desk["z"], desk["rotation"], type("D", (), {"w": 1.2, "d": 0.6})())  # type: ignore[arg-type]
    a, b = opening_span(sk, sk.windows[0])
    gap_x = max(0.0, max(rect.x0, min(a[0], b[0])) - min(rect.x1, max(a[0], b[0])))
    gap_z = max(0.0, rect.z0 - max(a[1], b[1]))
    assert (gap_x**2 + gap_z**2) ** 0.5 <= 0.3  # beside the window...
    band = window_band(sk, sk.windows[0], 0.6)
    assert not (rect.x0 < band.x1 - 1e-6 and band.x0 < rect.x1 - 1e-6 and rect.z0 < band.z1 - 1e-6 and band.z0 < rect.z1 - 1e-6)  # ...not in front of it
    assert layout["metrics"]["conflicts"] == 0 and layout["metrics"]["warnings"] == []
    assert "window" in out["reply"]
    assert out["links"] == [f"roomplanner://layout/{layout['id']}", f"http://localhost:5173/layout/{layout['id']}"]
    names = _names(client, bedroom)
    assert names[:3] == ["Original Room", "Current Room", "Marketplace Desk"] and len(names) == 2 + len(out["options"])
    assert client.get(f"/layouts/{bedroom['currentId']}").json()["layout"]["items"] == bedroom["current"]["items"]
    user = client.app.state.ctx.repo._db["users"][0]  # type: ignore[attr-defined]
    assert "never move the bed" in user["memories"]  # written back to (mock) Backboard in the same turn


def test_yoga_request_makes_minimal_moves(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, YOGA_Q)
    assert out["status"] == "ok"
    layout, plan = out["layout"], PlanOut.model_validate(out["plan"])
    assert layout["name"] == "Yoga corner"
    for fid in ("bed_double", "dresser"):
        assert _item(layout, fid) == _item(bedroom["current"], fid)
    zone = layout["zones"][0]
    assert zone["label"] == "Yoga" and zone["type"] == "clear" and sorted([zone["w"], zone["d"]]) == [1.2, 1.8]
    sk = _skeleton(client, bedroom)
    door = door_clearance_rect(sk, sk.doors[0], 0.9)
    assert zone["z"] + zone["d"] <= door.z0 + 1e-6 or zone["x"] >= door.x1 - 1e-6 or zone["x"] + zone["w"] <= door.x0 + 1e-6  # not in the door's way
    assert 1 <= len(plan.moves) <= 2 and all(m.name not in ("Double bed", "Dresser") for m in plan.moves)
    assert not [v for v in client.get(f"/layouts/{layout['id']}").json()["validation"]["violations"] if v["rule"] in ("clear_zone", "overlap", "bounds")]
    assert "does yoga every morning" in client.app.state.ctx.repo._db["users"][0]["memories"]  # type: ignore[attr-defined]


def test_memory_non_negotiables_become_locks(client: TestClient, bedroom: dict) -> None:
    moved_first = {m["name"] for m in _ask(client, bedroom, YOGA_Q)["plan"]["moves"]}
    assert moved_first == {"Nightstand"}
    _ask(client, bedroom, "never move my nightstand. make space for yoga")  # stated rule -> Backboard
    users = client.app.state.ctx.repo._db["users"]  # type: ignore[attr-defined]
    assert "never move the nightstand" in users[0]["memories"]
    out = _ask(client, bedroom, YOGA_Q)
    if out["status"] == "ok":
        assert "Nightstand" not in {m["name"] for m in out["plan"]["moves"]}
        assert _item(out["layout"], "nightstand") == _item(bedroom["current"], "nightstand")
    else:
        assert "largest free zone" in out["reply"]


def test_keep_clear_moves_the_blocking_item(client: TestClient, bedroom: dict) -> None:
    v = client.post(f"/layouts/{bedroom['currentId']}/fork", json={"name": "Desk at window"}).json()
    desk = {"id": "desk_9", "furnitureId": "desk", "x": 2.2, "z": 0.9, "rotation": 90, "locked": False}
    assert client.put(f"/layouts/{v['id']}", json={"items": v["items"] + [desk], "version": 1}).status_code == 200
    out = _ask(client, bedroom, "I don't want my desk blocking the window", layout_id=v["id"])
    assert out["status"] == "ok" and out["layout"]["parentLayoutId"] == v["id"]
    plan = PlanOut.model_validate(out["plan"])
    assert [m.item for m in plan.moves] == ["desk_9"]
    moved = next(i for i in out["layout"]["items"] if i["id"] == "desk_9")
    sk = _skeleton(client, bedroom)
    band, r = window_band(sk, sk.windows[0], 0.6), item_rect(moved["x"], moved["z"], moved["rotation"], type("D", (), {"w": 1.2, "d": 0.6})())  # type: ignore[arg-type]
    assert not (r.x0 < band.x1 - 1e-6 and band.x0 < r.x1 - 1e-6 and r.z0 < band.z1 - 1e-6 and band.z0 < r.z1 - 1e-6)
    assert out["layout"]["metrics"]["conflicts"] == 0


def test_keep_clear_with_nothing_blocking_creates_no_variant(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, "I don't want anything blocking the window")
    assert out["status"] == "ok" and out["layout"] is None and "nothing is blocking" in out["reply"].lower()
    assert len(_names(client, bedroom)) == 2


def test_rank_variants_answers_without_a_new_variant(client: TestClient, bedroom: dict) -> None:
    desk = _ask(client, bedroom, DESK_Q)["layout"]
    before = _names(client, bedroom)
    out = _ask(client, bedroom, "Which layout is better for studying?")
    assert out["status"] == "ok" and out["layout"] is None and out["layoutId"] is None and out["options"] == []
    assert out["ranking"][0]["layoutId"] == desk["id"] and "has a desk" in out["ranking"][0]["reason"]
    assert {r["layoutId"] for r in out["ranking"]} == {l["id"] for l in client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]}
    assert "1. Marketplace Desk" in out["reply"]
    assert _names(client, bedroom) == before  # ranking never saves a variant


def test_variant_names_dedupe(client: TestClient, bedroom: dict) -> None:
    _ask(client, bedroom, YOGA_Q)
    assert _ask(client, bedroom, YOGA_Q)["layout"]["name"] == "Yoga corner (2)"


def test_unknown_request_clarifies(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, "what's the weather like")
    assert out["status"] == "clarify" and out["layout"] is None
    assert out["reply"].endswith("?") and out["plan"]["question"] == out["reply"]
    assert len(_names(client, bedroom)) == 2


def test_mock_retry_relaxes_adjacency() -> None:
    assert [c["type"] for c in mock_plan_for(DESK_Q, retry=True)["constraints"]] == ["lock"]


BIG_BY_WINDOW = {
    "intent": "fit_item", "item": {"type": "desk", "name": "Banquet desk", "w_m": 3.3, "d_m": 0.6, "h_m": 0.75},
    "constraints": [{"type": "adjacent", "item": "desk", "feature": "window"}], "variantName": "Huge desk", "explanation": "Beside the window.",
}
DESK_ANYWHERE = {"intent": "fit_item", "item": {"type": "desk", "w_m": 1.0, "d_m": 0.5, "h_m": 0.75}, "constraints": [], "variantName": "Small desk", "explanation": "It fits."}


def test_retry_feeds_violations_back_and_succeeds(client: TestClient, bedroom: dict) -> None:
    calls = _patch_gemini(client, [BIG_BY_WINDOW, DESK_ANYWHERE])
    out = _ask(client, bedroom, "Will a banquet desk fit by the window?")
    assert out["status"] == "ok" and out["layout"]["name"] == "Small desk"
    assert len(calls) == 2 and calls[0] is None and calls[1] and "too wide for the window wall" in calls[1][-1]
    new = next(f for f in client.app.state.ctx.repo._db["furniture"] if f["id"] == out["plan"]["placement"]["furnitureId"])  # type: ignore[attr-defined]
    assert new["dims"] == {"w": 1.0, "d": 0.5, "h": 0.75} and new["source"] == "manual"  # Gemini's dims became a catalog item


def test_two_failures_reject_with_nearest_miss(client: TestClient, bedroom: dict) -> None:
    calls = _patch_gemini(client, [BIG_BY_WINDOW, BIG_BY_WINDOW])
    out = _ask(client, bedroom, "Will a banquet desk fit by the window?")
    assert out["status"] == "rejected" and out["layout"] is None and len(calls) == 2
    assert "cm too wide for the window wall" in out["reply"] and "any other wall" in out["reply"]  # 3.3 m fits no wall: say so, don't guess
    assert _names(client, bedroom) == ["Original Room", "Current Room"]


def test_invalid_json_then_valid_plan(client: TestClient, bedroom: dict) -> None:
    calls = _patch_gemini(client, [{"intent": "fit_item", "x": 1.0}, DESK_ANYWHERE])
    out = _ask(client, bedroom, "fit a small desk")
    assert out["status"] == "ok" and calls[1] and "plan JSON invalid" in calls[1][0]


def test_gemini_forgetting_a_lock_changes_nothing(client: TestClient, bedroom: dict) -> None:
    move_bed = {"intent": "fit_item", "item": {"type": "bed"}, "constraints": [{"type": "adjacent", "item": "bed", "feature": "door"}], "variantName": "Bed by door", "explanation": "Moved the bed."}
    _patch_gemini(client, [move_bed, move_bed])
    out = _ask(client, bedroom, "move my bed next to the door")
    assert out["status"] == "rejected" and out["violations"][0]["rule"] == "locked" and "locked" in out["reply"]


def test_agent_never_writes_base_or_current(client: TestClient, bedroom: dict) -> None:
    base_before = client.get(f"/layouts/{bedroom['baseId']}").json()["layout"]
    for text in (DESK_Q, YOGA_Q, "I don't want my desk blocking the window"):
        _ask(client, bedroom, text)
    assert client.get(f"/layouts/{bedroom['baseId']}").json()["layout"] == base_before
    cur = client.get(f"/layouts/{bedroom['currentId']}").json()["layout"]
    assert cur["items"] == bedroom["current"]["items"] and cur["version"] == 1


def test_agent_requests_are_logged(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, YOGA_Q)
    log = next(l for l in client.app.state.ctx.repo._db["agent_requests"] if l["id"] == out["requestId"])  # type: ignore[attr-defined]
    assert log["status"] == "ok" and log["resultLayoutId"] == out["layout"]["id"] and log["sourceLayoutId"] == bedroom["currentId"]
    assert log["requestText"] == YOGA_Q and log["geminiPlan"][0]["intent"] == "make_space" and log["solverAttempts"][0]["ok"] is True
    assert log["validation"]["metrics"]["conflicts"] == 0 and isinstance(log["latencyMs"], int)
    desk = _ask(client, bedroom, DESK_Q)
    desk_log = next(l for l in client.app.state.ctx.repo._db["agent_requests"] if l["id"] == desk["requestId"])  # type: ignore[attr-defined]
    assert desk_log["attachments"][0]["type"] == "link" and desk_log["attachments"][0]["furnitureId"].startswith("imp_")


def test_request_validation(client: TestClient, bedroom: dict) -> None:
    other = client.post("/rooms", json={"sample": "studio"}).json()
    assert client.post("/agent/request", json={"text": "hi", "roomId": "nope", "layoutId": bedroom["currentId"]}).status_code == 404
    assert client.post("/agent/request", json={"text": "hi", "roomId": bedroom["roomId"], "layoutId": other["currentLayout"]["id"]}).status_code == 422
    legacy = client.post("/agent/request", json={"text": YOGA_Q, "roomId": bedroom["roomId"], "baseLayoutId": bedroom["currentId"], "channel": "app"})
    assert legacy.status_code == 200 and legacy.json()["status"] == "ok"
    blocked = client.post("/agent/request", json={"text": "will this fit?", "roomId": bedroom["roomId"], "layoutId": bedroom["currentId"], "link": "http://127.0.0.1:9/listing"})
    assert blocked.status_code == 422 and "screenshot" in blocked.json()["detail"]["message"]


def test_photo_data_uri_is_imported(client: TestClient, bedroom: dict) -> None:
    import base64

    jpg = base64.b64encode((FIXTURES / "listings" / "desk.jpg").read_bytes()).decode()
    out = _ask(client, bedroom, "Will this fit?", photo=f"data:image/jpeg;base64,{jpg}")
    log = next(l for l in client.app.state.ctx.repo._db["agent_requests"] if l["id"] == out["requestId"])  # type: ignore[attr-defined]
    assert log["attachments"][0]["type"] == "photo" and log["attachments"][0]["url"].startswith("/blob/photos/")


def test_memory_parsing() -> None:
    assert memory_locks(["never move the bed", "Never touch my dresser again!", "does yoga every morning", "don't ever move my desk."]) == ["bed", "dresser", "desk"]
    assert stated_preferences("please never move my bed, thanks") == ["never move the bed"]
    assert stated_preferences("fit a desk without moving my bed") == []


def test_options_follow_the_interior_designer_format(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, DESK_Q)
    opts = out["options"]
    assert 1 <= len(opts) <= 3 and out["recommended"] == opts[0]["variantName"] and out["layoutId"] == opts[0]["layoutId"]
    assert out["roomSummary"].startswith("A 11 by 10 ft room (3.4 x 3 m)")
    assert len({o["layoutId"] for o in opts}) == len(opts) and len({o["variantName"] for o in opts}) == len(opts)
    for o in opts:
        assert o["explanation"] and o["tradeoff"] and o["validation"]["ok"] is True and 1 <= len(o["variantName"].split()) <= 4
        saved = client.get(f"/layouts/{o['layoutId']}").json()
        assert saved["layout"]["kind"] == "variant" and saved["validation"]["metrics"]["conflicts"] == 0
        assert "bed_double_1" not in o["moved"]  # locked items never show up as moved
    assert out["plan"]["placement"] == opts[0]["placement"]
    places = [(o["placement"]["x"], o["placement"]["z"], o["placement"]["rotation"]) for o in opts]
    assert len(set(places)) == len(places)


def test_desk_options_never_face_a_wall(client: TestClient, bedroom: dict) -> None:
    """The chair side of every desk option has room to pull the chair out (the validator alone only asks for *a* free edge)."""
    out = _ask(client, bedroom, DESK_Q)
    sk = _skeleton(client, bedroom)
    for o in out["options"]:
        p = o["placement"]
        fx, fz = {0: (0, 1), 90: (1, 0), 180: (0, -1), 270: (-1, 0)}[p["rotation"]]
        w, d = (1.2, 0.6) if p["rotation"] in (0, 180) else (0.6, 1.2)
        chair_x, chair_z = p["x"] + fx * (w / 2 + 0.4), p["z"] + fz * (d / 2 + 0.4)
        assert 0 < chair_x < sk.dimensions.l and 0 < chair_z < sk.dimensions.w, o["variantName"]


def test_photon_style_request_needs_no_ids(client: TestClient) -> None:
    empty = client.post("/agent/request", json={"text": "will this desk fit?", "channel": "imessage"}).json()
    assert empty["status"] == "clarify" and "scan your room" in empty["reply"]
    older = client.post("/rooms", json={"sample": "studio"}).json()
    newer = client.post("/rooms", json={"sample": "nyc-bedroom"}).json()
    out = client.post("/agent/request", json={"text": "make space for yoga", "channel": "imessage"}).json()
    assert out["status"] == "ok" and out["roomId"] == newer["room"]["id"] and out["sourceLayoutId"] == newer["currentLayout"]["id"]
    assert out["links"][1].endswith(f"/layout/{out['layoutId']}")  # what the Photon agent texts back
    client.patch(f"/rooms/{older['room']['id']}", json={"name": "Studio (used last)"})  # touching a room makes it the default
    assert client.post("/agent/request", json={"text": "make space for yoga", "channel": "imessage"}).json()["roomId"] == older["room"]["id"]
    log = client.app.state.ctx.repo._db["agent_requests"][-1]  # type: ignore[attr-defined]
    assert log["channel"] == "imessage"


def test_gemini_words_the_result_when_live(client: TestClient, bedroom: dict) -> None:
    async def fake_narrate(designer_prompt: str, facts: dict, draft: dict) -> dict:
        assert "Interior Designer" in designer_prompt and facts["options"] and draft["options"]
        return {"room_summary": "A small bedroom.", "recommended_index": 0, "reply": "Yes! It fits by the window.",
                "options": [{"index": 0, "variantName": "Window Desk", "explanation": "Daylight from the side.", "tradeoff": "A bit snug."}]}

    client.app.state.ctx.gemini.narrate = fake_narrate  # type: ignore[method-assign]
    out = _ask(client, bedroom, DESK_Q)
    assert out["reply"] == "Yes! It fits by the window." and out["recommended"] == "Window Desk" and out["roomSummary"] == "A small bedroom."
    assert out["options"][0]["tradeoff"] == "A bit snug."
    if len(out["options"]) > 1:
        assert out["options"][1]["explanation"]  # missing from Gemini's answer: the deterministic draft fills it

    async def broken(designer_prompt: str, facts: dict, draft: dict) -> dict:
        return {"reply": 42}

    client.app.state.ctx.gemini.narrate = broken  # type: ignore[method-assign]
    assert _ask(client, bedroom, DESK_Q)["reply"].startswith("Yes, it fits")


def test_rent_and_payment_are_routed_by_the_plan(client: TestClient, bedroom: dict) -> None:
    calls: list[str] = []

    async def plan(system_prompt: str, user_text: str, violations: list[str] | None = None) -> dict:
        calls.append(user_text)
        return {"intent": "payment_check", "payment": {"purpose": "application_fee", "amount": 120}, "constraints": [], "explanation": "Checking."}

    client.app.state.ctx.gemini.plan = plan  # type: ignore[method-assign]
    out = _ask(client, bedroom, "the broker wants a hundred and twenty bucks to apply")  # no keywords: Gemini decides
    assert calls and out["status"] == "rejected" and out["quote"]["status"] == "blocked" and "$20" in out["reply"]
