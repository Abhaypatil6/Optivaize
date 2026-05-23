# Demo — Customer Support Resolution Agent

**Purpose:** Satisfy the take-home requirement for a 2–3 minute demo showing **planner reasoning**, **tool calls**, and the **human-in-the-loop (HITL)** checkpoint.

You can submit **this transcript** as written proof, or record your screen while running the same commands below.

---

## How to record a screen demo (~2–3 minutes)

| Time | What to show on screen |
|------|-------------------------|
| 0:00–0:20 | Terminal: `cd Optivaze`, activate `venv`, `pip install -r requirements.txt` (skip if already done) |
| 0:20–0:30 | Show `.env` with `GROQ_API_KEY` (blur the key) or use `MOCK_LLM=1` for offline demo |
| 0:30–1:15 | Run `python main.py --ticket-id T-003` — scroll through **Reasoning & Tool Trace**, **HUMAN APPROVAL REQUIRED**, **Customer Reply** |
| 1:15–1:45 | Run `python main.py --ticket-id T-005` — highlight `ok=False` and “No order found” (no hallucination) |
| 1:45–2:15 | Run `python main.py --ticket-id T-008` — highlight `escalate` tool and `tier2_support` queue |
| 2:15–2:30 | Optional: `python -m eval.run_eval` showing `10/10 scenarios passed` |

**Commands to run while recording:**

```powershell
cd C:\Users\Abhay\Desktop\Optivaze
.\venv\Scripts\Activate.ps1
$env:MOCK_LLM="1"          # offline, no API key needed
python main.py --ticket-id T-003
python main.py --ticket-id T-005
python main.py --ticket-id T-008
```

**With live Groq LLM** (set in `.env`: `MOCK_LLM=0`, `GROQ_API_KEY=...`):

```powershell
python main.py --ticket-id T-003
```

---

## Example Run 1 — Refund request + HITL checkpoint (T-003)

### Input ticket

| Field | Value |
|-------|--------|
| **ID** | T-003 |
| **Subject** | Refund for defective headset |
| **Body** | Order ORD-1005 arrived but the left earcup has no audio. I want a full refund of $44.99 please. |

### Step 1 — Planner (separate LLM call)

The planner classifies the ticket and decomposes work **before** any tools run:

```
STEP 1 — Planner: classifying ticket and decomposing sub-tasks
  Path: order
  Confidence: 0.85
  Rationale: Refund request requires order context and approval
  Sub-tasks:
    1. Verify order status          → tool: get_order_status
    2. Check returns policy         → tool: kb_search
    3. Draft refund for human approval → tool: compose_reply
  Financial action: refund
  Proposed amount: $44.99
```

**Why this matters:** This is not one mega-prompt. The planner explicitly chooses the **order** path and flags a **financial action** that cannot auto-execute.

### Step 2 — Executor (tool calls)

```
STEP 2 — Executor: running tools per plan

Tool: get_order_status
  Input:  { "order_id": "ORD-1005" }
  Output: { "ok": true, "order": { "status": "delivered", "delivered_at": "2026-05-05", "total_usd": 44.99, ... } }

Tool: kb_search
  Input:  { "query": "Refund for defective headset Order ORD-1005 ..." }
  Output: { "ok": true, "results": [
            { "doc_id": "returns-policy", "title": "Returns & Refunds Policy", "score": 0.42 },
            { "doc_id": "troubleshooting-audio", "title": "Audio Troubleshooting", ... }
          ]}
```

### Step 3 — Human-in-the-loop (mandatory checkpoint)

The agent **does not** issue the refund. It creates a draft held for human approval:

```json
{
  "action": "refund",
  "amount_or_scope": "$44.99",
  "justification": "Customer requested refund per ticket: Order ORD-1005 arrived but the left earcup has no audio. I want a full refund of $44.99 please.",
  "ticket_id": "T-003",
  "status": "pending",
  "evidence_summary": "Order ORD-1005 status=delivered; KB: Returns & Refunds Policy"
}
```

**Rules enforced:**
- `status` is always `pending` until a human approves
- Auto-approve is rejected in code (`request_human_approval` raises if `auto_approve=True`)

### Step 4 — Customer reply (composer)

