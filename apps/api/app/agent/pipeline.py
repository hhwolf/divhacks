"""Interior Designer agent, with Gemini as the orchestrator.

Stage 0 context (skeleton, locks, catalog, Backboard memory, recent requests) -> Stage 1 Gemini picks the intent, i.e. the tool,
and extracts its inputs -> Stage 2 the tool runs: the placement solver (up to 3 validated options, one retry that feeds the
violations back to Gemini), the variant ranker, the rent check or the payment guardrails -> Stage 3 each option becomes a named
variant, stated preferences go back to Backboard -> Stage 4 Gemini words the result as the Interior Designer (deterministic draft
in mock mode or if it fails) -> agent_requests log.

The agent never writes the Base Layout or the Current Room: every placement result is a new `variant` forked from the source.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.agent import narrate
from app.agent.prompts import DESIGNER, build_system_prompt, memory_locks, stated_preferences
from app.catalog import all_furniture
from app.config import RECENT_REQUESTS_IN_CONTEXT
from app.deps import AppContext
from app.models import (
    AgentRequestLog,
    AgentStatus,
    Channel,
    DesignOption,
    GeminiPlan,
    HousingProfile,
    Layout,
    OptionValidation,
    PlanOut,
    RentAsk,
    Room,
    SolverAttempt,
    VariantRank,
    Violation,
)
from app.rent import assess_rent, guard_payment
from app.services.rooms import dedupe_name, make_layout, now_iso, taken_names, touch_room
from app.solver.placement import SolveResult, Solver
from app.solver.validate import validate_layout

log = logging.getLogger(__name__)
DEFAULT_NAMES = {"fit_item": "New Fit", "make_space": "More Space", "keep_clear": "Clear View"}


@dataclass
class PipelineResult:
    status: AgentStatus
    reply: str
    request_id: str
    plan: PlanOut | None = None
    layout: dict[str, Any] | None = None  # the recommended option's variant
    links: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    ranking: list[VariantRank] = field(default_factory=list)
    options: list[DesignOption] = field(default_factory=list)
    recommended: str | None = None
    room_summary: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)  # rent `assessment` / payment `quote`


def _sentence(text: str) -> str:
    text = text.strip()
    text = text[:1].upper() + text[1:]
    return text if text.endswith(("?", ".", "!")) else f"{text}."


def rank_layouts(plan: GeminiPlan, siblings: list[Layout], room: Room, catalog: dict) -> list[VariantRank]:
    """Gemini's ranking when it names real layouts; otherwise a deterministic study-friendliness score from the validator."""
    ids = {l.id for l in siblings}
    given = sorted((r for r in plan.ranking if r.layoutId in ids), key=lambda r: r.rank)
    if given:
        return [VariantRank(layoutId=r.layoutId, rank=i + 1, reason=r.reason) for i, r in enumerate(given)]
    scored = []
    for l in siblings:
        m = validate_layout(room.skeleton, catalog, l.items, l.zones).metrics
        has_desk = any(catalog.get(i.furnitureId) and catalog[i.furnitureId].kind == "desk" for i in l.items)
        score = (has_desk, -m.conflicts, m.walkability == "Good", m.openFloor)
        reason = f"{'has a desk' if has_desk else 'no desk'}, {m.conflicts} conflicts, walkability {m.walkability.lower()}, {m.openFloor:.0f}% open floor"
        scored.append((score, l.id, reason))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [VariantRank(layoutId=lid, rank=i + 1, reason=reason) for i, (_, lid, reason) in enumerate(scored)]


async def _rent_check(ctx: AppContext, plan: GeminiPlan, room: Room, source: Layout) -> tuple[AgentStatus, str, dict[str, Any]]:
    ask = plan.rent or RentAsk()
    previous = (await ctx.repo.list("rent_assessments", roomId=room.id))[-1:] or [None]
    rent = ask.askingRent or (previous[0]["askingRent"] if previous[0] else None)
    if rent is None:
        return "clarify", "What monthly rent should I check?", {}
    profile = HousingProfile(
        roomId=room.id, zip=ask.zip, askingRent=rent, occupancyType=ask.occupancyType or "private_room", declaredIssues=ask.issues,
        depositRequested=ask.depositRequested, applicationFee=ask.applicationFee,
    )
    a = await assess_rent(ctx, profile, layout_id=source.id)
    direction = "above" if a.deltaVsMid > 0 else "below"
    reply = (
        f"${rent:,.0f} a month is ${abs(a.deltaVsMid):,.0f} {direction} the fair middle (${a.estimatedFairRange.mid:,}) for a room this size "
        f"(about {a.spaceQuality.floorAreaSqFt:.0f} sq ft from your scan). It's an estimate with {a.confidence} confidence, not an appraisal."
    )
    if a.legalFlags:
        reply += f" Also: {a.legalFlags[0].rstrip('.')}."
    return "ok", reply, {"assessment": a.model_dump()}


