from __future__ import annotations

from dataclasses import dataclass, field

from src.agent.hitl import ApprovalDraft, build_approval_draft, request_human_approval
from src.agent.planner import FinancialAction, Plan, ResolutionPath
from src.tools.escalate import escalate
from src.tools.kb_search import kb_search
from src.tools.order_status import get_order_status


@dataclass
class ToolTrace:
    tool: str
    input: dict
    output: dict


@dataclass
class ExecutionState:
    plan: Plan
    traces: list[ToolTrace] = field(default_factory=list)
    kb_results: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    order_errors: list[dict] = field(default_factory=list)
    escalation: dict | None = None
    approval_draft: ApprovalDraft | None = None
    citations: list[str] = field(default_factory=list)


def _kb_query_from_ticket(ticket: dict) -> str:
    return f"{ticket.get('subject', '')} {ticket.get('body', '')}"


def execute_plan(ticket: dict, plan: Plan) -> ExecutionState:
    state = ExecutionState(plan=plan)

    for sub in plan.subtasks:
        tool = sub.tool
        if tool == "kb_search":
            query = _kb_query_from_ticket(ticket)
            out = kb_search(query)
            state.traces.append(ToolTrace("kb_search", {"query": query}, out))
            if out.get("results"):
                state.kb_results.extend(out["results"])
                for r in out["results"]:
                    state.citations.append(f"[{r['doc_id']}] {r['title']}")

        elif tool == "get_order_status":
            ids = plan.order_ids
            if not ids:
                state.order_errors.append({"error": "no_order_id_in_ticket"})
                continue
            for oid in ids:
                out = get_order_status(oid)
                state.traces.append(ToolTrace("get_order_status", {"order_id": oid}, out))
                if out.get("ok"):
                    state.orders.append(out["order"])
                else:
                    state.order_errors.append(out)

        elif tool == "escalate":
            reason = plan.escalate_reason or plan.rationale or "requires_human_review"
            priority = "high" if "security" in reason else "normal"
            out = escalate(ticket, reason=reason, priority=priority)
            state.traces.append(ToolTrace("escalate", {"reason": reason}, out))
            state.escalation = out.get("escalation")

    if plan.path == ResolutionPath.ESCALATION and state.escalation is None:
        out = escalate(ticket, reason=plan.escalate_reason or "escalation_path", priority="normal")
        state.traces.append(ToolTrace("escalate", {"reason": plan.escalate_reason}, out))
        state.escalation = out.get("escalation")

    if plan.financial_action != FinancialAction.NONE:
        action_label = plan.financial_action.value.replace("_", " ")
        order_total = state.orders[0]["total_usd"] if state.orders else None
        evidence_parts = []
        if state.orders:
            o = state.orders[0]
            evidence_parts.append(f"Order {o['order_id']} status={o['status']}")
        if state.kb_results:
            evidence_parts.append(f"KB: {state.kb_results[0]['title']}")
        if state.order_errors:
            evidence_parts.append(f"Order lookup: {state.order_errors[0].get('error')}")

        draft = build_approval_draft(
            ticket=ticket,
            action=action_label,
            amount_usd=plan.proposed_amount_usd,
            order_total=order_total,
            ticket_body=ticket.get("body", ""),
            evidence="; ".join(evidence_parts) or "No additional evidence",
        )
        state.approval_draft = request_human_approval(draft)

    return state
