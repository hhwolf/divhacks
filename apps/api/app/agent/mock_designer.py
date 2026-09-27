"""Stand-in for Gemini when there's no key: reads the room and catalog out of the same system prompt Gemini gets.

It is keyword-based, so it only covers the common requests (add / remove named pieces, clear everything, a new design,
questions). It exists so the app stays usable and testable offline; the real conversation needs GEMINI_API_KEY.
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.prompts import parse_catalog, parse_scene

REMOVE_RE = re.compile(r"\b(remove|delete|take (?:out|away)|get rid of|clear out|throw out|ditch)\b")
ADD_RE = re.compile(r"\b(add|bring|include|insert|put|place|want|need|get me|buy)\b")
ALL_RE = re.compile(r"\b(all|everything|every|whole room)\b")
REDESIGN_RE = re.compile(
    r"\b(redesign|re-design|new design|design (?:plan|idea)|makeover|furnish|restyle|decorate|recommend(?:ation)?s?\b.*\b(?:layout|design|room|study|bedroom|setup)"
    r"|suggest\b.*\b(?:layout|design|plan|setup)|make (?:it|this|my room|the room) (?:feel |look )?(?:more )?\w+|turn (?:it|this|my room) into"
    r"|other furnitures?|more furniture|fill (?:it|the room)|what else)\b"
)
QUESTION_RE = re.compile(r"^(what|how|why|which|where|should|is|are|do|does|can you tell|any (?:tips|ideas))\b|\?$")
# words people use -> catalog ids (only used when the id exists in the prompt's catalog)
SYNONYMS = {
    "couch": "sofa", "loveseat": "sofa", "pot": "plant", "potted plant": "plant", "greenery": "plant", "plants": "plant", "lamp": "floor_lamp",
    "light": "floor_lamp", "bookcase": "bookshelf", "shelf": "bookshelf", "shelves": "bookshelf", "fridge": "mini_fridge", "tv": "tv_stand",
    "carpet": "rug", "mat": "yoga_mat", "bedside table": "nightstand", "closet": "wardrobe", "drawers": "dresser", "chest": "dresser",
    "reading chair": "armchair", "lounge chair": "armchair", "office chair": "chair_desk", "desk chair": "chair_desk", "partition": "divider",
    "box": "moving_box", "dining table": "table", "round table": "table_round", "side table": "side_table", "coffee table": "coffee_table",
}
BASIC = ("desk", "floor_lamp", "plant", "armchair", "bookshelf", "divider")
ZONES = {"desk": "window wall, beside window", "floor_lamp": "corner, near window", "plant": "corner, near window", "armchair": "corner, near window",
         "bookshelf": "", "sofa": "opposite the door", "rug": "centered", "tv_stand": "", "divider": "centered"}


def _terms(catalog: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(phrase, catalog id), longest phrase first so 'desk chair' wins over 'desk'."""
    ids = {str(c["id"]) for c in catalog}
    pairs = {(str(c["id"]).replace("_", " "), str(c["id"])) for c in catalog} | {(str(c["name"]).lower(), str(c["id"])) for c in catalog}
    pairs |= {(word, cid) for word, cid in SYNONYMS.items() if cid in ids}
    return sorted(pairs, key=lambda p: -len(p[0]))


def _mentions(text: str, terms: list[tuple[str, str]]) -> list[str]:
    found, rest = [], f" {text} "
    for phrase, cid in terms:
        pat = re.compile(rf"\b{re.escape(phrase)}(?:e?s)?\b")
        if pat.search(rest):
            if cid not in found:
                found.append(cid)
            rest = pat.sub(" ", rest)
    return found


def _say_back(system: str) -> str:
    m = re.search(r"<scene-facts>\n- (.+)", system)
    return m.group(1) if m else ""


def _answer(reply: str, summary: str) -> dict[str, Any]:
    return {"intent": "answer", "reply": reply, "roomSummary": summary}


