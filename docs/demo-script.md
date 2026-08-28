# Dispute Shield — Demo Script

> **Purpose:** Step-by-step walkthrough for a live Buildathon demo.  
> **Audience:** Judges, reviewers, technical evaluators.  
> **Time:** ~8 minutes end-to-end. Each scenario is self-contained and takes ~45 seconds.

---

## Pre-Demo Setup

```powershell
# 1. Start the database (PostgreSQL on localhost:1234)

# 2. Start the backend
.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Start the frontend
.venv\Scripts\python.exe -m http.server 3000 --directory frontend
```

Open **http://localhost:3000** in the browser.

You should see:
- Green "Dispute Shield v1.0.0" status dot in the header
- FinOps Dashboard loading at the bottom
- All 3 panels visible (Support CRM, Simulator, Control Plane)

---

## Scenario A — Safe Refund (30 sec)

**Talking point:** "When no dispute exists, refunds flow through normally."

1. Select **"A . Safe Refund"** from the dropdown
2. Click **Load**
3. Panel 1 shows customer message: *"I haven't received my order..."*
4. Click **"Refund Rs.7,500"**
5. Panel 3 shows: SAFE TO REFUND, refund APPROVED, PROCESSED
6. ARN appears in the state card

**What to say:**
> "The middleware checked payment state, found no active dispute or pre-alert, and approved the refund. ARN is recorded in the ledger."

---

## Scenario B — Active Dispute, Refund BLOCKED (45 sec)

**Talking point:** "The core collision prevention."

1. Select **"B . Active Dispute"** -- Click **Load**
2. Panel 3 Risk Banner shows: REFUND WOULD BE BLOCKED
3. Click **"Refund Rs.5,000"**
4. Result: BLOCKED — "Dispute already active on this payment"
5. Amount saved shows: Rs.5,000 duplicate outflow PREVENTED

**What to say:**
> "The support agent would have processed this refund. The bank already has an open dispute for the same payment. Dispute Shield intercepts it in real time."

---

## Scenario C — Pre-Alert, Refund BLOCKED (30 sec)

1. Select **"C . Pre-Alert"** -- Click **Load**
2. Click **"Refund Rs.3,000"**
3. Result: BLOCKED — BLOCK_PRE_ALERT

**What to say:**
> "Pre-dispute alerts come from Visa/Mastercard network feeds. In production these would be live network webhooks. The refund is stopped before it reaches chargeback stage."

---

## Scenario D — Partial Refund + Chargeback (60 sec)

1. Select **"D . Partial Refund + Chargeback"** -- Click **Load**
2. Panel 3 shows: Contestable Rs.6,000, Uncovered Rs.4,000, Defense Package: PARTIALLY_DEFENSIBLE
3. Defense Package section shows 2 refund_confirmation evidence items

**What to say:**
> "The dispute is for Rs.10,000 but we can prove Rs.6,000 was already refunded. The remaining Rs.4,000 has no refund evidence — honestly flagged as uncovered. No hallucination."

---

## Scenario E — Refund Then Chargeback (45 sec)

1. Select **"E . Refund Then Chargeback"** -- Click **Load**
2. Panel 3: Contestable Rs.8,000, Uncovered Rs.0
3. Defense Package status: READY
4. Evidence: refund_confirmation with ARN, customer_communication

**What to say:**
> "Full refund was already processed with ARN. Customer opened a chargeback anyway. Defense package auto-assembled: ARN as refund proof, support thread as communication evidence."

---

## Scenario F — Webhook Idempotency (45 sec)

1. Select **"F . Webhook Failure"** -- Click **Load**
2. Click **"Send Refund.Processed"** button
3. First delivery: processed
4. Click **"Send Duplicate"**
5. Second delivery: duplicate_event_ignored

**What to say:**
> "Providers retry webhooks. Same event arriving twice returns duplicate_event_ignored. No extra ledger event, no double refund processing."

---

## Scenario G — Duplicate Webhook (30 sec)

1. Select **"G . Duplicate Webhook"** -- Click **Load**
2. Click **"Duplicate Webhook"** in Panel 2
3. Terminal: 1st=processed, 2nd=duplicate_event_ignored

---

## Scenario H — Out-of-Order Webhook (30 sec)

1. Select **"H . Out-of-Order Webhook"** -- Click **Load**
2. Click **"Out-of-Order Webhook"** in Panel 2
3. Terminal: Stale event result: already_processed

---

## FinOps Dashboard (30 sec)

1. Scroll to FinOps Dashboard at the bottom
2. Highlight: Dangerous Refunds Blocked, Duplicate Outflow Prevented, Evidence Completeness

---

## API Docs

Visit http://localhost:8000/docs

Key endpoints:
- POST /api/refunds/request -- the interceptor
- GET /api/state/{payment_id} -- live state
- GET /api/defense/{dispute_id} -- defense package
- GET /api/metrics -- FinOps metrics
- POST /api/scenarios/load/{name} -- scenario engine

---

## Run the Test Suite

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: 13 passed

---

## Key Technical Points

| Topic | What to Say |
|---|---|
| No LLM in money path | Safety decisions are deterministic. |
| Idempotency | Same key = same refund. No distributed 2PC. |
| Audit trail | ledger_events is append-only, hashed, never mutated. |
| Evidence grounding | Only evidence found in DB is used. Missing evidence explicitly named. |
| Pre-alerts simulated | Verifi/Ethoca integration is the production path. |

---

## Honest Limitations

- Pre-alert feeds are simulated (not live Verifi/Ethoca)
- Razorpay provider calls are mocked (no real API)
- Dispute win rate is not guaranteed
- Webhook HMAC validation not implemented in prototype
- Row-level locking needs distributed coordination in multi-node deployments

---

*Dispute Shield -- Razorpay Buildathon Prototype*
