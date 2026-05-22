"""CLI entry: resolve a ticket or run demo examples."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from src.agent.agent import resolve_ticket
from src.config import TICKETS_PATH

load_dotenv()
console = Console()

DEMO_TICKETS = ["T-003", "T-005", "T-008"]


def load_tickets() -> dict[str, dict]:
    with TICKETS_PATH.open(encoding="utf-8") as f:
        return {t["id"]: t for t in json.load(f)}


def print_result(result) -> None:
    console.print(Panel("\n".join(result.reasoning_log), title="Reasoning & Tool Trace"))
    if result.execution.approval_draft:
        console.print(
            Panel(
                json.dumps(result.execution.approval_draft.to_dict(), indent=2),
                title="[yellow]HUMAN APPROVAL REQUIRED[/yellow]",
                border_style="yellow",
            )
        )
    console.print(Panel(result.reply, title="Customer Reply"))


def main() -> None:
    if not os.getenv("MOCK_LLM", "0").strip().lower() in ("1", "true", "yes"):
        from src.llm import get_model, get_provider

        console.print(
            f"[dim]LLM: {get_provider()} / {get_model()} "
            f"(set MOCK_LLM=1 for offline; see .env.example)[/dim]"
        )

    parser = argparse.ArgumentParser(description="Customer Support Resolution Agent")
    parser.add_argument("--ticket-id", "-t", help="Ticket ID from data/tickets.json")
    parser.add_argument("--demo", action="store_true", help="Run 3 demo tickets (refund, unknown order, escalation)")
    parser.add_argument("--approve", action="store_true", help="Simulate human approval (demo only; does not execute refund)")
    args = parser.parse_args()

    tickets = load_tickets()

    if args.demo:
        for tid in DEMO_TICKETS:
            console.rule(f"Ticket {tid}")
            result = resolve_ticket(tickets[tid])
            print_result(result)
            if args.approve and result.execution.approval_draft:
                console.print("[green]Human approved[/green] (simulation — no financial API called)")
        return

    tid = args.ticket_id or "T-001"
    if tid not in tickets:
        console.print(f"Unknown ticket {tid}. Available: {', '.join(tickets)}")
        raise SystemExit(1)

    result = resolve_ticket(tickets[tid])
    print_result(result)

    if result.execution.approval_draft and not args.approve:
        console.print(
            "\n[yellow]Financial action is PENDING. Re-run with --approve to simulate human sign-off.[/yellow]"
        )


if __name__ == "__main__":
    main()
