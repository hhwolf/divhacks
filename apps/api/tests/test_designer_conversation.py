"""The designer as a conversation: history reaches Gemini, answers don't touch the room, add / remove / redesign all work."""

import json

from app.agent import prompts
from fastapi.testclient import TestClient


def _ask(client: TestClient, room: dict, text: str, base: str | None = None) -> dict:
    r = client.post("/agent/request", json={"text": text, "roomId": room["roomId"], "baseLayoutId": base or room["currentId"], "channel": "app"})
    assert r.status_code == 200, r.text
    return r.json()


def _ids(layout: dict) -> list[str]:
    return sorted(i["furnitureId"] for i in layout["items"])


def test_earlier_turns_reach_gemini_as_conversation(client: TestClient, bedroom: dict) -> None:
    seen: list[dict] = []
    real = client.app.state.ctx.gemini.plan

    async def spy(system_prompt: str, user_text: str, violations: list[str] | None = None, history: list | None = None) -> dict:
        seen.append({"system": system_prompt, "text": user_text, "history": history})
        return await real(system_prompt, user_text, violations=violations, history=history)

    client.app.state.ctx.gemini.plan = spy  # type: ignore[method-assign]
    _ask(client, bedroom, "what do you think of my room?")
    _ask(client, bedroom, "ok, add a sofa")
    said, answered = seen[-1]["history"][-1]
    assert said == "what do you think of my room?" and json.loads(answered)["intent"] == "answer"
    # the catalog Gemini adds from is in the prompt, parseable, and includes pieces the old prompt never listed
    ids = {row["id"] for row in prompts.parse_catalog(seen[-1]["system"])}
    assert {"sofa", "rug", "plant", "wardrobe", "desk"} <= ids


def test_questions_get_answers_and_leave_the_room_alone(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, "what do you think of my room?")
    assert out["status"] == "ok" and out["plan"]["intent"] == "answer" and out["layout"] is None
    assert "11 by 10 ft" in out["reply"]
    assert len(client.get(f"/rooms/{bedroom['roomId']}").json()["layouts"]) == 1


def test_add_then_remove_follows_the_open_layout(client: TestClient, bedroom: dict) -> None:
    added = _ask(client, bedroom, "can you add a rug and a floor lamp")
    assert added["status"] == "ok" and {"rug", "floor_lamp"} <= set(_ids(added["layout"]))
    removed = _ask(client, bedroom, "remove the rug", base=added["layout"]["id"])
    assert removed["status"] == "ok" and "rug" not in _ids(removed["layout"]) and "floor_lamp" in _ids(removed["layout"])
    assert removed["layout"]["parentLayoutId"] == added["layout"]["id"]


def test_remove_everything_keeps_locked_pieces(client: TestClient, bedroom: dict) -> None:
    items = [{**i, "locked": i["furnitureId"] == "bed_double"} for i in bedroom["current"]["items"]]
    assert client.put(f"/layouts/{bedroom['currentId']}", json={"items": items, "source": "editor"}).status_code == 200
    out = _ask(client, bedroom, "can you remove all the furniture")
    assert out["status"] == "ok" and _ids(out["layout"]) == ["bed_double"]
    assert "locked" in out["reply"]


def test_removing_something_that_isnt_there_says_so(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, "remove the desk")
    assert out["layout"] is None and "desk" in out["reply"] and "too wide" not in out["reply"]


def test_new_design_plan_becomes_a_variant(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, "can you make a recommendation for my study / bedroom")
    assert out["status"] == "ok" and out["plan"]["intent"] == "redesign"
    layout = out["layout"]
    assert layout["createdBy"] == "agent" and not layout["isCurrent"] and len(layout["items"]) > len(bedroom["current"]["items"])
    bed = next(i for i in layout["items"] if i["furnitureId"] == "bed_double")
    assert bed == next(i for i in bedroom["current"]["items"] if i["furnitureId"] == "bed_double")  # locked bed untouched
    assert out["options"][0]["layoutId"] == layout["id"] and out["options"][0]["validation"]["ok"]


