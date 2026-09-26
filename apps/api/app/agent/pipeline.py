"""Backboard context -> Gemini plan -> solver -> (one retry) -> forked variant -> reply -> memory write -> agent_requests log."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.agent.prompts import build_system_prompt
from app.catalog import all_furniture
from app.deps import AppContext
from app.integrations.gemini import PLAN_SCHEMA
from app.models import AgentPlan, AgentRequestLog, Channel, Layout, Room, Violation
from app.solver.placement import Solver, SolveResult
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
    system = build_system_prompt(room.skeleton, base, catalog, memories, imported)
    solver = Solver(room.skeleton, catalog, base.items, furniture_id)

    plan_or_err = parse_plan(await ctx.gemini.plan(system, request_text))
    result: SolveResult | None = None
    plan: AgentPlan | None = None
    for attempt in range(2):
        if isinstance(plan_or_err, AgentPlan):
            plan = plan_or_err
            if plan.intent == "clarify" or not plan.actions:
                reply = plan.clarifyingQuestion or plan.reply
                return await _finish(ctx, request_id, user_id, room_id, base_layout_id, channel, request_text, PipelineResult("clarify", reply, request_id, plan=plan))
            result = solver.solve(plan)
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
        createdAt=now_iso(),
        updatedAt=now_iso(),
    )
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