async def _payment_check(ctx: AppContext, plan: GeminiPlan, room: Room) -> tuple[AgentStatus, str, dict[str, Any]]:
    ask = plan.payment
    if ask is None or ask.amount is None:
        return "clarify", _sentence(plan.question or "How much are they asking you to pay?"), {}
    previous = (await ctx.repo.list("rent_assessments", roomId=room.id))[-1:] or [None]
    quote = guard_payment(
        ctx, purpose=ask.purpose, amount=ask.amount, rent_amount=previous[0]["askingRent"] if previous[0] else None, room_id=room.id,
        assessment_id=previous[0]["id"] if previous[0] else None,
    )
    await ctx.repo.insert("payment_quotes", quote.model_dump())
    blocked = quote.status == "blocked"
    # the guardrail that decided it: the blocking one, else the check for this purpose (not the boilerplate around it)
    reason = next((g for g in quote.guardrails if g.startswith("Blocked")), None) if blocked else None
    reason = (reason or (quote.guardrails[1] if len(quote.guardrails) > 1 else quote.guardrails[0])).removeprefix("Blocked: ")
    reply = ("I wouldn't pay that. " if blocked else "That looks okay. ") + reason
    extra: dict[str, Any] = {"quote": quote.model_dump()}
    return ("rejected" if blocked else "ok"), reply, extra


