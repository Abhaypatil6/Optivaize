"""
Main agent orchestrator.

Executes the plan produced by the planner:
  1. informational  → kb_search → compose reply with citations
  2. order_specific → get_order_status → compose grounded reply
  3. financial      → kb_search + get_order_status → HITL draft → human approval → execute
  4. escalation     → escalate tool → done

Uses the unified llm.chat() so any provider (Gemini, Groq, Ollama…) works.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .hitl import request_approval
from .llm import chat
from .planner import plan
from .prompts import (
    FINANCIAL_DRAFT_SYSTEM,
    FINANCIAL_DRAFT_USER,
    RESOLVER_SYSTEM,
    RESOLVER_USER,
)
from .tools import escalate, get_order_status, kb_search

logger = logging.getLogger(__name__)


# ── Result schema ─────────────────────────────────────────────────────────────

class AgentResult:
    def __init__(
        self,
        ticket_id: str,
        classification: str,
        resolution_path: str,
        reply: str,
        tools_called: list[str],
        hitl_triggered: bool,
        hitl_approved: bool | None,
        escalation_id: str | None,
        metadata: dict[str, Any],
    ):
        self.ticket_id = ticket_id
        self.classification = classification
        self.resolution_path = resolution_path
        self.reply = reply
        self.tools_called = tools_called
        self.hitl_triggered = hitl_triggered
        self.hitl_approved = hitl_approved
        self.escalation_id = escalation_id
        self.metadata = metadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "classification": self.classification,
            "resolution_path": self.resolution_path,
            "reply": self.reply,
            "tools_called": self.tools_called,
            "hitl_triggered": self.hitl_triggered,
            "hitl_approved": self.hitl_approved,
            "escalation_id": self.escalation_id,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _compose_reply(ticket: dict[str, Any], evidence: str, instructions: str) -> str:
    user_msg = RESOLVER_USER.format(
        ticket_id=ticket.get("ticket_id", ""),
        customer_email=ticket.get("customer_email", ""),
        subject=ticket.get("subject", ""),
        body=ticket.get("body", ""),
        evidence=evidence,
        instructions=instructions,
    )
    return chat(RESOLVER_SYSTEM, user_msg, max_tokens=1024)


def _draft_financial_action(
    ticket: dict[str, Any],
    order_data: str,
    kb_evidence: str,
    requested_action: str,
) -> dict[str, Any]:
    user_msg = FINANCIAL_DRAFT_USER.format(
        ticket_id=ticket.get("ticket_id", ""),
        customer_email=ticket.get("customer_email", ""),
        body=ticket.get("body", ""),
        order_data=order_data,
        kb_evidence=kb_evidence,
        requested_action=requested_action,
    )
    raw = chat(FINANCIAL_DRAFT_SYSTEM, user_msg, max_tokens=512)

    # Strip markdown fencing if model wraps output anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("[AGENT] Could not parse financial draft JSON: %s", raw)
        return {
            "proposed_action": "refund",
            "amount": None,
            "currency": None,
            "scope": "Unable to determine — parse error",
            "justification": raw[:200],
            "ticket_id": ticket.get("ticket_id"),
            "order_id": None,
        }


# ── Resolution paths ──────────────────────────────────────────────────────────

def _resolve_informational(ticket: dict[str, Any], plan_data: dict[str, Any]) -> AgentResult:
    logger.info("[AGENT] Path: informational")
    query = f"{ticket.get('subject', '')} {ticket.get('body', '')}"

    kb_result = kb_search(query)
    tools_called = ["kb_search"]

    if kb_result["status"] == "empty" or not kb_result["results"]:
        logger.warning("[AGENT] No KB results — escalating")
        esc = escalate(
            ticket,
            reason="Knowledge base returned no relevant articles. Human review needed.",
        )
        tools_called.append("escalate")
        return AgentResult(
            ticket_id=ticket["ticket_id"],
            classification="informational",
            resolution_path="escalation_fallback",
            reply="We've escalated your query to our support team who will get back to you shortly.",
            tools_called=tools_called,
            hitl_triggered=False,
            hitl_approved=None,
            escalation_id=esc.get("escalation_id"),
            metadata={"kb_result": kb_result},
        )

    evidence_parts = [
        f"[{r['source']}] {r['title']}\n{r['text']}"
        for r in kb_result["results"]
    ]
    evidence = "\n\n---\n\n".join(evidence_parts)

    instructions = (
        "Answer the customer's question using ONLY the evidence above. "
        "Cite each source article ID in parentheses after each factual claim. "
        "Be helpful and concise."
    )
    reply = _compose_reply(ticket, evidence, instructions)

    return AgentResult(
        ticket_id=ticket["ticket_id"],
        classification="informational",
        resolution_path="kb_answer",
        reply=reply,
        tools_called=tools_called,
        hitl_triggered=False,
        hitl_approved=None,
        escalation_id=None,
        metadata={"kb_result": kb_result},
    )


def _resolve_order_specific(ticket: dict[str, Any], plan_data: dict[str, Any]) -> AgentResult:
    logger.info("[AGENT] Path: order_specific")
    order_id: str | None = plan_data.get("order_id")
    tools_called: list[str] = []

    kb_result = kb_search(
        f"{ticket.get('subject', '')} {ticket.get('body', '')}", top_k=2
    )
    tools_called.append("kb_search")

    order_result: dict[str, Any] = {}
    if order_id:
        order_result = get_order_status(order_id)
        tools_called.append("get_order_status")
    else:
        logger.warning("[AGENT] No order_id extracted by planner for order_specific ticket")

    # Build evidence block
    evidence_parts: list[str] = []

    status = order_result.get("status")
    if status == "ok":
        evidence_parts.append(
            f"ORDER RECORD ({order_id}):\n{json.dumps(order_result['order'], indent=2)}"
        )
    elif status == "not_found":
        evidence_parts.append(
            f"ORDER LOOKUP: The order ID '{order_id}' was not found in our system. "
            "Do not invent any order details."
        )
    elif status == "api_error":
        evidence_parts.append(
            f"ORDER LOOKUP: The order API is temporarily unavailable. "
            f"Error: {order_result.get('error')}"
        )

    for r in kb_result.get("results") or []:
        evidence_parts.append(f"[{r['source']}] {r['title']}\n{r['text']}")

    evidence = "\n\n---\n\n".join(evidence_parts) if evidence_parts else "No evidence retrieved."

    # If planner also flagged a financial action, hand off
    fin = plan_data.get("financial_action", {})
    if fin.get("type") not in (None, "none", ""):
        return _resolve_financial(ticket, plan_data, order_result, kb_result)

    instructions = (
        "Reply to the customer based strictly on the order record above. "
        "If the order was not found, say so clearly and ask them to double-check the order number. "
        "Never invent order details, tracking numbers, or dates."
    )
    reply = _compose_reply(ticket, evidence, instructions)

    return AgentResult(
        ticket_id=ticket["ticket_id"],
        classification="order_specific",
        resolution_path="order_lookup",
        reply=reply,
        tools_called=tools_called,
        hitl_triggered=False,
        hitl_approved=None,
        escalation_id=None,
        metadata={"order_result": order_result},
    )


def _resolve_financial(
    ticket: dict[str, Any],
    plan_data: dict[str, Any],
    order_result: dict[str, Any] | None = None,
    kb_result: dict[str, Any] | None = None,
) -> AgentResult:
    logger.info("[AGENT] Path: financial (requires HITL)")
    order_id: str | None = plan_data.get("order_id")
    tools_called: list[str] = []

    if order_result:
        tools_called.append("get_order_status")
    elif order_id:
        order_result = get_order_status(order_id)
        tools_called.append("get_order_status")

    if kb_result:
        tools_called.append("kb_search")
    else:
        kb_result = kb_search(
            f"{ticket.get('subject', '')} {ticket.get('body', '')}", top_k=3
        )
        tools_called.append("kb_search")

    order_data_str = (
        json.dumps(order_result.get("order") or {}, indent=2)
        if order_result
        else "No order data available."
    )
    kb_evidence_str = "\n\n".join(
        f"[{r['source']}] {r['title']}: {r['text']}"
        for r in (kb_result.get("results") or [])
    ) or "No KB evidence."

    fin = plan_data.get("financial_action", {})
    requested_action = (
        f"{fin.get('type', 'refund')} of approximately "
        f"{fin.get('currency', 'EUR')} {fin.get('estimated_amount', 'unknown')}"
    )

    draft = _draft_financial_action(ticket, order_data_str, kb_evidence_str, requested_action)
    draft["ticket_id"] = ticket.get("ticket_id")
    draft["order_id"] = order_id

    # ── HUMAN-IN-THE-LOOP CHECKPOINT ─────────────────────────────────────
    approved, human_response = request_approval(draft)
    # ─────────────────────────────────────────────────────────────────────

    if approved:
        evidence = f"APPROVED FINANCIAL ACTION:\n{json.dumps(draft, indent=2)}\n\n{kb_evidence_str}"
        instructions = (
            "The human operator has APPROVED the financial action. "
            "Write a warm, professional reply confirming to the customer that the action "
            "will be processed, with realistic timelines from the KB evidence. "
            "Summarise the action in plain English — do not include raw JSON."
        )
        reply = _compose_reply(ticket, evidence, instructions)
        resolution_path = "financial_approved"
        esc_id = None
    else:
        esc = escalate(
            ticket,
            reason=(
                f"Financial action REJECTED by human (response: {human_response}). "
                f"Proposed: {draft.get('proposed_action')} "
                f"{draft.get('currency')} {draft.get('amount')}"
            ),
            priority="normal",
        )
        tools_called.append("escalate")
        evidence = f"Financial action rejected. Escalation ID: {esc.get('escalation_id')}"
        instructions = (
            "The requested financial action could not be automatically approved. "
            "Apologise sincerely and tell the customer their case has been escalated "
            "to a senior agent. Give a realistic response-time estimate (1–2 business days)."
        )
        reply = _compose_reply(ticket, evidence, instructions)
        resolution_path = "financial_rejected"
        esc_id = esc.get("escalation_id")

    return AgentResult(
        ticket_id=ticket["ticket_id"],
        classification="financial",
        resolution_path=resolution_path,
        reply=reply,
        tools_called=tools_called,
        hitl_triggered=True,
        hitl_approved=approved,
        escalation_id=esc_id,
        metadata={"draft": draft, "order_result": order_result},
    )


def _resolve_escalation(ticket: dict[str, Any], plan_data: dict[str, Any]) -> AgentResult:
    logger.info("[AGENT] Path: escalation")
    reason = plan_data.get("escalation_reason") or "Classified as requiring human review."

    priority = "urgent" if any(
        kw in ticket.get("body", "").lower()
        for kw in ["hacked", "fraud", "security", "stolen", "unauthorised", "urgent"]
    ) else "normal"

    esc = escalate(ticket, reason=reason, priority=priority)

    evidence = f"Escalation ID: {esc.get('escalation_id')}\nPriority: {priority}"
    instructions = (
        "The customer's request has been escalated to our specialist team. "
        "Write a brief, empathetic acknowledgement. "
        "Do NOT make promises about outcomes. "
        f"Priority: {priority}."
    )
    reply = _compose_reply(ticket, evidence, instructions)

    return AgentResult(
        ticket_id=ticket["ticket_id"],
        classification="escalation",
        resolution_path="human_queue",
        reply=reply,
        tools_called=["escalate"],
        hitl_triggered=False,
        hitl_approved=None,
        escalation_id=esc.get("escalation_id"),
        metadata={"escalation": esc, "priority": priority},
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def run(ticket: dict[str, Any]) -> AgentResult:
    """
    Resolve a single support ticket end-to-end.

    Step 1: Planner  — classifies ticket + decomposes into sub-tasks (separate LLM call)
    Step 2: Execute  — routes to informational / order_specific / financial / escalation
    """
    logger.info("=" * 60)
    logger.info("[AGENT] Processing ticket: %s", ticket.get("ticket_id"))

    # Step 1 — Plan (always a separate LLM call)
    plan_data = plan(ticket)
    classification = plan_data.get("classification", "escalation")

    # Step 2 — Execute
    if classification == "informational":
        result = _resolve_informational(ticket, plan_data)
    elif classification == "order_specific":
        result = _resolve_order_specific(ticket, plan_data)
    elif classification == "financial":
        result = _resolve_financial(ticket, plan_data)
    else:
        result = _resolve_escalation(ticket, plan_data)

    logger.info("[AGENT] Done: %s → %s", ticket.get("ticket_id"), result.resolution_path)
    return result
