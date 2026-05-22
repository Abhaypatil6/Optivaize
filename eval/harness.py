"""
Evaluation harness — 10 scripted test scenarios.

Run with:
    python eval/harness.py
    python eval/harness.py --verbose

Each scenario specifies:
  - ticket_id                : which ticket from tickets.json to process
  - expected_classification  : what the planner should output
  - expected_resolution_paths: which resolution branch should execute
  - expected_tools           : tool names that MUST appear in tools_called
  - hitl_expected            : whether HITL checkpoint should fire
  - hitl_auto                : APPROVE or REJECT to inject automatically
  - must_contain             : strings that MUST appear in the reply (case-insensitive)
  - must_not_contain         : strings that must NOT appear (hallucination guard)

Pass/fail logic:
  A scenario PASSES if all assertions are satisfied.
  Results are printed in a table and the exit code reflects overall pass/fail.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure the project root is on the path so `agent` is importable
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

# Load tickets
_TICKETS_FILE = _ROOT / "support_resolution_pack" / "tickets.json"
_ALL_TICKETS: dict[str, dict] = {}
with _TICKETS_FILE.open() as f:
    for t in json.load(f)["tickets"]:
        _ALL_TICKETS[t["ticket_id"]] = t


# ── Scenario definitions ──────────────────────────────────────────────────────

SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "S01",
        "description": "Informational: refund timing question (TKT-0001)",
        "ticket_id": "TKT-0001",
        "expected_classification": "informational",
        "expected_resolution_paths": ["kb_answer"],
        "expected_tools": ["kb_search"],
        "hitl_expected": False,
        "hitl_auto": None,
        "must_contain": ["refund", "business day"],
        "must_not_contain": ["ORD-99999", "hallucin"],
    },
    {
        "id": "S02",
        "description": "Order-specific: in-transit desk lamp (TKT-0002)",
        "ticket_id": "TKT-0002",
        "expected_classification": "order_specific",
        "expected_resolution_paths": ["order_lookup"],
        "expected_tools": ["get_order_status"],
        "hitl_expected": False,
        "hitl_auto": None,
        "must_contain": ["transit", "ORD-10002"],
        "must_not_contain": [],
    },
    {
        "id": "S03",
        "description": "Financial: damaged bag refund request (TKT-0003) - APPROVE",
        "ticket_id": "TKT-0003",
        "expected_classification": "financial",
        "expected_resolution_paths": ["financial_approved"],
        "expected_tools": ["get_order_status"],
        "hitl_expected": True,
        "hitl_auto": "APPROVE",
        "must_contain": ["refund"],
        "must_not_contain": [],
    },
    {
        "id": "S04",
        "description": "Informational: Iceland shipping & customs (TKT-0004)",
        "ticket_id": "TKT-0004",
        "expected_classification": "informational",
        "expected_resolution_paths": ["kb_answer"],
        "expected_tools": ["kb_search"],
        "hitl_expected": False,
        "hitl_auto": None,
        "must_contain": ["ship"],
        "must_not_contain": [],
    },
    {
        "id": "S05",
        "description": "Order-specific + financial: lost parcel ORD-10004 (TKT-0005) - APPROVE",
        "ticket_id": "TKT-0005",
        "expected_classification": "financial",
        "expected_resolution_paths": ["financial_approved", "financial_rejected"],
        "expected_tools": ["get_order_status"],
        "hitl_expected": True,
        "hitl_auto": "APPROVE",
        "must_contain": [],
        "must_not_contain": [],
    },
    {
        "id": "S06",
        "description": "Order-specific: cancel already-shipped order ORD-10025 (TKT-0007)",
        "ticket_id": "TKT-0007",
        "expected_classification": "order_specific",
        "expected_resolution_paths": ["order_lookup", "financial_approved", "financial_rejected"],
        "expected_tools": ["get_order_status"],
        "hitl_expected": False,
        "hitl_auto": "REJECT",
        "must_contain": [],
        "must_not_contain": [],
    },
    {
        "id": "S07",
        "description": "Unknown order graceful 404: order PKZ-77 (TKT-0008)",
        "ticket_id": "TKT-0008",
        "expected_classification": "order_specific",
        "expected_resolution_paths": ["order_lookup", "escalation_fallback", "human_queue"],
        "expected_tools": ["get_order_status"],
        "hitl_expected": False,
        "hitl_auto": None,
        "must_contain": [],
        "must_not_contain": [
            "PKZ-77 was shipped",
            "estimated delivery",
            "tracking number",
        ],
    },
    {
        "id": "S08",
        "description": "Financial + complex: refund + store credit demand (TKT-0010) - REJECT",
        "ticket_id": "TKT-0010",
        "expected_classification": "financial",
        "expected_resolution_paths": [
            "financial_approved",
            "financial_rejected",
            "human_queue",
        ],
        "expected_tools": [],
        "hitl_expected": True,
        "hitl_auto": "REJECT",
        "must_contain": [],
        "must_not_contain": [],
    },
    {
        "id": "S09",
        "description": "Escalation: late return outside 30-day window (TKT-0013)",
        "ticket_id": "TKT-0013",
        "expected_classification": "escalation",
        "expected_resolution_paths": ["human_queue", "financial_approved", "financial_rejected"],
        "expected_tools": ["escalate"],
        "hitl_expected": False,
        "hitl_auto": "REJECT",
        "must_contain": [],
        "must_not_contain": [],
    },
    {
        "id": "S10",
        "description": "Escalation urgent: hacked account (TKT-0014)",
        "ticket_id": "TKT-0014",
        "expected_classification": "escalation",
        "expected_resolution_paths": ["human_queue"],
        "expected_tools": ["escalate"],
        "hitl_expected": False,
        "hitl_auto": None,
        "must_contain": [],
        "must_not_contain": [],
    },
]


# ── Assertion helpers ─────────────────────────────────────────────────────────

def _check(scenario: dict, result: Any) -> tuple[bool, list[str]]:
    """Return (passed, list_of_failures)."""
    failures = []

    # Classification check
    exp_cls = scenario.get("expected_classification")
    if exp_cls and result.classification != exp_cls:
        failures.append(
            f"classification: expected '{exp_cls}', got '{result.classification}'"
        )

    # Resolution path check
    exp_paths = scenario.get("expected_resolution_paths", [])
    if exp_paths and result.resolution_path not in exp_paths:
        failures.append(
            f"resolution_path: expected one of {exp_paths}, got '{result.resolution_path}'"
        )

    # Tools called check
    for tool in scenario.get("expected_tools", []):
        if tool not in result.tools_called:
            failures.append(f"expected tool '{tool}' not called (called: {result.tools_called})")

    # HITL triggered check
    if scenario.get("hitl_expected") is True and not result.hitl_triggered:
        failures.append("HITL was expected to trigger but did not")

    # must_contain
    reply_lower = result.reply.lower()
    for phrase in scenario.get("must_contain", []):
        if phrase.lower() not in reply_lower:
            failures.append(f"reply missing expected phrase: '{phrase}'")

    # must_not_contain (hallucination guard)
    for phrase in scenario.get("must_not_contain", []):
        if phrase.lower() in reply_lower:
            failures.append(f"reply contains forbidden phrase (hallucination guard): '{phrase}'")

    return (len(failures) == 0), failures


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all(verbose: bool = True) -> int:
    """Run all scenarios. Returns exit code (0=all pass, 1=some fail)."""
    from agent import agent as agent_module

    results_summary: list[dict] = []
    overall_pass = True

    print("\n" + "=" * 72)
    print("  CUSTOMER-SUPPORT AGENT -- EVALUATION HARNESS")
    print("=" * 72)

    for scenario in SCENARIOS:
        sid = scenario["id"]
        desc = scenario["description"]
        ticket = _ALL_TICKETS.get(scenario["ticket_id"])

        if ticket is None:
            print(f"\n[{sid}] SKIP -- ticket {scenario['ticket_id']} not found in tickets.json")
            continue

        # Set HITL auto-response for this scenario
        if scenario.get("hitl_auto"):
            os.environ["HITL_AUTO_RESPONSE"] = scenario["hitl_auto"]
        else:
            os.environ.pop("HITL_AUTO_RESPONSE", None)

        # Patch hitl module so it picks up the env var at call time
        import agent.hitl as hitl_module
        hitl_module._AUTO_RESPONSE = scenario.get("hitl_auto")

        print(f"\n{'-' * 72}")
        print(f"[{sid}] {desc}")
        print(f"  Ticket  : {ticket['ticket_id']} -- {ticket['subject']}")

        start = time.time()
        error_msg = None
        result = None

        try:
            result = agent_module.run(ticket)
        except Exception as exc:
            error_msg = str(exc)

        elapsed = time.time() - start

        if error_msg:
            passed = False
            failures = [f"Exception: {error_msg}"]
        else:
            passed, failures = _check(scenario, result)

        overall_pass = overall_pass and passed
        status_icon = "PASS" if passed else "FAIL"

        print(f"  Status  : {status_icon}  ({elapsed:.1f}s)")

        if result:
            print(f"  Path    : {result.classification} -> {result.resolution_path}")
            print(f"  Tools   : {result.tools_called}")
            print(f"  HITL    : triggered={result.hitl_triggered}  approved={result.hitl_approved}")
            if verbose:
                print(f"\n  --- REPLY (first 400 chars) ---")
                print(f"  {result.reply[:400].replace(chr(10), chr(10)+'  ')}")

        if failures:
            print(f"\n  FAILURES:")
            for f in failures:
                print(f"    * {f}")

        results_summary.append({
            "id": sid,
            "description": desc,
            "passed": passed,
            "failures": failures,
            "elapsed_s": round(elapsed, 1),
        })

    # Final summary table
    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    total = len(results_summary)
    passed_count = sum(1 for r in results_summary if r["passed"])
    print(f"  Passed: {passed_count}/{total}")
    print()
    for r in results_summary:
        icon = "PASS" if r["passed"] else "FAIL"
        print(f"  [{icon}] [{r['id']}] {r['description'][:60]:60s}  ({r['elapsed_s']}s)")
    print("=" * 72 + "\n")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    # Load .env
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    # ── Validate API key before running any scenarios ─────────────────────────
    _provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    _key_map = {
        "groq":   "GROQ_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }

    if _provider not in _key_map:
        print(f"\n  ERROR: Unknown LLM_PROVIDER='{_provider}'. Supported: groq, gemini")
        print(f"  Open .env and set LLM_PROVIDER=groq or LLM_PROVIDER=gemini\n")
        sys.exit(1)

    _req_key = _key_map[_provider]
    _key_val = os.getenv(_req_key, "").strip()
    if not _key_val or _key_val.startswith("your-") or _key_val.endswith("-here"):
        print(f"\n  ERROR: {_req_key} is not set or still has placeholder value.")
        print(f"  Open .env and set: {_req_key}=your-real-key")
        print(f"  Free Groq key  : https://console.groq.com")
        print(f"  Free Gemini key: https://aistudio.google.com/apikey\n")
        sys.exit(1)

    import logging
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)-8s %(name)s: %(message)s",
    )

    exit_code = run_all(verbose="--verbose" in sys.argv or "-v" in sys.argv)
    sys.exit(exit_code)
