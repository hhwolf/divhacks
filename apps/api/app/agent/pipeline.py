"""Backboard context -> Gemini plan -> solver -> (one retry) -> forked variant -> reply -> memory write -> agent_requests log."""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.agent import review, scene
from app.agent.prompts import build_system_prompt, room_purpose
from app.catalog import all_furniture
from app.deps import AppContext
from app.integrations.gemini import PLAN_SCHEMA
from app.models import AgentPlan, AgentRequestLog, Channel, FurnitureItem, Layout, PlanOption, Room, ValidationResult, Violation
from app.solver.placement import Solver, SolveResult, resolve_catalog, resolve_instance
from app.planning_models import PlacementPlan
from app.solver.advanced_placement import Solver as AdvancedSolver
from app.solver.validate import validate_layout
from app.solver.units import format_length_imperial
from app.solver.zones import wall_label

Status = Literal["ok", "rejected", "clarify", "error"]
_plan_validator = Draft202012Validator(PLAN_SCHEMA)


@dataclass
class PipelineResult:
    status: Status
    reply: str
    request_id: str
    plan: AgentPlan | None = None
    layout: dict[str, Any] | None = None
    links: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)
    recommended: str | None = None
    room_summary: str | None = None


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_plan(raw: dict[str, Any]) -> AgentPlan | str:
    """Schema-validate a raw Gemini response; returns the plan or the first error message."""
    err = next(iter(_plan_validator.iter_errors(raw)), None)
    if err is not None:
        return f"plan JSON invalid: {err.message}"
    try:
        return AgentPlan.model_validate(raw)
    except ValidationError as exc:
        return f"plan JSON invalid: {exc.errors()[0]['msg']}"


def dedupe_name(name: str, taken: set[str]) -> str:
    candidate, n = name, 2
    while candidate in taken:
        candidate = f"{name} ({n})"
        n += 1
    return candidate


def compose_reply(plan: AgentPlan, result: SolveResult) -> str:
    reply = plan.reply.strip()
    if plan.intent == "fit_item" and result.gap_m is not None and result.gap_m >= 0.025:
        gap = format_length_imperial(result.gap_m)
        if gap not in reply and "spare" not in reply.lower():
            reply = f"{reply.rstrip('.')} ({gap} to spare)."
    for note in result.notes:
        reply = f"{reply.rstrip('.')}; {note}."
    return reply


def rejection_reply(sk_room: Room, result: SolveResult, alternative: str | None, piece: str | None = None) -> str:
    """Say what doesn't fit and by how much; suggest another wall only when the solver found a spot there (SKILL.md step 4)."""
    ask = f"want me to try {alternative}?" if alternative else "it doesn't fit along any other wall either. Want me to move something to make room?"
    if result.shortfall_m and result.failed_wall is not None:
        label = wall_label(sk_room.skeleton, result.failed_wall)
        who = f"The {piece} is" if piece else "It's"
        return f"{who} {round(result.shortfall_m * 100)} cm ({format_length_imperial(result.shortfall_m)}) too wide for the {label}; {ask}"
    reason = result.violations[0].message if result.violations else "it doesn't pass the fit check"
    return f"I couldn't make that work: {reason.lower()}; {ask}"


def tested_alternative(solver: Solver, room: Room, plan: AgentPlan, failed_wall: int | None) -> str | None:
    """The first other wall where the same placement actually solves, as 'the north wall', or None."""
    names = scene.wall_names(room.skeleton)
    for i, name in enumerate(names):
        if i == failed_wall or not name.endswith(" wall") or "-facing" in name:
            continue
        actions = [a.model_copy(update={"zone": name}) if a.type in ("add", "move") else a for a in plan.actions]
        trial = plan.model_copy(update={"actions": actions, "constraints": [c for c in plan.constraints if c.type != "adjacent"], "options": []})
        if solver.solve(trial).ok:
            return f"the {name}" + (" by the door" if any(d.wall == i for d in room.skeleton.doors) else "")
    return None


