"""Gemini adapter. Mock mode returns the canned plans in fixtures/plans; live mode uses google-genai structured output."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.catalog import FIXTURES_DIR
from app.config import REPO_ROOT, Settings

PLAN_SCHEMA_PATH = REPO_ROOT / "packages" / "contracts" / "schemas" / "plan.schema.json"
PLAN_SCHEMA: dict[str, Any] = json.loads(PLAN_SCHEMA_PATH.read_text())
LISTING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "category", "dims", "estimated"],
    "properties": {
        "name": {"type": "string"},
        "category": {"type": "string", "enum": ["bed", "desk", "seating", "storage", "table", "decor", "imported"]},
        "dims": {"type": "object", "required": ["w", "d", "h"], "properties": {"w": {"type": "number"}, "d": {"type": "number"}, "h": {"type": "number"}}},
        "price": {"type": "number", "nullable": True},
        "color": {"type": "string", "nullable": True},
        "estimated": {"type": "boolean"},
    },
}
MOCK_DESK: dict[str, Any] = {"name": "Desk", "category": "desk", "dims": {"w": 1.2, "d": 0.6, "h": 0.75}, "price": 80, "color": "oak", "estimated": False}
MOCK_CHAIR: dict[str, Any] = {"name": "Chair", "category": "seating", "dims": {"w": 0.5, "d": 0.5, "h": 0.9}, "price": None, "color": None, "estimated": True}
RETRY_ALTERNATIVE = "east wall, centered"
log = logging.getLogger(__name__)
_UNSUPPORTED_KEYS = {"$schema", "$id", "additionalProperties", "default"}
_EXTERNAL_ITEM_RE = re.compile(r"\b(https?://|facebook|marketplace|ikea|amazon|listing|photo|picture|image)\b")
_ADD_VERB_RE = re.compile(r"\b(add|bring|include|insert|put|place|recommend|suggest|need|want)\b")
_BASIC_ADDITIONS: tuple[tuple[str, tuple[str, ...], str, str, str, str | None], ...] = (
    ("desk", ("desk", "table to work", "work table"), "Add desk", "window wall, beside window", "I recommend adding a desk beside the window while keeping the bed where it is.", "window"),
    ("floor_lamp", ("floor lamp", "lamp", "light", "reading light"), "Add floor lamp", "corner, near window", "I recommend adding a floor lamp in the window-side corner so it supports a reading spot without blocking the door.", None),
    ("plant", ("plant", "potted plant"), "Add plant", "corner, near window", "I recommend adding a plant in the window-side corner where it gets light and stays out of the path.", None),
    ("armchair", ("armchair", "reading chair", "lounge chair"), "Add reading chair", "corner, near window", "I recommend adding a reading chair near the window while keeping the main walkway clear.", "window"),
    ("bookshelf", ("bookshelf", "bookcase", "shelf"), "Add bookshelf", "west wall, centered", "I recommend adding a bookshelf on an open wall so storage improves without crowding the bed.", None),
    ("divider", ("divider", "room divider", "partition"), "Add divider", "centered", "I recommend adding a divider centered off the open area so it defines the room without blocking the door.", None),
)


def strip_schema(schema: Any, root: Any = None) -> Any:
    """Drop JSON Schema keywords Gemini's response_schema rejects and inline local '#/...' refs, which it doesn't follow."""
    root = schema if root is None else root
    if isinstance(schema, dict):
        if isinstance(ref := schema.get("$ref"), str) and ref.startswith("#/"):
            target = root
            for key in ref[2:].split("/"):
                target = target[key]
            return strip_schema(target, root)
        return {k: strip_schema(v, root) for k, v in schema.items() if k not in _UNSUPPORTED_KEYS}
    if isinstance(schema, list):
        return [strip_schema(v, root) for v in schema]
    return schema


def _plan_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "plans" / f"{name}.json").read_text())


def _basic_addition_plan(text: str) -> dict[str, Any] | None:
    t = text.lower()
    if not (_ADD_VERB_RE.search(t) or "desk" in t or "reading corner" in t):
        return None
    for item, terms, name, zone, reply, adjacent in _BASIC_ADDITIONS:
        if any(term in t for term in terms):
            plan: dict[str, Any] = {
                "intent": "fit_item",
                "variantName": name,
                "actions": [{"type": "add", "item": item, "zone": zone}],
                "reply": reply,
            }
            if adjacent:
                plan["constraints"] = [{"type": "adjacent", "item": item, "feature": adjacent}]
            return plan
    if "reading corner" in t:
        return {
            "intent": "fit_item",
            "variantName": "Add reading chair",
            "constraints": [{"type": "adjacent", "item": "armchair", "feature": "window"}],
            "actions": [{"type": "add", "item": "armchair", "zone": "corner, near window"}],
            "reply": "I recommend adding a reading chair near the window while keeping the main walkway clear.",
        }
    return None


