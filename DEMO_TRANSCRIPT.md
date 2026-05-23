# Demo notes

**Recording setup:** eval offline (no key), demo live (Groq/Gemini from `.env`).

```powershell
cd C:\Users\Abhay\Desktop\Optivaze
.\venv\Scripts\Activate.ps1

# 1) tests — no API key
python -m eval.run_eval

# 2) demo — needs GROQ_API_KEY in .env (forces live LLM)
python main.py --demo
```

You'll see `eval mode: offline` then `Live LLM — groq / llama-3.3-70b-versatile (API key from .env)` on the demo.

---

## 1. Refund — T-003

**Ticket:** Headset on ORD-1005 has no audio in left side. Customer wants $44.99 back.

**Planner**

```
path=order  confidence=0.85
sub-tasks: verify order, check returns policy, draft refund for approval
financial_action=refund  amount=$44.99
```

**Tools**

```
get_order_status(ORD-1005)  -> ok, status=delivered
kb_search(...)              -> returns-policy, troubleshooting-audio
```

**Approval draft** (stays pending)

```json
{
  "action": "refund",
  "amount_or_scope": "$44.99",
  "status": "pending",
  "evidence_summary": "Order ORD-1005 status=delivered; KB: Returns & Refunds Policy"
}
```

**Reply (snippet)** — mentions pending approval, cites policy, does **not** say the refund was processed.

---

## 2. Bad order id — T-005

**Ticket:** ORD-9999 never arrived.

```
get_order_status(ORD-9999) -> ok=false, order_not_found
```

Reply tells the customer we can't find that order and to double-check the id. No invented tracking info.

---

## 3. Hacked account — T-008

**Ticket:** Unauthorized orders, wants account locked.

```
path=escalation
escalate(reason=security_incident) -> queue tier2_support
```

Reply says the ticket was escalated; no automated refund or order edits.

---

## Eval (optional tail of a recording)

```powershell
python -m eval.run_eval
```

Expect `10/10 scenarios passed`.