def _advanced_fallback(
    plan: AgentPlan, room: Room, base: Layout, catalog: dict[str, FurnitureItem],
    furniture_id: str | None, memories: list[str],
) -> tuple[SolveResult, FurnitureItem | None] | None:
    """Search open-floor candidates only when the old plan can be mapped losslessly.

    Any zone phrase is left to the primary solver: named walls, corners, centering,
    and ordered alternatives have semantics this internal plan does not represent.
    """
    requested_import = catalog.get(furniture_id) if furniture_id else None
    if requested_import and requested_import.source in ("photo", "link") and not requested_import.dimensionsConfirmed:
        return None
    if plan.intent != "fit_item" or len(plan.actions) != 1:
        return None
    action = plan.actions[0]
    if action.type not in ("add", "move") or action.rotation is not None or (action.zone or "").strip():
        return None
    target = resolve_instance(action.item, base.items, catalog) if action.type == "move" else None
    furniture = catalog.get(target.furnitureId) if target else resolve_catalog(action.item, catalog, furniture_id)
    if not furniture or (action.type == "move" and (not target or target.locked)):
        return None
    if furniture.source in ("photo", "link") and not furniture.dimensionsConfirmed:
        return None
    constraints = []
    target_refs = {action.item, furniture.id, target.id if target else furniture.id}
    for constraint in plan.constraints:
        if constraint.type == "lock":
            if not constraint.item or not resolve_instance(constraint.item, base.items, catalog):
                return None
            constraints.append(constraint)
        elif constraint.type in ("adjacent", "keep_clear"):
            allowed = ("window", "door", "outlet") if constraint.type == "adjacent" else ("window", "door")
            if constraint.feature not in allowed or (constraint.item is not None and constraint.item not in target_refs):
                return None
            features = {"window": room.skeleton.windows, "door": room.skeleton.doors, "outlet": room.skeleton.outlets}
            if not features[constraint.feature]:
                return None
            constraints.append(constraint.model_copy(update={"item": target.id if target else furniture.id}))
        else:
            # Required clear zones and their optionality are owned by the primary
            # planner; do not silently discard one when the second solver can't fit it.
            return None
    extra_locks = []
    for memory in memories:
        # Preserve directional preferences whose priority cannot be represented here.
        if re.search(r"\b(wall|corner|window|door|outlet|north|south|east|west)\b", memory, re.I):
            return None
        match = re.search(r"\b(?:never|don't|do not)\s+(?:move|touch|shift)\s+(?:the\s+|my\s+)?(.+?)(?:[.,;!?]|$)", memory, re.I)
        if match:
            locked = resolve_instance(match.group(1).strip(), base.items, catalog)
            if not locked:
                return None
            extra_locks.append(locked.id)
    planner = AdvancedSolver(room.skeleton, catalog, base.items,
                             furniture.id if action.type == "add" else None, extra_locks=extra_locks)
    internal = PlacementPlan(intent="fit_item", item={"type": target.id if target else furniture.id},
                             operation=action.type, constraints=constraints)
    candidate = planner.solve(internal)
    if not candidate.ok or candidate.noop:
        return None
    zones = [*base.zones, *(zone for zone in candidate.zones if zone not in base.zones)]
    result_catalog = {**catalog, **({candidate.new_furniture.id: candidate.new_furniture} if candidate.new_furniture else {})}
    validation = validate_layout(room.skeleton, result_catalog, candidate.items, zones, base.items)
    previous = validate_layout(room.skeleton, catalog, base.items, base.zones, base.items)
    previous_clear = {v.message for v in previous.violations if v.rule == "clear_zone"}
    if validation.blocked or validation.metrics.conflicts or any(
        v.rule == "clear_zone" and v.message not in previous_clear for v in validation.violations
    ):
        return None
    return SolveResult(True, candidate.items, zones, [], validation,
                       gap_m=candidate.gap_m, notes=candidate.notes), candidate.new_furniture


