"""
Planner module.

Calls the LLM (via the unified llm.py client) to classify the ticket
and produce an explicit sub-task plan BEFORE any resolution work happens.

This is a separate LLM call from the resolver — satisfying the
"planner step" requirement.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .llm import chat
from .prompts import PLANNER_SYSTEM, PLANNER_USER

logger = logging.getLogger(__name__)


def plan(ticket: dict[str, Any]) -> dict[str, Any]:
    """
    Classify the ticket and decompose it into sub-tasks.

    Returns a dict with keys:
      classification, confidence, order_id, sub_tasks,
      financial_action, escalation_reason
    """
    user_msg = PLANNER_USER.format(
        ticket_id=ticket.get("ticket_id", ""),
        customer_email=ticket.get("customer_email", ""),
        subject=ticket.get("subject", ""),
        body=ticket.get("body", ""),
    )

    logger.info("[PLANNER] Classifying ticket %s", ticket.get("ticket_id"))

    raw = chat(PLANNER_SYSTEM, user_msg, max_tokens=512)
    logger.debug("[PLANNER] Raw response: %s", raw)

    # Strip markdown fencing if the model wraps it anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        plan_data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("[PLANNER] JSON parse failed: %s\nRaw: %s", exc, raw)
        # Fallback: treat as escalation so nothing is lost
        plan_data = {
            "classification": "escalation",
            "confidence": 0.0,
            "order_id": None,
            "sub_tasks": [
                {
                    "step": 1,
                    "action": "escalate",
                    "rationale": "Planner failed to parse — safe fallback.",
                }
            ],
            "financial_action": {
                "type": "none",
                "estimated_amount": None,
                "currency": None,
            },
            "escalation_reason": f"Planner output was malformed: {exc}",
        }

    logger.info(
        "[PLANNER] classification=%s  confidence=%.2f  order_id=%s",
        plan_data.get("classification"),
        plan_data.get("confidence", 0),
        plan_data.get("order_id"),
    )
    return plan_data
