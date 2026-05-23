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
    log.append("Planner")
    plan = plan_ticket(ticket)
    log.append(f"  path={plan.path.value} confidence={plan.confidence}")
    log.append(f"  tasks: {[s.description for s in plan.subtasks]}")
    log.append(f"  note: {plan.rationale}")

    log.append("Tools")
    execution = execute_plan(ticket, plan)
    for t in execution.traces:
        log.append(f"  {t.tool}({t.input}) ok={t.output.get('ok', True)}")

    if execution.approval_draft:
        log.append("Approval (pending — not executed)")
        log.append(f"  {execution.approval_draft.to_dict()}")

    log.append("Reply")
    reply = compose_reply(ticket, execution)

    return AgentResult(
        ticket_id=ticket.get("id", ""),
        plan=plan,
        execution=execution,
        reply=reply,
        reasoning_log=log,
    )