async def run(
    ctx: AppContext,
    *,
    request_text: str,
    user_id: str,
    room_id: str,
    base_layout_id: str,
    furniture_id: str | None = None,
    channel: Channel = "app",
) -> PipelineResult:
    request_id = uuid.uuid4().hex[:12]
    room_doc = await ctx.repo.get("rooms", room_id)
    base_doc = await ctx.repo.get("layouts", base_layout_id)
    if room_doc is None or base_doc is None:
        return await _finish(ctx, request_id, user_id, room_id, base_layout_id, channel, request_text, PipelineResult("error", "I couldn't find that room or layout.", request_id))
    room, base = Room.model_validate(room_doc), Layout.model_validate(base_doc)
    catalog = await all_furniture(ctx.repo)
    memories = await ctx.backboard.get_context(user_id)
    imported = catalog.get(furniture_id) if furniture_id else None
    if imported and imported.source in ("photo", "link") and not imported.dimensionsConfirmed:
        return await _finish(ctx, request_id, user_id, room_id, base_layout_id, channel, request_text, PipelineResult("clarify", "Imported the item. Open Imported furniture in the editor and confirm its dimensions before I recommend a fit.", request_id, links=[f"{ctx.settings.public_web_url}/layout/{base.id}"]))
    purpose = room_purpose(room_doc)
    system = build_system_prompt(room.skeleton, base, catalog, memories, imported, purpose, request_text)
    solver = Solver(room.skeleton, catalog, base.items, furniture_id)
    before = validate_layout(room.skeleton, catalog, base.items, base.zones)
    review_before = review.skill_validate(room.skeleton, catalog, base.items, base.items)

    history = await conversation(ctx, user_id, room_id)
    try:
        plan_or_err = parse_plan(await ctx.gemini.plan(system, request_text, history=history))
    except Exception as exc:  # noqa: BLE001 - quota, bad key, retired model, network: keep the app working and say so
        log.exception("agent: Gemini plan call failed; using the offline planner")
        from app.agent import mock_designer
        from app.integrations.gemini import mock_plan_for

        OFFLINE_NOTE.set(gemini_unavailable(exc))
        plan_or_err = parse_plan(mock_designer.plan(system, request_text) or mock_plan_for(request_text, retry=False))
    plan: AgentPlan | None = None
    outcomes: list[Outcome] = []
    for attempt in range(2):
        if isinstance(plan_or_err, AgentPlan):
            plan = plan_or_err
            if plan.intent == "answer" and _readable(plan.reply):
                out = PipelineResult("ok", plan.reply, request_id, plan=plan, room_summary=_summary(plan, room, purpose))
                return await _finish(ctx, request_id, user_id, room_id, base_layout_id, channel, request_text, out)
            if plan.intent == "redesign":
                out = await _redesign(ctx, plan, request_id, room_doc, base, catalog, purpose, before, review_before)
                if plan.preferencesLearned:
                    await ctx.backboard.add_memories(user_id, plan.preferencesLearned)
                return await _finish(ctx, request_id, user_id, room_id, base_layout_id, channel, request_text, out)
            empty = plan.intent != "clarify" and not (plan.actions or any(o.actions for o in plan.options))
            if empty and attempt == 0:
                # e.g. intent fit_item with no actions: ask once more rather than showing a non-answer
                feedback = [f"Your plan had intent {plan.intent} but no actions. Give the actions (in options and at the top level), "
                            "or use intent answer or clarify with a reply the person can read."]
                plan_or_err = await _replan(ctx, system, request_text, feedback, history, plan_or_err)
                continue
            if plan.intent == "clarify" or empty:
                reply = _readable(plan.clarifyingQuestion) or _readable(plan.reply) or (
                    "I'm not sure what to change yet. Tell me a piece to add, move or remove, or ask for a new design for the room.")
                return await _finish(ctx, request_id, user_id, room_id, base_layout_id, channel, request_text, PipelineResult("clarify", reply, request_id, plan=plan))
            outcomes = [_solve_option(solver, opt, room, base, catalog, furniture_id, memories) for opt in plan_options(plan)]
            if any(o.accepted for o in outcomes):
                break
            feedback = [p for o in outcomes for p in o.problems]
        else:
            feedback = [plan_or_err]
        if attempt == 0:
            plan_or_err = await _replan(ctx, system, request_text, feedback, history, plan_or_err)

    accepted = _distinct([o for o in outcomes if o.accepted])
    if plan is None or not accepted:
        first = outcomes[0] if outcomes else None
        unplaceable = bool(first and first.result and _not_a_fit_problem(first.result))
        alternative = None if unplaceable or not first else tested_alternative(solver, room, first.plan, first.result.failed_wall if first.result else None)
        if unplaceable and first and first.result:
            reason = first.result.violations[0].message
            hint = " Tell me which piece you mean, or pick one from the catalog." if not reason.endswith("was moved") else " Unlock it in the editor first if you really want it to change."
            reply = f"I couldn't do that: {reason[0].lower() + reason[1:]}.{hint}"
        elif first and first.result and not first.result.ok:
            reply = rejection_reply(room, first.result, alternative, _failed_piece(first, base, catalog))
        elif first and first.problems:
            ask = f"Want me to try {alternative}?" if alternative else "Want me to move something to make room?"
            reply = f"I couldn't make that work: {review.imperial(first.problems[0]).rstrip('.').lower()}. {ask}"
        else:
            reply = f"I couldn't read a valid plan ({plan_or_err}). Could you rephrase?"
        violations = first.result.violations if first and first.result else []
        return await _finish(
            ctx, request_id, user_id, room_id, base_layout_id, channel, request_text,
            PipelineResult("rejected", reply, request_id, plan=plan, violations=violations, room_summary=_summary(plan, room, purpose)),
        )

    taken = {l["name"] for l in await ctx.repo.list_by_room("layouts", room_id)}
    saved: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    for n, o in enumerate(accepted):
        assert o.result and o.result.validation is not None
        name = dedupe_name((o.name or plan.variantName or "Variant").strip()[:60], taken)
        taken.add(name)
        layout = Layout(
            id=uuid.uuid4().hex[:12], roomId=room_id, name=name, isCurrent=False, parentLayoutId=base.id, items=o.result.items,
            zones=o.result.zones, metrics=o.result.validation.metrics, createdBy="agent", requestText=request_text, style=base.style,
            createdAt=now_iso(), updatedAt=now_iso(),
        )
        if o.furniture is not None:
            await ctx.repo.insert("furniture", {**o.furniture.model_dump(), "userId": user_id, "createdAt": now_iso()})
        await ctx.repo.insert("layouts", layout.model_dump())
        saved.append(layout.model_dump())
        options.append(_option_out(o, layout, n == 0, base, before, review_before))
    links = [f"roomplanner://layout/{saved[0]['id']}", f"{ctx.settings.public_web_url}/layout/{saved[0]['id']}"]
    if plan.preferencesLearned:
        await ctx.backboard.add_memories(user_id, plan.preferencesLearned)
    reply = compose_reply(plan, accepted[0].result)  # type: ignore[arg-type]
    if not outcomes[0].accepted:
        reply = f"My first idea didn't pass the fit check, so I went with {options[0]['variantName']}. {accepted[0].explanation or ''}".strip()
    if len(options) > 1:
        reply = f"{reply.rstrip()} I saved {len(options)} layouts; {options[0]['variantName']} is my pick."
    out = PipelineResult("ok", reply, request_id, plan=plan, layout=saved[0], links=links, options=options,
                         recommended=options[0]["variantName"], room_summary=_summary(plan, room, purpose))
    return await _finish(ctx, request_id, user_id, room_id, base_layout_id, channel, request_text, out)


