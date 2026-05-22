"""
Human-in-the-Loop (HITL) checkpoint.

For any financially consequential action (refund, store credit, cancellation),
the agent drafts a structured proposal and BLOCKS until a human types APPROVE,
REJECT, or MODIFY.

In the evaluation harness, this module is monkey-patched to auto-respond so
tests can run without stdin interaction.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Auto-approval for the eval harness ──────────────────────────────────────
# Set HITL_AUTO_RESPONSE=APPROVE or REJECT to skip interactive prompts.
_AUTO_RESPONSE: str | None = os.getenv("HITL_AUTO_RESPONSE")


def request_approval(draft: dict[str, Any]) -> tuple[bool, str]:
    """
    Display the financial action draft and wait for human approval.

    Args:
        draft: structured dict produced by the financial draft LLM call:
               {proposed_action, amount, currency, scope, justification,
                ticket_id, order_id}

    Returns:
        (approved: bool, response: str)
        approved=True means "proceed", False means "abort".

    The agent MUST NOT execute the financial action unless this returns True.
    """
    _print_banner()
    _print_draft(draft)

    if _AUTO_RESPONSE:
        response = _AUTO_RESPONSE.strip().upper()
        print(f"\n[HITL AUTO-RESPONSE] -> {response}\n")
    else:
        response = _prompt_human()

    approved = response == "APPROVE"
    logger.info(
        "[HITL] ticket=%s action=%s decision=%s",
        draft.get("ticket_id"),
        draft.get("proposed_action"),
        response,
    )
    return approved, response


def _print_banner() -> None:
    print("\n" + "=" * 70)
    print("  [WARNING] HUMAN APPROVAL REQUIRED - FINANCIAL ACTION")
    print("=" * 70)


def _print_draft(draft: dict[str, Any]) -> None:
    action = draft.get("proposed_action", "unknown").upper()
    amount = draft.get("amount")
    currency = draft.get("currency", "")
    scope = draft.get("scope", "")
    justification = draft.get("justification", "")
    ticket_id = draft.get("ticket_id", "")
    order_id = draft.get("order_id", "")

    amount_str = f"{currency} {amount:.2f}" if amount is not None else "N/A"

    print(f"\n  Ticket ID   : {ticket_id}")
    print(f"  Order ID    : {order_id or 'N/A'}")
    print(f"  Action      : {action}")
    print(f"  Amount      : {amount_str}")
    print(f"  Scope       : {scope}")
    print(f"\n  Justification:")
    print(f"  {justification}")
    print()


def _prompt_human() -> str:
    while True:
        raw = input("  Your decision [APPROVE / REJECT / MODIFY]: ").strip().upper()
        if raw in ("APPROVE", "REJECT", "MODIFY"):
            return raw
        print("  Please type exactly: APPROVE, REJECT, or MODIFY")
