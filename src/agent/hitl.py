from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ApprovalDraft:
    action: str
    amount_or_scope: str
    justification: str
    ticket_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    evidence_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "amount_or_scope": self.amount_or_scope,
            "justification": self.justification,
            "ticket_id": self.ticket_id,
            "status": self.status.value,
            "evidence_summary": self.evidence_summary,
        }


def build_approval_draft(
    ticket: dict,
    action: str,
    amount_usd: float | None,
    order_total: float | None,
    ticket_body: str,
    evidence: str,
) -> ApprovalDraft:
    if amount_usd is not None:
        scope = f"${amount_usd:.2f}"
    elif order_total is not None:
        scope = f"full order value ${order_total:.2f}"
    else:
        scope = "per policy review"

    justification = (
        f"Customer requested {action} per ticket: {ticket_body[:120]}..."
        if len(ticket_body) > 120
        else f"Customer requested {action} per ticket: {ticket_body}"
    )

    return ApprovalDraft(
        action=action,
        amount_or_scope=scope,
        justification=justification,
        ticket_id=ticket.get("id", "unknown"),
        evidence_summary=evidence[:500],
    )


def request_human_approval(draft: ApprovalDraft, auto_approve: bool = False) -> ApprovalDraft:
    if auto_approve:
        raise ValueError("can't auto-approve money actions")
    draft.status = ApprovalStatus.PENDING
    return draft