HISTORY_TURNS = 6
log = logging.getLogger(__name__)


# set when Gemini couldn't be reached and the offline planner answered; _finish tells the person
OFFLINE_NOTE: ContextVar[str | None] = ContextVar("OFFLINE_NOTE", default=None)


def gemini_unavailable(exc: Exception) -> str:
    """Why Gemini didn't answer, in plain words; the details go to the server log, never to the person."""
    text = str(exc)
    if "API key" in text or "PERMISSION_DENIED" in text or "401" in text or "403" in text:
        why = "the Gemini API key was refused"
    elif "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower():
        why = "Gemini's rate limit was hit"
    elif "404" in text or "NOT_FOUND" in text:
        why = "the configured Gemini model isn't available (check GEMINI_MODEL)"
    else:
        why = "Gemini didn't answer"
    return f"{why[0].upper() + why[1:]}, so this is my quick offline answer; ask again in a minute for the full designer"


async def conversation(ctx: AppContext, user_id: str, room_id: str) -> list[tuple[str, str]]:
    """This person's recent turns about this room, oldest first, as (message, designer's answer as plan JSON)."""
    logs = [l for l in await ctx.repo.list("agent_requests", roomId=room_id) if l.get("userId") == user_id]
    logs.sort(key=lambda l: l.get("createdAt", ""))
    turns = []
    for l in logs[-HISTORY_TURNS:]:
        plan = l.get("plan") or {}
        said = {"intent": plan.get("intent", "answer"), "reply": l.get("reply", "")}
        if plan.get("variantName") and l.get("status") == "ok":
            said["variantName"] = plan["variantName"]
        said["outcome"] = {"ok": "done, saved as a new layout" if l.get("layoutId") else "answered", "rejected": "couldn't be done",
                           "clarify": "asked a question", "error": "failed"}.get(l.get("status", ""), l.get("status", ""))
        turns.append((l.get("text", ""), json.dumps(said)))
    return turns


