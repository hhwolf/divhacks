"""Gemini adapter. Mock mode returns the canned plans in fixtures/plans; live mode uses google-genai structured output."""

from __future__ import annotations

import asyncio
import json
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
_UNSUPPORTED_KEYS = {"$schema", "$id", "additionalProperties", "default"}


def strip_schema(schema: Any) -> Any:
    """Drop JSON Schema keywords Gemini's response_schema rejects."""
    if isinstance(schema, dict):
        return {k: strip_schema(v) for k, v in schema.items() if k not in _UNSUPPORTED_KEYS}
    if isinstance(schema, list):
        return [strip_schema(v) for v in schema]
    return schema


def _plan_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "plans" / f"{name}.json").read_text())


def mock_plan_for(text: str, retry: bool) -> dict[str, Any]:
    t = text.lower()
    if any(w in t for w in ("desk", "fit", "window")):
        plan = _plan_fixture("marketplace-desk")
    elif any(w in t for w in ("yoga", "space")):
        plan = _plan_fixture("yoga-corner")
    else:
        return _plan_fixture("clarify")
    if retry:
        for action in plan.get("actions", []):
            if action.get("zone"):
                action["zone"] = f"{action['zone']} or {RETRY_ALTERNATIVE}"
    return plan


class GeminiAdapter:
    def __init__(self, settings: Settings) -> None:
        self.live = settings.gemini_live
        self.model = settings.gemini_model
        self._client: Any = None
        if self.live:
            from google import genai

            self._client = genai.Client(api_key=settings.gemini_api_key)

    async def _generate(self, system: str, contents: list[Any], schema: dict[str, Any]) -> dict[str, Any]:
        from google.genai import types

        config = types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", response_schema=strip_schema(schema))
        resp = await asyncio.to_thread(self._client.models.generate_content, model=self.model, contents=contents, config=config)
        return json.loads(resp.text or "{}")

    async def plan(self, system_prompt: str, user_text: str, violations: list[str] | None = None) -> dict[str, Any]:
        """Return a raw plan dict (schema validation happens in the pipeline). `violations` marks the single retry call."""
        if not self.live:
            return mock_plan_for(user_text, retry=violations is not None)
        contents: list[Any] = [user_text]
        if violations:
            contents.append("The previous plan was rejected by the fit validator:\n- " + "\n- ".join(violations) + "\nPropose a different placement.")
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
