from __future__ import annotations

import json
import re

from src.config import ORDERS_PATH

_orders_cache: dict | None = None


def _load_orders() -> dict:
    global _orders_cache
    if _orders_cache is None:
        with ORDERS_PATH.open(encoding="utf-8") as f:
            _orders_cache = json.load(f)
    return _orders_cache


def extract_order_ids(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"ORD-\d{4}", text, flags=re.IGNORECASE)))


def get_order_status(order_id: str) -> dict:
    order_id = order_id.upper().strip()
    orders = _load_orders()
    record = orders.get(order_id)
    if record is None:
        return {
            "ok": False,
            "order_id": order_id,
            "error": "order_not_found",
            "message": f"No order found with ID {order_id}. Please verify the ID with the customer.",
        }
    return {"ok": True, "order": record}