async def _replan(ctx: AppContext, system: str, text: str, feedback: list[str], history: list[tuple[str, str]], previous: AgentPlan | str) -> AgentPlan | str:
    """The one retry: Gemini sees what went wrong. If the call itself fails, the previous result stands."""
    try:
        return parse_plan(await ctx.gemini.plan(system, text, violations=feedback, history=history))
    except Exception:  # noqa: BLE001 - quota / network on the retry: report the first plan's outcome
        log.exception("agent: Gemini retry call failed")
        return previous


def _readable(text: str | None) -> str | None:
    t = (text or "").strip()
    return None if t.lower() in ("", "null", "none", "n/a") else t


def _failed_piece(o: Outcome, base: Layout, catalog: dict[str, FurnitureItem]) -> str | None:
    """The piece a rejected option couldn't place, by name: a new instance named in the violations, else the option's first addition."""
    have = {i.id for i in base.items}
    for v in o.result.violations if o.result else []:
        for iid in v.items:
            fid = iid.rsplit("_", 1)[0]
            if iid not in have and fid in catalog:
                return catalog[fid].name.lower()
    for a in o.plan.actions:
        if a.type == "add" and (f := resolve_catalog(a.item, catalog, None)):
            return f.name.lower()
    return None


def _join(names: list[str]) -> str:
    names = list(dict.fromkeys(names))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def _not_a_fit_problem(result: SolveResult) -> bool:
    """Unknown pieces, pieces not in the room, locked pieces: no other wall will help, so don't offer one."""
    return any(v.rule == "locked" or v.message.startswith(("Unknown furniture", "No '")) for v in result.violations)


