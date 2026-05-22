"""
The three core tools the agent can call:

  kb_search(query)              → RAG over the knowledge base
  get_order_status(order_id)    → Mock order API call, with retry & graceful 404 handling
  escalate(ticket, reason)      → Routes ticket to human queue

Each function returns a typed dict so the agent can reason over structured data.
"""
from __future__ import annotations

import os
import time
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from .rag import retrieve, SearchResult

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
ORDER_API_BASE = os.getenv("ORDER_API_BASE", "http://localhost:8080")
REQUEST_TIMEOUT = float(os.getenv("ORDER_API_TIMEOUT", "5.0"))   # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5   # seconds, multiplied on each attempt

# In-memory escalation queue (persisted to disk for demo purposes)
_ESCALATION_LOG = Path(__file__).parent.parent / ".cache" / "escalations.jsonl"


# ── Tool 1: kb_search ────────────────────────────────────────────────────────

def kb_search(query: str, top_k: int = 3) -> dict[str, Any]:
    """
    Search the product knowledge base using RAG.

    Returns:
        {
          "status": "ok" | "empty",
          "query": str,
          "results": [{"text": str, "source": str, "title": str, "score": float}, ...]
        }

    Failure mode handled: if the KB index is missing or empty, returns status="empty"
    so the agent can fall back to escalation instead of hallucinating.
    """
    try:
        hits: list[SearchResult] = retrieve(query, top_k=top_k)
    except Exception as exc:
        logger.error("kb_search error: %s", exc)
        return {"status": "error", "query": query, "results": [], "error": str(exc)}

    if not hits:
        logger.info("kb_search: no results for query=%r", query)
        return {"status": "empty", "query": query, "results": []}

    return {
        "status": "ok",
        "query": query,
        "results": [
            {
                "text": r.text,
                "source": r.source,
                "title": r.article_title,
                "score": round(r.score, 4),
            }
            for r in hits
        ],
    }


# ── Tool 2: get_order_status ─────────────────────────────────────────────────

def get_order_status(order_id: str) -> dict[str, Any]:
    """
    Fetch a single order from the mock order API.

    Failure modes handled:
      - 404 (unknown order_id): returns status="not_found" — never hallucinated.
      - 500 / network timeout: retried up to MAX_RETRIES times with exponential backoff.
      - After all retries exhausted: returns status="api_error".

    Returns:
        {
          "status": "ok" | "not_found" | "api_error",
          "order_id": str,
          "order": dict | null,
          "error": str | null
        }
    """
    url = f"{ORDER_API_BASE}/orders/{order_id}"
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = httpx.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                return {
                    "status": "ok",
                    "order_id": order_id,
                    "order": resp.json(),
                    "error": None,
                }

            if resp.status_code == 404:
                # Do NOT retry — order simply doesn't exist
                logger.info("get_order_status: order %s not found (404)", order_id)
                return {
                    "status": "not_found",
                    "order_id": order_id,
                    "order": None,
                    "error": f"Order {order_id} was not found in our system.",
                }

            # Any other HTTP error (e.g. 500) → retry
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning(
                "get_order_status attempt %d/%d: %s", attempt, MAX_RETRIES, last_error
            )

        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_error = f"Network error on attempt {attempt}: {exc}"
            logger.warning("get_order_status timeout/connect: %s", last_error)

        # Exponential backoff before next retry
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * (2 ** (attempt - 1)))

    logger.error("get_order_status: all retries exhausted for %s", order_id)
    return {
        "status": "api_error",
        "order_id": order_id,
        "order": None,
        "error": f"Order API unavailable after {MAX_RETRIES} attempts. Last error: {last_error}",
    }


# ── Tool 3: escalate ─────────────────────────────────────────────────────────

def escalate(ticket: dict[str, Any], reason: str, priority: str = "normal") -> dict[str, Any]:
    """
    Route a ticket to the human support queue.

    Args:
        ticket:   The original ticket dict (must include ticket_id, customer_email).
        reason:   Structured reason string explaining why escalation is needed.
        priority: "urgent" | "normal" | "low"

    Returns:
        {
          "status": "escalated",
          "ticket_id": str,
          "escalation_id": str,
          "queue_position": int,
          "reason": str,
          "priority": str
        }

    This tool always succeeds. In production it would POST to a ticketing system.
    Here we write to a local JSONL log so the harness can inspect escalations.
    """
    import datetime, hashlib

    ticket_id = ticket.get("ticket_id", "UNKNOWN")
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    escalation_id = "ESC-" + hashlib.sha1(f"{ticket_id}{ts}".encode()).hexdigest()[:8].upper()

    record = {
        "escalation_id": escalation_id,
        "ticket_id": ticket_id,
        "customer_email": ticket.get("customer_email", ""),
        "subject": ticket.get("subject", ""),
        "reason": reason,
        "priority": priority,
        "escalated_at": ts,
    }

    _ESCALATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _ESCALATION_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    logger.info("Escalated %s → %s (%s)", ticket_id, escalation_id, priority)

    return {
        "status": "escalated",
        "ticket_id": ticket_id,
        "escalation_id": escalation_id,
        "queue_position": 1,
        "reason": reason,
        "priority": priority,
    }