```
Re: Refund for defective headset

[ACTION PENDING HUMAN APPROVAL] Proposed refund ($44.99).
Justification: Customer requested refund per ticket: ...
Evidence: Order ORD-1005 status=delivered; KB: Returns & Refunds Policy
A support specialist will confirm before anything is processed.

Order ORD-1005: status delivered. Delivered 2026-05-05.

From our help articles:
- Returns & Refunds Policy: ... 30 days ... defective items: full refund ...
Sources: [returns-policy] Returns & Refunds Policy, [troubleshooting-audio] Audio Troubleshooting
```

**Takeaway:** Reply cites KB sources and order facts; it never says “your refund has been issued.”

---

## Example Run 2 — Unknown order / tool failure (T-005)

### Input ticket

| Field | Value |
|-------|--------|
| **ID** | T-005 |
| **Subject** | Order ORD-9999 never arrived |
| **Body** | My order ORD-9999 shows nothing in tracking. Please help. |

### Step 1 — Planner

```
Path: order
Confidence: 0.9
Rationale: Order status inquiry
Sub-tasks:
  1. Fetch order status   → get_order_status
  2. Compose status reply → compose_reply
```

### Step 2 — Executor (failure handled gracefully)

```
Tool: get_order_status
  Input:  { "order_id": "ORD-9999" }
  Output: {
    "ok": false,
    "error": "order_not_found",
    "message": "No order found with ID ORD-9999. Please verify the ID with the customer."
  }
```

No KB search is needed; the agent does **not** invent tracking numbers or delivery dates.

### Step 3 — Customer reply

```
Re: Order ORD-9999 never arrived

No order found with ID ORD-9999. Please verify the ID with the customer.
```

**Takeaway:** Required failure mode — unknown order ID handled without hallucination.

---

## Example Run 3 — Security escalation (T-008)

### Input ticket

| Field | Value |
|-------|--------|
| **ID** | T-008 |
| **Subject** | Account hacked — urgent |
| **Body** | Someone changed my email and placed orders I did not authorize. I need immediate help locking my account. |

### Step 1 — Planner

```
Path: escalation
Confidence: 0.95
Rationale: Security or high-risk issue
Sub-tasks:
  1. Escalate to human security queue → escalate
  2. Draft holding reply              → compose_reply
escalate_reason: security_incident
```

### Step 2 — Executor

```
Tool: escalate
  Input:  { "reason": "security_incident", "priority": "high" }
  Output: {
    "ok": true,
    "escalation": {
      "ticket_id": "T-008",
      "reason": "security_incident",
      "priority": "high",
      "queue": "tier2_support",
      "queued_at": "2026-05-22T..."
    }
  }
```

### Step 3 — Customer reply

```
Re: Account hacked — urgent

Your ticket has been escalated to our team (queue: tier2_support).
Reason: security_incident.
```

**Takeaway:** High-risk tickets bypass automated refunds/order fixes and route to humans immediately.

---

## Quick demo command (all three in one)

```powershell
python main.py --demo
```

Runs T-003, T-005, and T-008 sequentially.

---

## Simulate human approval (optional ending for recording)

```powershell
python main.py --ticket-id T-003 --approve
```

Prints that a human approved the draft. **No refund is executed** — there is no payment API wired up (by design).

---

## Reproduce this transcript locally

```powershell
cd C:\Users\Abhay\Desktop\Optivaze
.\venv\Scripts\Activate.ps1
$env:MOCK_LLM="1"
python main.py --ticket-id T-003
python main.py --ticket-id T-005
python main.py --ticket-id T-008
python -m eval.run_eval
```

Expected eval result: **10/10 scenarios passed**.

---

## What reviewers should see

| Capability | Demonstrated in |
|------------|-----------------|
| Explicit planner + sub-tasks | Run 1, 2, 3 — Step 1 |
| `kb_search` RAG + citations | Run 1 — Step 2 & 4 |
| `get_order_status` | Run 1 (success), Run 2 (failure) |
| `escalate` | Run 3 |
| HITL pending financial action | Run 1 — Step 3 |
| No hallucination on missing order | Run 2 |

This document can be submitted as the **written demo transcript** required by the take-home brief.