async def _redesign(ctx: AppContext, plan: AgentPlan, request_id: str, room_doc: dict[str, Any], base: Layout, catalog: dict[str, FurnitureItem],
                    purpose: str | None, before: ValidationResult, review_before: dict[str, Any]) -> PipelineResult:
    """A new design plan: the furnishing flow picks catalog pieces for the theme around what's already there, as a new variant."""
    from app.furnish import furnish_room

    room = Room.model_validate(room_doc)
    theme = (plan.theme or plan.variantName or "a fresh layout").strip()
    made = await furnish_room(ctx, room_doc, base.model_dump(), theme, purpose, catalog)
    lay = made.layout
    # SKILL.md step 4: an arrangement that fails validate_layout.py gets fixed or dropped. Here: drop the added pieces it names, re-check.
    base_ids = {i.id for i in base.items}
    dropped: list[str] = []
    checked = review.skill_validate(room.skeleton, catalog, lay.items, base.items)
    for _ in range(8):
        if checked["ok"]:
            break
        added = [i.id for i in lay.items if i.id not in base_ids]
        # a flagged new piece goes; if only existing pieces are flagged (their path is blocked), the newest piece goes
        bad = ({i for v in checked["violations"] for i in v["items"]} - base_ids) or set(added[-1:])
        if not bad:
            break
        dropped += [catalog[i.furnitureId].name.lower() for i in lay.items if i.id in bad and i.furnitureId in catalog]
        lay = lay.model_copy(update={"items": [i for i in lay.items if i.id not in bad]})
        checked = review.skill_validate(room.skeleton, catalog, lay.items, base.items)
    app = validate_layout(room.skeleton, catalog, lay.items, lay.zones, base.items)
    reply = made.reply
    left_out = [*made.skipped, *dict.fromkeys(dropped)]
    if left_out:
        # the model wrote its reply before anything was placed; when pieces didn't make it, say what's really there
        placed = [catalog[i.furnitureId].name.lower() for i in lay.items if i.id not in base_ids and i.furnitureId in catalog]
        reply = (f"Here's a {lay.name.lower()} layout" + (f" with a {_join(placed)} added" if placed else "")
                 + f". The {_join([n.lower() for n in dict.fromkeys(left_out)])} didn't fit without blocking the way; want me to move something to make room?")
    if dropped:
        lay = lay.model_copy(update={"metrics": app.metrics})
        await ctx.repo.update("layouts", lay.id, {"items": [i.model_dump() for i in lay.items], "metrics": app.metrics.model_dump()})

    moved = review.moved_ids(lay.items, base.items)
    warnings = review.measured_warnings(app, before, checked, review_before, catalog, lay.items)
    option = {
        "variantName": lay.name, "layoutId": lay.id, "recommended": True, "moved": moved, "explanation": plan.reply,
        "tradeoff": review.complete_tradeoff(None, warnings, before.metrics.openFloor, app.metrics.openFloor, []),
        "validation": {"ok": not app.blocked, "warnings": sum(v.severity == "warning" for v in app.violations), "openFloorPct": app.metrics.openFloor},
        "skillValidation": {"ok": checked["ok"], "warnings": len(checked["warnings"]), "open_floor_pct": checked["metrics"]["open_floor_pct"]},
    }
    links = [f"roomplanner://layout/{lay.id}", f"{ctx.settings.public_web_url}/layout/{lay.id}"]
    return PipelineResult("ok", reply, request_id, plan=plan, layout=lay.model_dump(), links=links, options=[option],
                          recommended=lay.name, room_summary=_summary(plan, room, purpose))


@dataclass
class Outcome:
    """One option from the designer, after the solver (skill step 3) and both fit checks (step 4)."""

    name: str
    plan: AgentPlan
    explanation: str | None = None
    tradeoff: str | None = None
    result: SolveResult | None = None
    furniture: FurnitureItem | None = None
    review: dict[str, Any] | None = None
    problems: list[str] = field(default_factory=list)
    catalog: dict[str, FurnitureItem] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return bool(self.result and self.result.ok and self.review and self.review["ok"])


def plan_options(plan: AgentPlan) -> list[tuple[AgentPlan, PlanOption | None]]:
    """The designer's options as single-placement plans, favorite first.

    Top-level constraints are the favorite's. Locks, keep-clears and clear zones hold for every option; an adjacency
    only for the favorite unless an option repeats it.
    """
    if not plan.options:
        return [(plan, None)]
    shared = [c for c in plan.constraints if c.type != "adjacent"]
    ordered = sorted(plan.options, key=lambda o: o.variantName != (plan.recommended or plan.variantName))
    out = []
    for opt in ordered:
        own = opt.constraints or (plan.constraints if opt.variantName == (plan.recommended or plan.variantName) else [])
        constraints = [*own, *(c for c in shared if c not in own)]
        out.append((plan.model_copy(update={"variantName": opt.variantName, "actions": opt.actions, "constraints": constraints, "options": []}), opt))
    return out


