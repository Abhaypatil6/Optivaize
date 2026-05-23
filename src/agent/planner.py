"""Explicit planner step: classify ticket and decompose sub-tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.llm import chat_json, extract_order_ids, use_mock_llm


class ResolutionPath(str, Enum):
    INFORMATIONAL = "informational"
    ORDER = "order"
    ESCALATION = "escalation"


class FinancialAction(str, Enum):
    REFUND = "refund"
    STORE_CREDIT = "store_credit"
    CANCEL_ORDER = "cancel_order"
    NONE = "none"


@dataclass
class SubTask:
    id: str
    description: str
    tool: str | None = None


@dataclass
class Plan:
    path: ResolutionPath
    subtasks: list[SubTask]
    rationale: str
    order_ids: list[str] = field(default_factory=list)
    financial_action: FinancialAction = FinancialAction.NONE
    proposed_amount_usd: float | None = None
    confidence: float = 0.8
    escalate_reason: str | None = None


PLANNER_SYSTEM = """You are a customer-support planning module.
Decompose the ticket into explicit sub-tasks. Choose exactly one resolution path:
- informational: product/policy questions answerable from KB
- order: needs order status lookup
- escalation: fraud, legal, safety, account compromise, or too vague/confident < 0.5

Detect financial actions (refund, store_credit, cancel_order) even if path is order/informational.
Return JSON:
{
  "path": "informational|order|escalation",
  "confidence": 0.0-1.0,
  "rationale": "short",
  "order_ids": ["ORD-..."],
  "financial_action": "refund|store_credit|cancel_order|none",
  "proposed_amount_usd": number or null,
  "escalate_reason": "string or null",
  "subtasks": [{"id":"1","description":"...","tool":"kb_search|get_order_status|escalate|compose_reply|null"}]
}
Rules: refunds/credits/cancellations must set financial_action; never skip subtasks."""


def _extract_dollar_amount(text: str) -> float | None:
    import re

    matches = re.findall(r"\$(\d+(?:\.\d{2})?)", text)
    if matches:
        return float(matches[-1])
    return None


def _mock_plan(ticket: dict) -> dict[str, Any]:
    text = f"{ticket.get('subject', '')} {ticket.get('body', '')}".lower()
    order_ids = extract_order_ids(text)

    if any(w in text for w in ("hacked", "unauthorized", "fraud", "legal", "supervisor")):
        return {
            "path": "escalation",
            "confidence": 0.95,
            "rationale": "Security or high-risk issue",
            "order_ids": order_ids,
            "financial_action": "none",
            "proposed_amount_usd": None,
            "escalate_reason": "security_incident",
            "subtasks": [
                {"id": "1", "description": "Escalate to human security queue", "tool": "escalate"},
                {"id": "2", "description": "Draft holding reply", "tool": "compose_reply"},
            ],
        }

    if "refund" in text or "partial refund" in text:
        amt = _extract_dollar_amount(ticket.get("body", ""))
        return {
            "path": "order" if order_ids else "informational",
            "confidence": 0.85,
            "rationale": "Refund request requires order context and approval",
            "order_ids": order_ids,
            "financial_action": "refund",
            "proposed_amount_usd": amt,
            "escalate_reason": None,
            "subtasks": [
                {"id": "1", "description": "Verify order status", "tool": "get_order_status"},
                {"id": "2", "description": "Check returns policy", "tool": "kb_search"},
                {"id": "3", "description": "Draft refund for human approval", "tool": "compose_reply"},
            ],
        }

    if "store credit" in text or "credit" in text and "$" in text:
        amt = _extract_dollar_amount(ticket.get("body", "")) or 15.0
        return {
            "path": "order",
            "confidence": 0.8,
            "rationale": "Store credit request",
            "order_ids": order_ids,
            "financial_action": "store_credit",
            "proposed_amount_usd": amt,
            "escalate_reason": None,
            "subtasks": [
                {"id": "1", "description": "Look up order", "tool": "get_order_status"},
                {"id": "2", "description": "Review credit policy", "tool": "kb_search"},
                {"id": "3", "description": "Draft credit for approval", "tool": "compose_reply"},
            ],
        }

    if "cancel" in text and order_ids:
        return {
            "path": "order",
            "confidence": 0.85,
            "rationale": "Cancellation request",
            "order_ids": order_ids,
            "financial_action": "cancel_order",
            "proposed_amount_usd": None,
            "escalate_reason": None,
            "subtasks": [
                {"id": "1", "description": "Check if order cancellable", "tool": "get_order_status"},
                {"id": "2", "description": "Review cancellation policy", "tool": "kb_search"},
                {"id": "3", "description": "Draft cancellation for approval", "tool": "compose_reply"},
            ],
        }

    if order_ids and any(w in text for w in ("where is", "status", "tracking", "shipped", "delivered", "never arrived")):
        return {
            "path": "order",
            "confidence": 0.9,
            "rationale": "Order status inquiry",
            "order_ids": order_ids,
            "financial_action": "none",
            "proposed_amount_usd": None,
            "escalate_reason": None,
            "subtasks": [
                {"id": "1", "description": "Fetch order status", "tool": "get_order_status"},
                {"id": "2", "description": "Compose status reply", "tool": "compose_reply"},
            ],
        }

    if any(w in text for w in ("thing i bought", "sounds weird", "hate it", "fix it")) and not order_ids:
        return {
            "path": "escalation",
            "confidence": 0.35,
            "rationale": "Too vague to resolve automatically",
            "order_ids": [],
            "financial_action": "none",
            "proposed_amount_usd": None,
            "escalate_reason": "low_confidence_vague_request",
            "subtasks": [
                {"id": "1", "description": "Escalate to human", "tool": "escalate"},
            ],
        }

    if "billing" in text or "charged twice" in text:
        return {
            "path": "informational",
            "confidence": 0.75,
            "rationale": "Billing policy question",
            "order_ids": order_ids,
            "financial_action": "none",
            "proposed_amount_usd": None,
            "escalate_reason": None,
            "subtasks": [
                {"id": "1", "description": "Search billing KB", "tool": "kb_search"},
                {"id": "2", "description": "Compose reply with citations", "tool": "compose_reply"},
            ],
        }

    return {
        "path": "informational",
        "confidence": 0.85,
        "rationale": "General product/policy question",
        "order_ids": order_ids,
        "financial_action": "none",
        "proposed_amount_usd": None,
        "escalate_reason": None,
        "subtasks": [
            {"id": "1", "description": "Search knowledge base", "tool": "kb_search"},
            {"id": "2", "description": "Compose cited reply", "tool": "compose_reply"},
        ],
    }


def plan_ticket(ticket: dict) -> Plan:
    user = (
        f"Ticket ID: {ticket.get('id')}\n"
        f"Subject: {ticket.get('subject')}\n"
        f"Body: {ticket.get('body')}\n"
        f"Customer: {ticket.get('customer_email')}"
    )
    raw = chat_json(PLANNER_SYSTEM, user, mock_response=_mock_plan(ticket) if use_mock_llm() else None)

    path = ResolutionPath(raw.get("path", "escalation"))
    if raw.get("confidence", 1) < 0.5:
        path = ResolutionPath.ESCALATION

    fin = FinancialAction(raw.get("financial_action", "none"))
    subtasks = [
        SubTask(id=st["id"], description=st["description"], tool=st.get("tool"))
        for st in raw.get("subtasks", [])
    ]
    return Plan(
        path=path,
        subtasks=subtasks,
        rationale=raw.get("rationale", ""),
        order_ids=raw.get("order_ids") or extract_order_ids(user),
        financial_action=fin,
        proposed_amount_usd=raw.get("proposed_amount_usd"),
        confidence=float(raw.get("confidence", 0.8)),
        escalate_reason=raw.get("escalate_reason"),
    )
