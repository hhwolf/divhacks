"""Backboard context -> Gemini plan -> solver -> (one retry) -> forked variant -> reply -> memory write -> agent_requests log."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.agent.prompts import build_system_prompt, room_purpose
from app.catalog import all_furniture
from app.deps import AppContext
from app.integrations.gemini import PLAN_SCHEMA
from app.models import AgentPlan, AgentRequestLog, Channel, FurnitureItem, Layout, Room, Violation
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
    if plan.intent == "fit_item" and result.gap_m is not None:
        gap = format_length_imperial(result.gap_m)
        if gap not in reply and "spare" not in reply.lower():
            reply = f"{reply.rstrip('.')} ({gap} to spare)."
    for note in result.notes:
        reply = f"{reply.rstrip('.')}; {note}."
    return reply


def rejection_reply(sk_room: Room, result: SolveResult, alternative: str) -> str:
    if result.shortfall_m and result.failed_wall is not None:
        label = wall_label(sk_room.skeleton, result.failed_wall)
        return f"It's {round(result.shortfall_m * 100)} cm too wide for the {label}; want me to try {alternative}?"
    reason = result.violations[0].message if result.violations else "it doesn't pass the fit check"
    return f"I couldn't make that work: {reason.lower()}. Want me to try {alternative}?"


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
    system = build_system_prompt(room.skeleton, base, catalog, memories, imported, room_purpose(room_doc))
    solver = Solver(room.skeleton, catalog, base.items, furniture_id)

    plan_or_err = parse_plan(await ctx.gemini.plan(system, request_text))
    result: SolveResult | None = None
    fallback_furniture: FurnitureItem | None = None
    plan: AgentPlan | None = None
    for attempt in range(2):
        if isinstance(plan_or_err, AgentPlan):
            plan = plan_or_err
            if plan.intent == "clarify" or not plan.actions:
                reply = plan.clarifyingQuestion or plan.reply
                return await _finish(ctx, request_id, user_id, room_id, base_layout_id, channel, request_text, PipelineResult("clarify", reply, request_id, plan=plan))
            result = solver.solve(plan)
            if not result.ok:
                fallback = _advanced_fallback(plan, room, base, catalog, furniture_id, memories)
                if fallback is not None:
                    result, fallback_furniture = fallback
            if result.ok:
                break
            feedback = [v.message for v in result.violations]
        else:
            feedback = [plan_or_err]
        if attempt == 0:
            plan_or_err = parse_plan(await ctx.gemini.plan(system, request_text, violations=feedback))

    if plan is None or result is None or not result.ok:
        alternative = "the wall by the door" if room.skeleton.doors else "another wall"
        reply = rejection_reply(room, result, alternative) if result else f"I couldn't read a valid plan ({plan_or_err}). Could you rephrase?"
        return await _finish(
            ctx, request_id, user_id, room_id, base_layout_id, channel, request_text,
            PipelineResult("rejected", reply, request_id, plan=plan, violations=result.violations if result else []),
        )

    taken = {l["name"] for l in await ctx.repo.list_by_room("layouts", room_id)}
    assert result.validation is not None
    layout = Layout(
        id=uuid.uuid4().hex[:12],
        roomId=room_id,
        name=dedupe_name((plan.variantName or "Variant").strip()[:60], taken),
        isCurrent=False,
        parentLayoutId=base.id,
        items=result.items,
        zones=result.zones,
        metrics=result.validation.metrics,
        createdBy="agent",
        requestText=request_text,
        style=base.style,
        createdAt=now_iso(),
        updatedAt=now_iso(),
    )
    if fallback_furniture is not None:
        await ctx.repo.insert("furniture", {**fallback_furniture.model_dump(), "userId": user_id, "createdAt": now_iso()})
    await ctx.repo.insert("layouts", layout.model_dump())
    links = [f"roomplanner://layout/{layout.id}", f"{ctx.settings.public_web_url}/layout/{layout.id}"]
    if plan.preferencesLearned:
        await ctx.backboard.add_memories(user_id, plan.preferencesLearned)
    out = PipelineResult("ok", compose_reply(plan, result), request_id, plan=plan, layout=layout.model_dump(), links=links)
    return await _finish(ctx, request_id, user_id, room_id, base_layout_id, channel, request_text, out)


async def _finish(ctx: AppContext, request_id: str, user_id: str, room_id: str | None, base_id: str | None, channel: Channel, text: str, out: PipelineResult) -> PipelineResult:
    log = AgentRequestLog(
        id=request_id, userId=user_id, roomId=room_id, baseLayoutId=base_id, channel=channel, text=text, status=out.status, plan=out.plan,
        layoutId=out.layout["id"] if out.layout else None, reply=out.reply, violations=out.violations, createdAt=now_iso(),
    )
    await ctx.repo.insert("agent_requests", log.model_dump())
    return out
