"""Compose customer-facing reply from execution evidence."""

from __future__ import annotations

from src.agent.executor import ExecutionState
from src.agent.planner import ResolutionPath
from src.llm import chat_text, use_mock_llm


def _mock_reply(ticket: dict, state: ExecutionState) -> str:
    parts = [f"Re: {ticket.get('subject', 'your request')}"]

    if state.approval_draft:
        d = state.approval_draft
        parts.append(
            f"\n[ACTION PENDING HUMAN APPROVAL] Proposed {d.action} ({d.amount_or_scope}). "
            f"Justification: {d.justification}"
        )
        parts.append(f"Evidence: {d.evidence_summary}")
        parts.append("A support specialist will confirm before anything is processed.")

    if state.escalation:
        parts.append(
            f"\nYour ticket has been escalated to our team (queue: {state.escalation.get('queue')}). "
            f"Reason: {state.escalation.get('reason')}."
        )

    if state.orders:
        for o in state.orders:
            parts.append(
                f"\nOrder {o['order_id']}: status **{o['status']}**."
                + (f" Delivered {o['delivered_at']}." if o.get("delivered_at") else "")
                + (f" Shipped {o['shipped_at']}." if o.get("shipped_at") and not o.get("delivered_at") else "")
            )

    if state.order_errors:
        for err in state.order_errors:
            parts.append(f"\n{err.get('message', err.get('error', 'Order lookup failed'))}")

    if state.kb_results:
        parts.append("\nFrom our help articles:")
        for r in state.kb_results[:2]:
            parts.append(f"- {r['title']}: {r['passage'][:200]}...")
        if state.citations:
            parts.append("\nSources: " + ", ".join(state.citations))

    if state.plan.path == ResolutionPath.INFORMATIONAL and not state.kb_results:
        parts.append("\nI could not find a specific article; a human agent will follow up.")

    return "\n".join(parts)


COMPOSE_SYSTEM = """Write a concise, empathetic customer-support reply.
Use only facts from the provided evidence. Cite KB sources as [doc_id] Title.
If order not found, say so clearly — do not invent order data.
If approval is pending, state that clearly and do not say the refund/credit/cancel was completed."""


def compose_reply(ticket: dict, state: ExecutionState) -> str:
    evidence = {
        "orders": state.orders,
        "order_errors": state.order_errors,
        "kb": state.kb_results,
        "citations": state.citations,
        "escalation": state.escalation,
        "approval": state.approval_draft.to_dict() if state.approval_draft else None,
    }
    user = f"Ticket:\n{ticket}\n\nEvidence:\n{evidence}"
    return chat_text(COMPOSE_SYSTEM, user, mock_text=_mock_reply(ticket, state) if use_mock_llm() else None)
