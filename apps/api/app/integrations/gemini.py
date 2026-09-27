"""Gemini adapter: the agent's orchestrator. Stage 1 `plan` picks the intent (and so the tool) and extracts its inputs, with the
Pydantic `GeminiPlan` as the structured-output schema (no coordinate fields); Stage 4 `narrate` words the result as the Interior
Designer. Mock mode returns the canned plans in fixtures/plans and leaves the wording to the deterministic draft."""

from __future__ import annotations

import json
import re
from typing import Any

from app.catalog import FIXTURES_DIR
from app.config import GEMINI_MODEL, Settings
from app.models import GeminiPlan, Narration

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


def _plan_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "plans" / f"{name}.json").read_text())


_ISSUES = (("rat", "rats"), ("rodent", "rodents"), ("bug", "bugs"), ("roach", "bugs"), ("leak", "water leak"), ("faucet", "bad faucet"),
           ("plumbing", "plumbing problem"), ("floor", "floor damage"), ("voucher", "voucher / source of income concern"))


def _money(text: str) -> float | None:
    m = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text)
    return float(m.group(1).replace(",", "")) if m else None


def _zip(text: str) -> str | None:
    m = re.search(r"\b(10[0-2][0-9]{2}|11[0-6][0-9]{2})\b", text)
    return m.group(1) if m else None


def mock_plan_for(text: str, retry: bool) -> dict[str, Any]:
    """Deterministic Stage 1 stand-in for every intent. The retry relaxes `adjacent` constraints, like a model told its first spot failed."""
    t = text.lower()
    if "deposit" in t or "application fee" in t or "app fee" in t:
        purpose = "deposit" if "deposit" in t else "application_fee"
        return {"intent": "payment_check", "payment": {"purpose": purpose, "amount": _money(text)}, "constraints": [],
                "explanation": "Checking that payment against NYC's limits.", "question": None if _money(text) is not None else "How much are they asking you to pay?"}
    if any(k in t for k in ("rent", "fair", "overpriced", "price check")):
        issues = list(dict.fromkeys(label for word, label in _ISSUES if word in t))
        return {"intent": "rent_check", "rent": {"askingRent": _money(text), "zip": _zip(text), "issues": issues, "occupancyType": "private_room"},
                "constraints": [], "explanation": "Checking your rent against the room you scanned."}
    if any(w in t for w in ("blocking", "block the", "keep clear", "clear of")):
        plan = _plan_fixture("keep-window-clear")
    elif any(w in t for w in ("which layout", "better for", "best layout", "rank")):
        plan = _plan_fixture("rank-variants")
    elif any(w in t for w in ("desk", "fit", "window")):
        plan = _plan_fixture("marketplace-desk")
    elif any(w in t for w in ("yoga", "space")):
        plan = _plan_fixture("yoga-corner")
    else:
        return _plan_fixture("clarify")
    if retry:
        plan["constraints"] = [c for c in plan.get("constraints", []) if c.get("type") != "adjacent"]
    return plan


class GeminiAdapter:
    def __init__(self, settings: Settings) -> None:
        self.live = settings.gemini_live
        self.model = GEMINI_MODEL
        self._client: Any = None
        if self.live:
            from google import genai

            self._client = genai.Client(api_key=Settings.reveal(settings.gemini_api_key))

    async def _generate(self, system: str, contents: list[Any], schema: Any) -> dict[str, Any]:
        from google.genai import types

        config = types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", response_schema=schema)
        resp = await self._client.aio.models.generate_content(model=self.model, contents=contents, config=config)
        return json.loads(resp.text or "{}")

    async def plan(self, system_prompt: str, user_text: str, violations: list[str] | None = None) -> dict[str, Any]:
        """Stage 1: intent + constraints as a raw dict (the pipeline validates it). `violations` marks the single retry call."""
        if not self.live:
            return mock_plan_for(user_text, retry=violations is not None)
        contents: list[Any] = [user_text]
        if violations:
            contents.append(
                "The placement solver could not satisfy your previous plan:\n- " + "\n- ".join(violations)
                + "\nReturn a revised plan (relax or change a constraint). Still no coordinates."
            )
        return await self._generate(system_prompt, contents, GeminiPlan)

    async def narrate(self, designer_prompt: str, facts: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any] | None:
        """Stage 4: the Interior Designer words the result. Facts are ground truth; the draft shows the expected shape and tone.
        None in mock mode (the deterministic draft is used as is)."""
        if not self.live:
            return None
        prompt = (
            "Word this result for the person, in your voice. Use ONLY these facts; never add a position, size or claim that isn't in them. "
            "Keep option indexes. variantName: 1 to 3 plain words. explanation: 1-2 sentences on why it's good for them. tradeoff: 1 honest "
            "sentence. reply: one sentence for iMessage, the answer first. You may change recommended_index if another option is clearly "
            "better for what they asked.\n\nFACTS:\n" + json.dumps(facts) + "\n\nDRAFT:\n" + json.dumps(draft)
        )
        return await self._generate(designer_prompt, [prompt], Narration)

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

