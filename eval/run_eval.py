from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MOCK_LLM", "1")

from rich.console import Console
from rich.table import Table

from src.agent.agent import resolve_ticket
from src.config import TICKETS_PATH
from src.tools.escalate import clear_escalation_log

console = Console()


def load_tickets() -> dict[str, dict]:
    with TICKETS_PATH.open(encoding="utf-8") as f:
        tickets = json.load(f)
    return {t["id"]: t for t in tickets}


def load_scenarios() -> list[dict]:
    path = Path(__file__).parent / "scenarios.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def check_scenario(result, expect: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    plan = result.plan
    ex = result.execution
    reply_lower = result.reply.lower()

    if "path" in expect and plan.path.value != expect["path"]:
        failures.append(f"path: expected {expect['path']}, got {plan.path.value}")

    if "tool_called" in expect:
        tools = {t.tool for t in ex.traces}
        if expect["tool_called"] not in tools:
            failures.append(f"tool {expect['tool_called']} not called; got {tools}")

    if expect.get("has_citations") and not ex.citations:
        failures.append("expected KB citations, none found")

    if "financial_action" in expect and plan.financial_action.value != expect["financial_action"]:
        failures.append(
            f"financial_action: expected {expect['financial_action']}, got {plan.financial_action.value}"
        )

    if expect.get("financial_pending"):
        if ex.approval_draft is None:
            failures.append("expected approval draft, got none")
        elif ex.approval_draft.status.value != "pending":
            failures.append(f"approval status should be pending, got {ex.approval_draft.status}")

    if expect.get("approval_not_executed"):
        if "has been processed" in reply_lower or "refund issued" in reply_lower:
            failures.append("reply incorrectly states financial action completed")

    if "order_status" in expect:
        if not ex.orders:
            failures.append("expected order record")
        elif ex.orders[0]["status"] != expect["order_status"]:
            failures.append(f"order status expected {expect['order_status']}")

    if expect.get("order_not_found"):
        if not ex.order_errors:
            failures.append("expected order_not_found error")
        elif not any(e.get("error") == "order_not_found" for e in ex.order_errors):
            failures.append(f"expected order_not_found, got {ex.order_errors}")

    if expect.get("no_fake_delivered"):
        if "delivered" in reply_lower and not ex.orders:
            failures.append("reply hallucinates delivery without order data")

    if expect.get("escalated") and ex.escalation is None:
        failures.append("expected escalation record")

    if "reply_contains" in expect and expect["reply_contains"].lower() not in reply_lower:
        failures.append(f"reply missing '{expect['reply_contains']}'")

    return len(failures) == 0, failures


def main() -> int:
    clear_escalation_log()
    tickets = load_tickets()
    scenarios = load_scenarios()
    table = Table(title="eval")
    table.add_column("Scenario")
    table.add_column("Status")
    table.add_column("Notes")

    passed = 0
    for sc in scenarios:
        ticket = tickets.get(sc["ticket_id"])
        if not ticket:
            table.add_row(sc["name"], "[red]FAIL[/red]", "ticket not found")
            continue
        clear_escalation_log()
        result = resolve_ticket(ticket)
        ok, failures = check_scenario(result, sc["expect"])
        if ok:
            passed += 1
            table.add_row(sc["name"], "[green]PASS[/green]", "")
        else:
            table.add_row(sc["name"], "[red]FAIL[/red]", "; ".join(failures))

    console.print(table)
    console.print(f"\n[bold]{passed}/{len(scenarios)}[/bold] scenarios passed")
    return 0 if passed == len(scenarios) else 1


if __name__ == "__main__":
    raise SystemExit(main())