def test_piece_that_fits_nowhere_is_honest(client: TestClient, bedroom: dict) -> None:
    out = _ask(client, bedroom, "can you add a sofa")
    if out["status"] == "ok":
        assert "sofa" in _ids(out["layout"])
    else:
        assert "sofa" in out["reply"].lower() or "too wide" in out["reply"] or "fit" in out["reply"]


def test_gemini_down_falls_back_to_the_offline_planner_and_says_so(client: TestClient, bedroom: dict) -> None:
    async def down(*args: object, **kwargs: object) -> dict:
        raise RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand.")

    client.app.state.ctx.gemini.plan = down  # type: ignore[method-assign]
    out = _ask(client, bedroom, "can you add a rug and a floor lamp")
    assert out["status"] == "ok" and {"rug", "floor_lamp"} <= set(_ids(out["layout"]))
    assert out["reply"].startswith("(Gemini didn't answer, so this is my quick offline answer")


def test_actions_given_only_inside_options_still_change_the_room(client: TestClient, bedroom: dict) -> None:
    async def options_only(*args: object, **kwargs: object) -> dict:
        return {"intent": "fit_item", "reply": "A rug fits in the middle.", "recommended": "Center Rug",
                "options": [{"variantName": "Center Rug", "actions": [{"type": "add", "item": "rug", "zone": "centered"}], "tradeoff": "x"}]}

    client.app.state.ctx.gemini.plan = options_only  # type: ignore[method-assign]
    out = _ask(client, bedroom, "add a rug")
    assert out["status"] == "ok" and out["layout"]["name"] == "Center Rug" and "rug" in _ids(out["layout"])


def test_busy_or_rate_limited_model_hands_over_to_the_next(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    from app.config import Settings
    from app.integrations.gemini import GeminiAdapter
    from google.genai import errors

    calls: list[str] = []

    class Resp:
        text = '{"intent": "answer", "reply": "hi"}'

    class Models:
        def generate_content(self, model: str, **kwargs: object) -> Resp:
            calls.append(model)
            if model == "busy":
                raise errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})
            if model == "spent":
                raise errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
            return Resp()

    adapter = GeminiAdapter(Settings.from_env())
    adapter._client = type("C", (), {"models": Models()})()
    adapter.models = ["busy", "spent", "ok"]
    assert asyncio.run(adapter._generate("sys", ["hi"], {"type": "object"})) == {"intent": "answer", "reply": "hi"}
    assert calls == ["busy", "spent", "ok"]  # busy and out-of-quota models hand over straight away


def test_a_plan_with_no_actions_is_sent_back_once_and_never_shows_null(client: TestClient, bedroom: dict) -> None:
    calls: list[list[str] | None] = []

    async def empty_then_good(system_prompt: str, user_text: str, violations: list[str] | None = None, history: list | None = None) -> dict:
        calls.append(violations)
        if len(calls) == 1:
            return {"intent": "fit_item", "reply": "null"}
        return {"intent": "fit_item", "variantName": "Add Rug", "reply": "A rug goes in the middle.", "actions": [{"type": "add", "item": "rug", "zone": "centered"}]}

    client.app.state.ctx.gemini.plan = empty_then_good  # type: ignore[method-assign]
    out = _ask(client, bedroom, "can you add a rug")
    assert out["status"] == "ok" and "rug" in _ids(out["layout"]) and len(calls) == 2 and "no actions" in calls[1][0]

    async def always_empty(*args: object, **kwargs: object) -> dict:
        return {"intent": "fit_item", "reply": "null"}

    client.app.state.ctx.gemini.plan = always_empty  # type: ignore[method-assign]
    out = _ask(client, bedroom, "can you add a rug")
    assert out["layout"] is None and out["reply"] != "null" and "add, move or remove" in out["reply"]
