"""Support resolution agent orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.agent.composer import compose_reply
from src.agent.executor import ExecutionState, execute_plan
from src.agent.planner import Plan, plan_ticket


@dataclass
class AgentResult:
    ticket_id: str
    plan: Plan
    execution: ExecutionState
    reply: str
    reasoning_log: list[str] = field(default_factory=list)


def resolve_ticket(ticket: dict) -> AgentResult:
    log: list[str] = []
    log.append("STEP 1 — Planner: classifying ticket and decomposing sub-tasks")
    plan = plan_ticket(ticket)
    log.append(f"  Path: {plan.path.value}, confidence: {plan.confidence}")
    log.append(f"  Sub-tasks: {[s.description for s in plan.subtasks]}")
    log.append(f"  Rationale: {plan.rationale}")

    log.append("STEP 2 — Executor: running tools per plan")
    execution = execute_plan(ticket, plan)
    for t in execution.traces:
        log.append(f"  Tool {t.tool}({t.input}) -> ok={t.output.get('ok', True)}")

    if execution.approval_draft:
        log.append("STEP 3 — HITL: financial action draft created (PENDING approval)")
        log.append(f"  {execution.approval_draft.to_dict()}")

    log.append("STEP 4 — Composer: drafting customer reply")
    reply = compose_reply(ticket, execution)

    return AgentResult(
        ticket_id=ticket.get("id", ""),
        plan=plan,
        execution=execution,
        reply=reply,
        reasoning_log=log,
    )
