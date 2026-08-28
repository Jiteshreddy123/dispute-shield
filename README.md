# 🛡️ Dispute Shield

> **Track: AI Finance Controller — Razorpay Buildathon**

**Dispute Shield is a smart middleware layer that intercepts customer support refunds to block double-charges when a bank dispute is already brewing, and automatically builds ironclad evidence packages if a customer files a chargeback later.**

---

## The Problem We Solve

When a customer contacts support requesting a refund, the support agent has **zero visibility** into whether the bank has already received a dispute signal for the same payment.

If the agent processes the refund while a dispute is in flight:

- The merchant pays **twice** — once via the voluntary refund, once via the chargeback
- No structured evidence is ever assembled for the dispute
- The duplicate outflow is **entirely avoidable** with the right middleware

> Existing reconciliation tools operate **after the fact**. Dispute Shield sits in the critical path **before money moves**.

---

## Live Demo

The project ships with a **story-driven interactive simulator** — no technical knowledge needed for a judge to understand the product.

```
Open http://localhost:3000
Pick a story → step through it → see the system decide in real time
```

**8 built-in scenarios:**

| Story | What it demonstrates |
|---|---|
| ⚡ A Dispute Is Brewing | Pre-dispute alert blocks refund (HERO scenario) |
| ⚔️ A Chargeback Is Already Open | Active dispute blocks refund — double liability prevented |
| 🕵️ Refunded — Then Charged Back | Merchant refunds, customer still files chargeback — auto-defense built |
| ✅ A Normal Refund | Clean path — approved, processed, ARN issued |
| ⚖️ Partial Refund, Full Chargeback | Partial coverage quantified — ₹6K covered, ₹4K exposed |
| 🔄 The Webhook Arrived Twice | Idempotent processing — one financial effect |
| ⏱️ The Network Went Down | Safe retry with idempotency key |
| 🔀 Events Arrived Out of Order | Financial state cannot regress |

