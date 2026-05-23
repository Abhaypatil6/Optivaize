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

load_dotenv()

from src.agent.agent import resolve_ticket
from src.config import TICKETS_PATH

console = Console()

DEMO_TICKETS = ["T-003", "T-005", "T-008"]


def load_tickets() -> dict[str, dict]:
    with TICKETS_PATH.open(encoding="utf-8") as f:
        return {t["id"]: t for t in json.load(f)}


def print_result(result) -> None:
    console.print(Panel("\n".join(result.reasoning_log), title="Trace"))
    if result.execution.approval_draft:
        console.print(
            Panel(
                json.dumps(result.execution.approval_draft.to_dict(), indent=2),
                title="Needs approval",
                border_style="yellow",
            )
        )
    console.print(Panel(result.reply, title="Reply"))


def _print_llm_mode(live: bool) -> None:
    from src.llm import get_model, get_provider

    if live:
        console.print(
            f"[bold cyan]Live LLM[/bold cyan] — {get_provider()} / {get_model()} "
            f"(API key from .env)"
        )
    else:
        console.print("[dim]Offline mock planner/composer (MOCK_LLM=1)[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--ticket-id", help="e.g. T-001")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="T-003, T-005, T-008 via Groq/Gemini API (needs key in .env)",
    )
    parser.add_argument("--approve", action="store_true", help="fake sign-off (demo only)")
    args = parser.parse_args()

    tickets = load_tickets()

    if args.demo:
        # Demo always uses the real API so you can show Groq/Gemini in a recording.
        os.environ["MOCK_LLM"] = "0"
        from src.llm import ensure_live_llm

        ensure_live_llm()
        _print_llm_mode(live=True)

        for tid in DEMO_TICKETS:
            console.rule(tid)
            result = resolve_ticket(tickets[tid])
            print_result(result)
            if args.approve and result.execution.approval_draft:
                console.print("[green]marked approved (simulation only)[/green]")
        return

    # Single ticket: follow .env (MOCK_LLM=0 + key for live, or MOCK_LLM=1 offline)
    _print_llm_mode(live=os.getenv("MOCK_LLM", "0").strip().lower() not in ("1", "true", "yes"))
    if os.getenv("MOCK_LLM", "0").strip().lower() not in ("1", "true", "yes"):
        from src.llm import ensure_live_llm

        ensure_live_llm()

    tid = args.ticket_id or "T-001"
    if tid not in tickets:
        console.print(f"unknown ticket {tid}. try: {', '.join(sorted(tickets))}")
        raise SystemExit(1)

    result = resolve_ticket(tickets[tid])
    print_result(result)

    if result.execution.approval_draft and not args.approve:
        console.print("\n[yellow]still pending — add --approve to simulate a human ok[/yellow]")


if __name__ == "__main__":
    main()