def plan(system: str, text: str, retry: bool = False) -> dict[str, Any] | None:
    """A plan for the requests this stand-in understands, or None to fall back to the canned fixtures."""
    if "<scene " not in system or "<catalog " not in system:
        return None
    t = text.lower().strip()
    scene, catalog = parse_scene(system), parse_catalog(system)
    summary = _say_back(system)
    terms = _terms(catalog)
    placed = {iid: f for iid, f in scene["furniture"].items()}  # type: ignore[union-attr]
    locked = {p["furnitureId"] for p in scene["base_items"] if p["locked"]}  # type: ignore[union-attr]
    names = {cid: str(c["name"]).lower() for c in catalog for cid in [str(c["id"])]}

    if REMOVE_RE.search(t):
        if ALL_RE.search(t):
            targets = [iid for iid in placed if iid not in locked]
        else:
            wanted = _mentions(t, terms)
            targets = [iid for iid, f in placed.items() if f["catalogId"] in wanted or any(w.replace("_", " ") in f["name"].lower() for w in wanted)]
        kept = [placed[i]["name"].lower() for i in placed if i in locked and (ALL_RE.search(t) or i in targets)]
        targets = [i for i in targets if i not in locked]
        if not targets:
            asked = _mentions(t, terms)
            what = "anything you can remove" if ALL_RE.search(t) else f"a {' or '.join(names.get(c, c) for c in asked)}" if asked else "that piece"
            return _answer(f"I don't see {what} in this layout" + (f"; the {', '.join(kept)} is locked" if kept else "") + ". Which piece should go?", summary)
        label = "Cleared room" if ALL_RE.search(t) else f"Without the {placed[targets[0]]['name'].lower()}"[:30]
        counts: dict[str, int] = {}
        for i in targets:
            counts[placed[i]["name"].lower()] = counts.get(placed[i]["name"].lower(), 0) + 1
        gone = ", ".join(n if k == 1 else f"{k} {n}s" for n, k in counts.items())
        note = f" I left the {', '.join(kept)} because it's locked." if kept else ""
        return {"intent": "fit_item", "variantName": label, "actions": [{"type": "remove", "item": i} for i in targets], "roomSummary": summary,
                "options": [{"variantName": label, "actions": [{"type": "remove", "item": i} for i in targets],
                             "explanation": f"Taking out the {gone} frees up floor.", "tradeoff": "You lose what those pieces did for the room."}],
                "reply": f"Done: I took out the {gone} in a new layout.{note}"}

    if REDESIGN_RE.search(t):
        return {"intent": "redesign", "theme": text.strip()[:120], "variantName": "New design", "roomSummary": summary,
                "reply": "Here's a new design to start from, built around what can't move."}

    wanted = _mentions(t, terms)
    if len(wanted) == 1 and wanted[0] in BASIC and ADD_RE.search(t) and not retry:
        from app.integrations.gemini import (
            _basic_addition_plan,  # the canned single-piece plans already place these well
        )

        basic = _basic_addition_plan(f"add {wanted[0].replace('_', ' ')}")
        if basic:
            return {**basic, "roomSummary": summary}
    if wanted and (ADD_RE.search(t) or len(t.split()) <= 3):
        # a retry means the first spot failed the fit check: let the solver try every wall
        actions = [{"type": "add", "item": cid, "zone": "" if retry else ZONES.get(cid, "")} for cid in wanted[:4]]
        # SKILL.md options-output: 1 to 3 plain words ("Add sofa", "Lamp and Rug")
        label = f"Add {names.get(wanted[0], wanted[0])}"[:30] if len(wanted) == 1 else " and ".join(names.get(c, c).split()[-1].title() for c in wanted[:2])
        pieces = " and ".join(names.get(c, c) for c in wanted[:4])
        return {"intent": "fit_item", "variantName": label, "actions": actions, "roomSummary": summary,
                "options": [{"variantName": label, "actions": actions, "explanation": f"The {pieces} {'go' if len(wanted) > 1 else 'goes'} "
                             "where there's room without blocking the door or the window."}],
                "reply": f"I added the {pieces} where {'they fit' if len(wanted) > 1 else 'it fits'} best."}

    if QUESTION_RE.search(t) and not any(w in t for w in ("yoga", "desk", "fit")):
        return _answer(f"{summary} I can add pieces, move or remove what's there, clear space for something like yoga, or draft a whole new "
                       "design. Try 'add a sofa', 'remove the plant' or 'make it a cozy study'.", summary)
    return None
