from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_escalation_log: list[dict[str, Any]] = []


def escalate(ticket: dict, reason: str, priority: str = "normal") -> dict:
    entry = {
        "ticket_id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "customer_email": ticket.get("customer_email"),
        "reason": reason,
        "priority": priority,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "queue": "tier2_support",
    }
    _escalation_log.append(entry)
    return {"ok": True, "escalation": entry}


def get_escalation_log() -> list[dict]:
    return list(_escalation_log)


def clear_escalation_log() -> None:
    _escalation_log.clear()