def _solve_option(solver: Solver, option: tuple[AgentPlan, PlanOption | None], room: Room, base: Layout, catalog: dict[str, FurnitureItem],
                  furniture_id: str | None, memories: list[str]) -> Outcome:
    plan, opt = option
    o = Outcome(name=plan.variantName or "Variant", plan=plan, explanation=opt.explanation if opt else plan.reply, tradeoff=opt.tradeoff if opt else None)
    result = solver.solve(plan)
    if not result.ok:
        fallback = _advanced_fallback(plan, room, base, catalog, furniture_id, memories)
        if fallback is not None:
            result, o.furniture = fallback
    o.result = result
    if not result.ok:
        o.problems = [v.message for v in result.violations] or ["it doesn't pass the fit check"]
        return o
    o.catalog = {**catalog, **({o.furniture.id: o.furniture} if o.furniture else {})}
    new_zones = [z for z in result.zones if z not in base.zones]
    o.review = review.skill_validate(room.skeleton, o.catalog, result.items, base.items, new_zones)
    if not o.review["ok"]:
        o.problems = [v["message"] for v in o.review["violations"]]
    return o


def _distinct(outcomes: list[Outcome]) -> list[Outcome]:
    """Never pad with near-duplicates: an option whose items land exactly where an earlier one's did is dropped."""
    seen: set[tuple[Any, ...]] = set()
    out = []
    for o in outcomes:
        key = tuple(sorted((i.id, i.x, i.z, i.rotation) for i in o.result.items))  # type: ignore[union-attr]
        if key not in seen:
            seen.add(key)
            out.append(o)
    return out


def _option_out(o: Outcome, layout: Layout, recommended: bool, base: Layout, before: ValidationResult, review_before: dict[str, Any]) -> dict[str, Any]:
    """references/options-output.md, with the saved layout's id and both checks' results."""
    assert o.result and o.result.validation and o.review is not None
    app = o.result.validation
    warnings = review.measured_warnings(app, before, o.review, review_before, o.catalog, layout.items)
    moved = review.moved_ids(layout.items, base.items)
    named = [o.catalog[i.furnitureId].name.lower() for i in layout.items if i.id in moved and i.furnitureId in o.catalog]
    return {
        "variantName": layout.name,
        "layoutId": layout.id,
        "recommended": recommended,
        "moved": moved,
        "explanation": o.explanation,
        "tradeoff": review.complete_tradeoff(o.tradeoff, warnings, before.metrics.openFloor, app.metrics.openFloor, named),
        "validation": {"ok": True, "warnings": sum(v.severity == "warning" for v in app.violations), "openFloorPct": app.metrics.openFloor},
        "skillValidation": {"ok": o.review["ok"], "warnings": len(o.review["warnings"]), "open_floor_pct": o.review["metrics"]["open_floor_pct"]},
    }


def _summary(plan: AgentPlan | None, room: Room, purpose: str | None) -> str:
    return (plan.roomSummary if plan and plan.roomSummary else None) or scene.say_back(room.skeleton, purpose)


async def _finish(ctx: AppContext, request_id: str, user_id: str, room_id: str | None, base_id: str | None, channel: Channel, text: str, out: PipelineResult) -> PipelineResult:
    if note := OFFLINE_NOTE.get():
        OFFLINE_NOTE.set(None)
        out.reply = f"({note}) {out.reply}"
    log = AgentRequestLog(
        id=request_id, userId=user_id, roomId=room_id, baseLayoutId=base_id, channel=channel, text=text, status=out.status, plan=out.plan,
        layoutId=out.layout["id"] if out.layout else None, reply=out.reply, violations=out.violations, createdAt=now_iso(),
        layoutIds=[o["layoutId"] for o in out.options] or ([out.layout["id"]] if out.layout else []),
    )
    await ctx.repo.insert("agent_requests", log.model_dump())
    return out
