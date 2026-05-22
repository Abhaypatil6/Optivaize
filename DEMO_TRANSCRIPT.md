# Demo Transcript (≈3 minutes of runs)

Three representative tickets showing planner decomposition, tool calls, and human-in-the-loop.

---

## Run 1 — Refund request (T-003) — HITL checkpoint

**Ticket:** Defective headset, full refund $44.99 on ORD-1005

```
STEP 1 — Planner
  Path: order, confidence: 0.85
  Sub-tasks: Verify order status | Check returns policy | Draft refund for human approval
  Financial action: refund

STEP 2 — Executor
  Tool get_order_status({'order_id': 'ORD-1005'}) -> ok=True
  Tool kb_search({'query': '...'}) -> ok=True (returns-policy, troubleshooting-audio)
  HITL draft created: status=pending

STEP 3 — Customer Reply (excerpt)
  [ACTION PENDING HUMAN APPROVAL] Proposed refund ($44.99).
  Evidence: Order ORD-1005 status=delivered; KB: Returns & Refunds Policy
  A support specialist will confirm before anything is processed.
```

**Takeaway:** Refund is drafted, not executed. Reply does not claim “refund issued.”

---

## Run 2 — Unknown order (T-005) — failure handling

**Ticket:** ORD-9999 never arrived

```
STEP 1 — Planner
  Path: order
  Sub-tasks: Fetch order status | Compose status reply

STEP 2 — Executor
  Tool get_order_status({'order_id': 'ORD-9999'}) -> ok=False, error=order_not_found

STEP 3 — Customer Reply (excerpt)
  No order found with ID ORD-9999. Please verify the ID with the customer.
```

**Takeaway:** Agent does not invent tracking or delivery dates for missing orders.

---

## Run 3 — Security escalation (T-008)

**Ticket:** Account hacked, unauthorized orders

```
STEP 1 — Planner
  Path: escalation, confidence: 0.95
  escalate_reason: security_incident

STEP 2 — Executor
  Tool escalate({'reason': 'security_incident'}) -> queue=tier2_support, priority=high

STEP 3 — Customer Reply (excerpt)
  Your ticket has been escalated to our team (queue: tier2_support).
  Reason: security_incident.
```

**Takeaway:** High-risk tickets skip automated financial/order fixes and route to humans.

---

## Commands to reproduce

```bash
pip install -r requirements.txt
set MOCK_LLM=1
python main.py --demo
python main.py --ticket-id T-003
```

With Groq (free): set `GROQ_API_KEY`, `LLM_PROVIDER=groq`, `MOCK_LLM=0` in `.env`.