async def run(
    ctx: AppContext,
    *,
    request_text: str,
    user_id: str,
    room: Room,
    source: Layout,
    furniture_id: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    channel: Channel = "app",
) -> PipelineResult:
    started = time.perf_counter()
    request_id = uuid.uuid4().hex[:12]
    trace: dict[str, Any] = {"raw": [], "attempts": [], "validation": None}

    async def finish(out: PipelineResult) -> PipelineResult:
        entry = AgentRequestLog(
            id=request_id, userId=user_id, roomId=room.id, sourceLayoutId=source.id, resultLayoutId=out.layout["id"] if out.layout else None,
            requestText=request_text, attachments=attachments or [], channel=channel, geminiPlan=trace["raw"], plan=out.plan,
            solverAttempts=trace["attempts"], validation=trace["validation"], status=out.status, reply=out.reply,
            latencyMs=round((time.perf_counter() - started) * 1000), createdAt=now_iso(),
        )
        doc = {**entry.model_dump(), "resultLayoutIds": [o.layoutId for o in out.options if o.layoutId], "intent": out.plan.intent if out.plan else None}
        await ctx.repo.insert("agent_requests", doc)
        return out

    # Stage 0: context
    catalog = await all_furniture(ctx.repo)
    memories = await ctx.backboard.get_context(user_id)
    siblings = [Layout.model_validate(l) for l in await ctx.repo.list_by_room("layouts", room.id)]
    recent = [r["requestText"] for r in (await ctx.repo.list("agent_requests", roomId=room.id))[-RECENT_REQUESTS_IN_CONTEXT:] if r.get("requestText")]
    system = build_system_prompt(room.skeleton, source, catalog, memories, recent, siblings, catalog.get(furniture_id) if furniture_id else None)
    solver = Solver(room.skeleton, catalog, source.items, furniture_id, extra_locks=memory_locks(memories))

    # Stage 1 (Gemini picks the tool) + Stage 2 (the tool runs); one retry feeds what failed back to Gemini
    plan: GeminiPlan | None = None
    results: list[SolveResult] = []
    feedback: list[str] | None = None
    for attempt in (1, 2):
        try:
            raw = await ctx.gemini.plan(system, request_text, violations=feedback)
        except Exception as exc:  # quota / network: count it as a failed attempt rather than a 500
            raw = {"error": f"planner unavailable: {exc}"}
        trace["raw"].append(raw)
        try:
            plan = GeminiPlan.model_validate(raw)
        except ValidationError as exc:
            plan, results = None, []
            note = raw.get("error") or f"plan JSON invalid: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}"
            trace["attempts"].append(SolverAttempt(attempt=attempt, ok=False, note=note))
            feedback = [note]
            continue
        out_plan = PlanOut(**plan.model_dump())
        if plan.intent == "clarify":
            return await finish(PipelineResult("clarify", _sentence(plan.question or plan.explanation), request_id, plan=out_plan))
        if plan.intent == "rank_variants":
            ranking = rank_layouts(plan, siblings, room, catalog)
            names = {l.id: l.name for l in siblings}
            listing = "; ".join(f"{r.rank}. {names[r.layoutId]} ({r.reason})" for r in ranking)
            reply = f"{plan.explanation.rstrip('.')}: {listing}." if listing else _sentence(plan.explanation)
            out = PlanOut(**{**plan.model_dump(), "ranking": [r.model_dump() for r in ranking]})
            return await finish(PipelineResult("ok", reply, request_id, plan=out, ranking=ranking))
        if plan.intent == "rent_check":
            status, reply, extra = await _rent_check(ctx, plan, room, source)
            return await finish(PipelineResult(status, reply, request_id, plan=out_plan, extra=extra))
        if plan.intent == "payment_check":
            status, reply, extra = await _payment_check(ctx, plan, room)
            return await finish(PipelineResult(status, reply, request_id, plan=out_plan, extra=extra))
        results = solver.design(plan)
        best = results[0]
        trace["attempts"].append(SolverAttempt(attempt=attempt, ok=best.ok, violations=best.violations, note=best.nearest_miss))
        if best.ok:
            break
        feedback = [v.message for v in best.violations] + ([best.nearest_miss] if best.nearest_miss else [])

    if plan is None or not results or not results[0].ok:
        best = results[0] if results else None
        if best is not None and best.nearest_miss:
            reply = f"I couldn't make that work: {best.nearest_miss}"
        elif best is not None and best.violations:
            reply = f"I couldn't make that work: {best.violations[0].message.lower()}. Could you try a different spot?"
        else:
            reply = "I couldn't turn that into a plan. Could you rephrase it?"
        out_plan = PlanOut(**plan.model_dump()) if plan else None
        return await finish(PipelineResult("rejected", _sentence(reply), request_id, plan=out_plan, violations=best.violations if best else []))

    if results[0].noop:  # nothing to change: say so instead of saving a copy of the source layout
        return await finish(PipelineResult("ok", _sentence(results[0].notes[0] if results[0].notes else "Nothing needed to change"), request_id, plan=PlanOut(**plan.model_dump())))

    # Stage 4 wording (before saving, so the variants get the designer's names)
    locked_ids = solver.locked_ids(plan)
    locked_names = list(dict.fromkeys(catalog[i.furnitureId].name.lower() for i in source.items if i.id in locked_ids and i.furnitureId in catalog))
    facts = narrate.facts_for(room.skeleton, solver.catalog, source.items, plan, results, locked_names)  # includes items the solver created
    text = narrate.draft(plan, facts)
    try:
        text = narrate.merge(text, await ctx.gemini.narrate(DESIGNER, facts, text.model_dump()), len(results))
    except Exception as exc:  # the draft is always good enough to send
        log.warning("gemini narrate failed, using the draft: %s", exc)
    order = [text.recommended_index] + [i for i in range(len(results)) if i != text.recommended_index]

    # Stage 3: one named variant per option, recommended first
    if results[0].new_furniture is not None:
        await ctx.repo.insert("furniture", {**results[0].new_furniture.model_dump(), "userId": user_id, "createdAt": now_iso()})
    taken = await taken_names(ctx, room.id)
    source_pose = {i.id: (i.x, i.z, i.rotation) for i in source.items}
    options: list[DesignOption] = []
    layouts: list[dict[str, Any]] = []
    for i in order:
        res, words = results[i], text.options[i]
        assert res.validation is not None
        name = dedupe_name(words.variantName or plan.variantName or DEFAULT_NAMES.get(plan.intent, "Variant"), taken)
        taken.add(name)
        layout = make_layout(room.id, name, "variant", res.items, res.zones, res.validation, parent=source.id, created_by="agent", request_text=request_text)
        await ctx.repo.insert("layouts", layout.model_dump())
        layouts.append(layout.model_dump())
        m = res.validation.metrics
        options.append(DesignOption(
            variantName=name, layoutId=layout.id, explanation=words.explanation, tradeoff=words.tradeoff,
            moved=[it.id for it in res.items if source_pose.get(it.id) != (it.x, it.z, it.rotation)],
            placement=res.placement, moves=res.moves, zones=res.zones, relaxed=res.relaxed,
            validation=OptionValidation(ok=True, warnings=sum(v.severity == "warning" for v in res.validation.violations), open_floor_pct=m.openFloor),
        ))
    await touch_room(ctx, room.id)
    rec = results[order[0]]
    assert rec.validation is not None
    trace["validation"] = {"violations": [v.model_dump() for v in rec.validation.violations], "metrics": rec.validation.metrics.model_dump()}

    preferences = list(dict.fromkeys([*plan.preferences, *stated_preferences(request_text)]))
    if preferences:
        await ctx.backboard.add_memories(user_id, preferences)
    out_plan = PlanOut(**{**plan.model_dump(), "variantName": options[0].variantName, "explanation": options[0].explanation},
                       placement=rec.placement, moves=rec.moves, zones=rec.zones)
    links = [f"roomplanner://layout/{options[0].layoutId}", f"{ctx.settings.public_web_url}/layout/{options[0].layoutId}"]
    return await finish(PipelineResult(
        "ok", _sentence(text.reply), request_id, plan=out_plan, layout=layouts[0], links=links, options=options,
        recommended=options[0].variantName, room_summary=text.room_summary,
    ))
