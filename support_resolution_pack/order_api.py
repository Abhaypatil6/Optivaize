"""Mock order-status API for the Customer-Support Resolution take-home.

Run:
    pip install fastapi uvicorn
    uvicorn order_api:app --reload --port 8080

Endpoints:
    GET /orders/{order_id}                  → full order record (404 if unknown)
    GET /orders?email=foo@example.com       → orders for that email
    GET /healthz                            → liveness

Failure modes the candidate's agent must handle:
    - Unknown order_id → 404, not a guess.
    - Optional simulated latency / flake via SIMULATE_FLAKE env var (see below).
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any

# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException, Query

# Optional fault injection — set SIMULATE_FLAKE=1 to randomly delay or 500.
# The agent should retry / handle gracefully. Off by default so the happy path is reliable.
SIMULATE_FLAKE = os.getenv("SIMULATE_FLAKE", "0") == "1"

DATA_PATH = Path(__file__).parent / "orders.json"
with DATA_PATH.open() as f:
    _DATA: dict[str, Any] = json.load(f)

# Index by order_id for O(1) lookup
_BY_ID = {o["order_id"]: o for o in _DATA["orders"]}

app = FastAPI(title="Mock Order Status API", version="1.0")


def _maybe_flake() -> None:
    """Simulate intermittent slowness or 500s when SIMULATE_FLAKE is on."""
    if not SIMULATE_FLAKE:
        return
    r = random.random()
    if r < 0.10:
        time.sleep(1.5)  # slow response
    if r < 0.05:
        raise HTTPException(status_code=500, detail="Simulated upstream error")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/orders/{order_id}")
def get_order(order_id: str) -> dict[str, Any]:
    """Return a single order by ID, or 404 if not found."""
    _maybe_flake()
    order = _BY_ID.get(order_id)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail=f"Order {order_id} not found",
        )
    return order


@app.get("/orders")
def list_orders_for_email(
    email: str = Query(..., description="Customer email address to look up."),
) -> dict[str, Any]:
    """Return all orders for a given email. Empty list if no orders."""
    _maybe_flake()
    matches = [o for o in _DATA["orders"] if o["customer_email"].lower() == email.lower()]
    return {"email": email, "count": len(matches), "orders": matches}