Each scenario tells a human story (Ramu's ₹5,000 jacket) before revealing the technical decision.

---

## How It Works: Prevent → Execute → Defend

```
Support Agent clicks Refund
        │
        ▼
Dispute Shield Middleware (FastAPI)
        │
        ├── Is there an active dispute?     → BLOCK
        ├── Is there a pre-dispute alert?   → BLOCK
        ├── Would this over-refund?         → BLOCK
        └── None of the above              → APPROVE
                                                │
                                                ▼
                                         execute_refund()
                                                │
                                                ▼
                                        Razorpay Provider
                                         (idempotent key)
                                                │
                                                ▼
                                    POST /webhooks/razorpay
                                     refund.processed
                                                │
                                                ▼
                                    Refund → PROCESSED
                                    ARN recorded in ledger

Later: POST /webhooks/razorpay/dispute
        payment.dispute.created
                │
                ▼
        Evidence Matcher
                │
                ▼
        Defense Package
        (refund_confirmation + customer_communication)
```

**The financial safety decision is deterministic — never delegated to an LLM.**

AI is used only for synthesizing unstructured support communication into the defense narrative. It never touches money movement logic.

---

## AI Finance Controller Track Fit

This project addresses three pillars of the AI Finance Controller track:

| Pillar | What Dispute Shield Delivers |
|---|---|
| **Real-time financial safety** | Intercepts refund requests in the critical path before provider API is called |
| **Automated dispute intelligence** | Assembles evidence packages from structured data on every `payment.dispute.created` webhook |
| **Financial visibility** | Live FinOps metrics: duplicate outflow prevented, evidence coverage, defense readiness |

**Why this is not just a reconciliation dashboard:**
Reconciliation is retrospective — it tells you after the double-payment has occurred. Dispute Shield is prospective — it prevents the duplicate outflow from happening.

---

## Architecture

### Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python) |
| Database | PostgreSQL 18 |
| ORM | SQLAlchemy 2.0 (async) |
| Webhook simulation | In-process mock (Razorpay API contract) |
| Frontend | Vanilla HTML/CSS/JS (story-based simulator) |

### Core Domain Models

```
Payment          → CAPTURED
RefundIntent     → CHECKING → APPROVED → EXECUTING → PENDING → PROCESSED
                          → BLOCKED
Refund           → PENDING → PROCESSED (with ARN)
Dispute          → OPEN
DefensePackage   → READY | PARTIALLY_DEFENSIBLE | INCOMPLETE
LedgerEvent      → append-only, hashed, never mutated
ProviderEvent    → idempotency layer for webhook deduplication
```

### Key Safety Properties

- **Idempotency keys** — same key always resolves to the same provider refund
- **Webhook deduplication** — `provider_events` table prevents duplicate ledger effects
- **Row-level locking** — `SELECT FOR UPDATE` on payment during refund request
- **Out-of-order protection** — PROCESSED + stale webhook → `already_processed` (no regression)
- **No fake 2PC** — external provider not in our DB transaction; idempotency + outbox instead
- **Integer paise arithmetic** — no floating point in financial calculations

### Evidence Pipeline

| Evidence Type | Source | When Present |
|---|---|---|
| `refund_confirmation` | Refund record (ARN, amount, timestamp) | When PROCESSED refunds exist |
| `customer_communication` | SupportMessage records | When support messages exist |
| Missing evidence | Explicitly named in defense summary | Always — never hallucinated |

---

## API Reference

| Endpoint | Purpose |
|---|---|
| `POST /api/refunds/request` | Intercept + risk-check a refund request |
| `GET /api/state/{payment_id}` | Live payment + refund + dispute state |
| `GET /api/defense/{dispute_id}` | Assembled defense package + evidence |
| `GET /api/metrics` | FinOps metrics (blocked count, amounts, coverage) |
| `POST /api/scenarios/load/{name}` | Seed one of 8 demo scenarios |
| `POST /api/scenarios/reset` | Wipe all demo data |
| `POST /webhooks/razorpay` | Handle `refund.processed` events (idempotent) |
| `POST /webhooks/razorpay/dispute` | Handle `payment.dispute.created` events |

Full interactive docs: `http://localhost:8000/docs`

---

## Quick Start (Local)

### Prerequisites
- Python 3.13+
- PostgreSQL running on `localhost:1234`, database `dispute-shield`
- `.env` with `DATABASE_URL=postgresql+asyncpg://...`

### Run in 4 commands

```powershell
# 1. Install dependencies
.venv\Scripts\pip install -r requirements.txt

# 2. Initialise the database
.venv\Scripts\python.exe -m app.db.init_db

# 3. Start the backend
.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Start the frontend (new terminal)
.venv\Scripts\python.exe -m http.server 3000 --directory frontend
```

Open **http://localhost:3000** → choose a story → run the simulation.

### Run Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
# Expected: 13 passed
```

---

## Deployment

### Recommended: Railway (Backend + Database)

Railway supports FastAPI + managed PostgreSQL with zero infrastructure setup.

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add a **PostgreSQL** plugin — Railway injects `DATABASE_URL` automatically
4. Set environment variable: `DATABASE_URL` (Railway provides this)
5. Set start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Run `python -m app.db.init_db` as a one-off command to initialise the schema

**Frontend:** Deploy the `frontend/` directory to [Vercel](https://vercel.com) or [Netlify](https://netlify.com) (static site — drag and drop).

Update `API_BASE` in `frontend/app.js` line 1 to point to your Railway backend URL.

### Alternative: Render

1. New Web Service → connect GitHub repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add a Render PostgreSQL database and copy the internal URL to `DATABASE_URL`

### Alternative: Fly.io

```bash
fly launch
fly postgres create
fly secrets set DATABASE_URL="postgresql+asyncpg://..."
fly deploy
```

---

## Limitations (Honest)

| Component | Reality |
|---|---|
| Pre-dispute alerts | **Simulated** — not live Verifi/Ethoca/CDRN integration |
| Razorpay provider | **Mocked** — no real API calls made |
| AI defense narrative | **Rule-based text** — LLM would improve fluency, not required for correctness |
| Dispute outcomes | **Not guaranteed** — depend on issuer/network decisions |
| Webhook HMAC | Not validated in prototype — add `X-Razorpay-Signature` check in production |
| Distributed locking | Row-level `SELECT FOR UPDATE` — replace with distributed lock in multi-node deployment |

> Dispute Shield does **not** claim to integrate with live Visa/Mastercard networks, guarantee dispute wins, or replace Razorpay's reconciliation tools. It is a complementary proactive middleware control layer.

---

## Project Structure

```
dispute-shield/
├── app/
│   ├── main.py              # FastAPI app, all API routes, webhook handlers
│   ├── db/
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   └── init_db.py       # Schema initialisation
│   ├── domain/
│   │   ├── risk_engine.py   # Deterministic refund safety decision
│   │   ├── refund_service.py
│   │   ├── refund_execution.py
│   │   └── defense_service.py
│   └── providers/
│       └── razorpay_mock.py # Razorpay API mock with idempotency
├── frontend/
│   ├── index.html           # Story-driven simulator shell
│   ├── app.js               # Story engine + backend API calls
│   └── styles.css           # Dark fintech UI
├── tests/
│   └── test_scenarios.py    # 13 integration tests (all passing)
├── docs/
│   └── demo-script.md       # Step-by-step judge demo guide
└── requirements.txt
```

---

*Razorpay Buildathon — AI Finance Controller Track*