def mock_plan_for(text: str, retry: bool) -> dict[str, Any]:
    t = text.lower()
    basic = None if _EXTERNAL_ITEM_RE.search(t) else _basic_addition_plan(text)
    if basic:
        plan = basic
    elif any(w in t for w in ("desk", "fit", "window")):
        plan = _plan_fixture("marketplace-desk")
    elif any(w in t for w in ("yoga", "space")):
        plan = _plan_fixture("yoga-corner")
    else:
        return _plan_fixture("clarify")
    if retry:
        for action in [*plan.get("actions", []), *(a for o in plan.get("options", []) for a in o["actions"])]:
            if action.get("zone"):
                action["zone"] = f"{action['zone']} or {RETRY_ALTERNATIVE}"
    return plan


# Busy (503/500/504), out of quota (429; the free tier allows 20 requests a day per model) or retired/unknown (404):
# go straight to the next model. Retrying the same one was almost always busy again, and a 429 retry only burns quota.
NEXT_MODEL = (404, 429, 500, 503, 504)
CALL_TIMEOUT_MS = 30_000
# The designer is a chat: low reasoning answers in a few seconds instead of 10+ and still plans well.
THINKING_LEVEL = "LOW"


class GeminiAdapter:
    def __init__(self, settings: Settings) -> None:
        self.live = settings.gemini_live
        self.model = settings.gemini_model
        self.models = list(dict.fromkeys([settings.gemini_model, *settings.gemini_fallback_models]))
        self._client: Any = None
        if self.live:
            from google import genai
            from google.genai import types

            # a hung call must not hold the request: time out and move on to the next model
            self._client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=CALL_TIMEOUT_MS))

    async def _generate(self, system: str, contents: list[Any], schema: dict[str, Any]) -> dict[str, Any]:
        import httpx
        from google.genai import errors, types

        config = types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", response_schema=strip_schema(schema),
                                             thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL))
        last: Exception | None = None
        for model in self.models:
            try:
                try:
                    resp = await asyncio.to_thread(self._client.models.generate_content, model=model, contents=contents, config=config)
                except errors.ClientError as exc:
                    if exc.code != 400 or "thinking" not in str(exc).lower():
                        raise
                    # a model that doesn't take a thinking level: ask it once more without one
                    plain = config.model_copy(update={"thinking_config": None})
                    resp = await asyncio.to_thread(self._client.models.generate_content, model=model, contents=contents, config=plain)
            except errors.APIError as exc:
                last = exc
                if exc.code not in NEXT_MODEL:
                    raise
                log.warning("gemini %s: %s, trying the next model", model, exc.code)
                continue
            except httpx.TransportError as exc:  # timeout or connection reset
                last = exc
                log.warning("gemini %s: %s, trying the next model", model, type(exc).__name__)
                continue
            if model != self.model:
                log.warning("gemini: answered by fallback model %s", model)
            return json.loads(resp.text or "{}")
        assert last is not None
        raise last

    async def plan(self, system_prompt: str, user_text: str, violations: list[str] | None = None,
                   history: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        """Return a raw plan dict (schema validation happens in the pipeline). `violations` marks the single retry call.

        `history` is the room's earlier conversation as (person's message, designer's reply as plan JSON), oldest first.
        """
        if not self.live:
            from app.agent import mock_designer

            if (designed := mock_designer.plan(system_prompt, user_text, retry=violations is not None)) is not None:
                return designed
            return mock_plan_for(user_text, retry=violations is not None)
        from google.genai import types

        contents: list[Any] = []
        for said, answered in history or []:
            contents += [types.Content(role="user", parts=[types.Part.from_text(text=said)]),
                         types.Content(role="model", parts=[types.Part.from_text(text=answered)])]
        text = user_text
        if violations:
            text += "\n\nYour previous plan for this message was rejected by the fit check:\n- " + "\n- ".join(violations) + "\nPropose a different arrangement."
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
        return await self._generate(system_prompt, contents, PLAN_SCHEMA)

    async def furnish(self, system_prompt: str, theme: str, photos: list[tuple[bytes, str]] | None = None) -> dict[str, Any]:
        """Raw furnishing plan for a theme and optional inspiration photos (live only; app.furnish owns the mock kits and validation)."""
        from google.genai import types

        from app.furnish import FURNISH_SCHEMA

        parts: list[Any] = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in photos or []]
        return await self._generate(system_prompt, [*parts, f"Theme: {theme}"], FURNISH_SCHEMA)

    async def extract_listing(self, text: str, html_meta: dict[str, Any]) -> dict[str, Any]:
        if not self.live:
            return dict(MOCK_DESK)
        prompt = (
            "Extract the furniture item from this marketplace listing. Dimensions in meters (w = width along the front, d = depth, h = height). "
            "Set estimated=true when dimensions are inferred rather than stated.\n\nMETA:\n" + json.dumps(html_meta) + "\n\nTEXT:\n" + text[:6000]
        )
        return await self._generate("You extract structured furniture listings.", [prompt], LISTING_SCHEMA)

    async def estimate_from_photo(self, data: bytes, mime: str) -> dict[str, Any]:
        if not self.live:
            return dict(MOCK_CHAIR)
        from google.genai import types

        part = types.Part.from_bytes(data=data, mime_type=mime)
        return await self._generate(
            "You identify a single furniture item in a photo and estimate its real-world dimensions in meters. Always set estimated=true.",
            [part, "Identify the furniture item and estimate w, d, h in meters."],
            LISTING_SCHEMA,
        )
