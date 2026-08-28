import uuid
from datetime import datetime

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Header,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    Refund,
    RefundIntent,
    ProviderEvent,
    LedgerEvent,
    Payment,
    Dispute,
    PreAlert,
    DefensePackage,
    EvidenceItem,
    SupportMessage,
    OutboxEvent,
)
from app.schemas.refund import RefundRequest
from app.schemas.webhook import (
    RazorpayWebhook,
    RazorpayDisputeWebhook,
)
from app.domain.refund_service import request_refund
from app.domain.refund_execution import execute_refund
from app.domain.defense_service import build_defense_package


app = FastAPI(
    title="Dispute Shield",
    version="1.0.0",
    description=(
        "Smart middleware that intercepts refunds when disputes are brewing "
        "and automatically builds defense packages for chargebacks."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    from app.db.init_db import init_db
    try:
        init_db()
        print("Startup: Database tables verified/initialized.")
    except Exception as e:
        print(f"Startup DB init warning: {e}")


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": "Dispute Shield",
        "version": "1.0.0",
    }


# =========================================================
# 1. REQUEST A REFUND
# =========================================================

@app.post("/api/refunds/request")
def create_refund(
    request: RefundRequest,
    db: Session = Depends(get_db),
):
    try:
        intent = request_refund(
            db=db,
            payment_id=request.payment_id,
            amount_paise=request.amount_paise,
        )

        return {
            "refund_intent_id": intent.id,
            "payment_id": intent.payment_id,
            "amount_paise": intent.amount_paise,
            "status": intent.status,
            "decision": intent.decision,
            "reason": intent.reason,
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# =========================================================
# 2. EXECUTE APPROVED REFUND
# =========================================================

@app.post("/api/refunds/{refund_intent_id}/execute")
def execute_refund_endpoint(
    refund_intent_id: str,
    db: Session = Depends(get_db),
):
    intent = (
        db.query(RefundIntent)
        .filter(RefundIntent.id == refund_intent_id)
        .first()
    )

    if not intent:
        raise HTTPException(
            status_code=404,
            detail="Refund intent not found",
        )

    try:
        refund = execute_refund(
            db=db,
            intent=intent,
        )

        return {
            "refund_id": refund.id,
            "refund_intent_id": refund.refund_intent_id,
            "payment_id": refund.payment_id,
            "amount_paise": refund.amount_paise,
            "status": refund.status,
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# =========================================================
# 3. GET PAYMENT STATE (control plane)
# =========================================================

@app.get("/api/state/{payment_id}")
def get_payment_state(
    payment_id: str,
    db: Session = Depends(get_db),
):
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .first()
    )

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    disputes = (
        db.query(Dispute)
        .filter(Dispute.payment_id == payment_id)
        .order_by(Dispute.created_at.desc())
        .all()
    )

    pre_alerts = (
        db.query(PreAlert)
        .filter(PreAlert.payment_id == payment_id)
        .order_by(PreAlert.received_at.desc())
        .all()
    )

    refunds = (
        db.query(Refund)
        .filter(Refund.payment_id == payment_id)
        .order_by(Refund.created_at.desc())
        .all()
    )

    refund_intents = (
        db.query(RefundIntent)
        .filter(RefundIntent.payment_id == payment_id)
        .order_by(RefundIntent.created_at.desc())
        .all()
    )

    ledger_events = (
        db.query(LedgerEvent)
        .filter(LedgerEvent.payment_id == payment_id)
        .order_by(LedgerEvent.sequence.asc())
        .all()
    )

    defense_packages = (
        db.query(DefensePackage)
        .filter(DefensePackage.payment_id == payment_id)
        .all()
    )

    support_messages = (
        db.query(SupportMessage)
        .filter(SupportMessage.payment_id == payment_id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )

    active_dispute = next(
        (d for d in disputes if d.status == "OPEN"), None
    )
    active_pre_alert = next(
        (p for p in pre_alerts if p.status == "OPEN"), None
    )

    total_refunded = sum(
        r.amount_paise for r in refunds
        if r.status in ("PENDING", "PROCESSED")
    )
    remaining_refundable = payment.amount_paise - total_refunded

    latest_intent = refund_intents[0] if refund_intents else None

    # Build event timeline
    timeline = []
    for le in ledger_events:
        timeline.append({
            "sequence": le.sequence,
            "event_type": le.event_type,
            "amount_paise": le.amount_paise,
            "reference_id": le.reference_id,
            "created_at": le.created_at.isoformat(),
        })

    # Defense package details
    dp_list = []
    for dp in defense_packages:
        evidence_items = (
            db.query(EvidenceItem)
            .filter(EvidenceItem.defense_package_id == dp.id)
            .all()
        )
        dp_list.append({
            "id": dp.id,
            "dispute_id": dp.dispute_id,
            "disputed_amount_paise": dp.disputed_amount_paise,
            "contestable_amount_paise": dp.contestable_amount_paise,
            "uncovered_amount_paise": dp.uncovered_amount_paise,
            "summary": dp.summary,
            "status": dp.status,
            "created_at": dp.created_at.isoformat(),
            "evidence_count": len(evidence_items),
            "evidence_items": [
                {
                    "id": ev.id,
                    "evidence_type": ev.evidence_type,
                    "source_type": ev.source_type,
                    "description": ev.description,
                    "document_reference": ev.document_reference,
                }
                for ev in evidence_items
            ],
        })

    return {
        "payment": {
            "id": payment.id,
            "merchant_id": payment.merchant_id,
            "amount_paise": payment.amount_paise,
            "currency": payment.currency,
            "status": payment.status,
            "created_at": payment.created_at.isoformat(),
        },
        "risk_state": {
            "has_active_dispute": active_dispute is not None,
            "has_active_pre_alert": active_pre_alert is not None,
            "would_block_refund": (
                active_dispute is not None or active_pre_alert is not None
            ),
            "block_reason": (
                "Active dispute detected — refund would cause duplicate financial outflow"
                if active_dispute
                else (
                    "Active pre-dispute network alert — refund blocked pending review"
                    if active_pre_alert
                    else None
                )
            ),
        },
        "refund_summary": {
            "total_refunded_paise": total_refunded,
            "remaining_refundable_paise": remaining_refundable,
            "refund_count": len(refunds),
        },
        "disputes": [
            {
                "id": d.id,
                "amount_paise": d.amount_paise,
                "phase": d.phase,
                "status": d.status,
                "reason_code": d.reason_code,
                "created_at": d.created_at.isoformat(),
            }
            for d in disputes
        ],
        "pre_alerts": [
            {
                "id": p.id,
                "provider": p.provider,
                "alert_type": p.alert_type,
                "status": p.status,
                "received_at": p.received_at.isoformat(),
            }
            for p in pre_alerts
        ],
        "refunds": [
            {
                "id": r.id,
                "amount_paise": r.amount_paise,
                "status": r.status,
                "arn": r.arn,
                "created_at": r.created_at.isoformat(),
                "processed_at": r.processed_at.isoformat() if r.processed_at else None,
            }
            for r in refunds
        ],
        "latest_intent": {
            "id": latest_intent.id,
            "amount_paise": latest_intent.amount_paise,
            "status": latest_intent.status,
            "decision": latest_intent.decision,
            "reason": latest_intent.reason,
            "created_at": latest_intent.created_at.isoformat(),
        } if latest_intent else None,
        "support_messages": [
            {
                "id": m.id,
                "channel": m.channel,
                "sender": m.sender,
                "message_text": m.message_text,
                "created_at": m.created_at.isoformat(),
            }
            for m in support_messages
        ],
        "defense_packages": dp_list,
        "event_timeline": timeline,
    }


# =========================================================
# 4. GET DEFENSE PACKAGE
# =========================================================

@app.get("/api/defense/{dispute_id}")
def get_defense_package(
    dispute_id: str,
    db: Session = Depends(get_db),
):
    dp = (
        db.query(DefensePackage)
        .filter(DefensePackage.dispute_id == dispute_id)
        .first()
    )

    if not dp:
        raise HTTPException(
            status_code=404,
            detail="Defense package not found for this dispute",
        )

    evidence_items = (
        db.query(EvidenceItem)
        .filter(EvidenceItem.defense_package_id == dp.id)
        .all()
    )

    return {
        "defense_package": {
            "id": dp.id,
            "dispute_id": dp.dispute_id,
            "payment_id": dp.payment_id,
            "disputed_amount_paise": dp.disputed_amount_paise,
            "contestable_amount_paise": dp.contestable_amount_paise,
            "uncovered_amount_paise": dp.uncovered_amount_paise,
            "summary": dp.summary,
            "status": dp.status,
            "created_at": dp.created_at.isoformat(),
        },
        "evidence_items": [
            {
                "id": ev.id,
                "evidence_type": ev.evidence_type,
                "source_type": ev.source_type,
                "source_id": ev.source_id,
                "description": ev.description,
                "document_reference": ev.document_reference,
            }
            for ev in evidence_items
        ],
        "contest_payload": {
            "dispute_id": dispute_id,
            "action": "contest",
            "contest_amount": dp.contestable_amount_paise,
            "evidence_types": list(set(ev.evidence_type for ev in evidence_items)),
            "notes": dp.summary,
        },
    }


# =========================================================
# 5. METRICS (FinOps Dashboard)
# =========================================================

@app.get("/api/metrics")
def get_metrics(db: Session = Depends(get_db)):
    total_intents = db.query(RefundIntent).count()
    blocked_intents = (
        db.query(RefundIntent)
        .filter(RefundIntent.status == "BLOCKED")
        .count()
    )
    safe_refunds = (
        db.query(Refund)
        .filter(Refund.status == "PROCESSED")
        .count()
    )
    disputes_total = db.query(Dispute).count()
    defense_packages_total = db.query(DefensePackage).count()

    # Blocked amounts — sum of all blocked refund intent amounts
    blocked_amounts = (
        db.query(RefundIntent)
        .filter(RefundIntent.status == "BLOCKED")
        .all()
    )
    total_blocked_paise = sum(i.amount_paise for i in blocked_amounts)

    # Defense package coverage
    defense_packages = db.query(DefensePackage).all()
    total_contestable = sum(dp.contestable_amount_paise for dp in defense_packages)
    total_uncovered = sum(dp.uncovered_amount_paise for dp in defense_packages)
    total_disputed = sum(dp.disputed_amount_paise for dp in defense_packages)

    # Evidence completeness (packages that have at least one refund evidence item)
    packages_with_evidence = 0
    for dp in defense_packages:
        ev_count = (
            db.query(EvidenceItem)
            .filter(EvidenceItem.defense_package_id == dp.id)
            .count()
        )
        if ev_count > 0:
            packages_with_evidence += 1

    evidence_completeness = (
        round(packages_with_evidence / defense_packages_total * 100)
        if defense_packages_total > 0 else 0
    )

    return {
        "refund_requests_intercepted": total_intents,
        "dangerous_refunds_blocked": blocked_intents,
        "duplicate_outflow_prevented_paise": total_blocked_paise,
        "safe_refunds_executed": safe_refunds,
        "disputes_detected": disputes_total,
        "defense_packages_generated": defense_packages_total,
        "refund_supported_dispute_amount_paise": total_contestable,
        "uncovered_dispute_exposure_paise": total_uncovered,
        "evidence_completeness_pct": evidence_completeness,
        "note": (
            "Eligible synthetic defense packages correctly assembled: "
            f"{evidence_completeness}%"
        ),
    }


# =========================================================
# 6. RAZORPAY REFUND PROCESSED WEBHOOK
# =========================================================

@app.post("/webhooks/razorpay")
async def razorpay_webhook(
    webhook: RazorpayWebhook,
    db: Session = Depends(get_db),
    event_id: str | None = Header(
        default=None,
        alias="x-razorpay-event-id",
    ),
):
    event_type = webhook.event

    if event_type != "refund.processed":
        return {
            "status": "ignored",
            "event": event_type,
        }

    if not event_id:
        raise HTTPException(
            status_code=400,
            detail="Missing x-razorpay-event-id header",
        )

    # ---- Deduplication: check provider_event table ----
    existing_event = (
        db.query(ProviderEvent)
        .filter(ProviderEvent.provider_event_id == event_id)
        .first()
    )

    if existing_event:
        return {
            "status": "duplicate_event_ignored",
            "event_id": event_id,
        }

    refund_entity = webhook.payload.refund.entity
    razorpay_refund_id = refund_entity.id
    payment_id = refund_entity.payment_id
    amount_paise = refund_entity.amount

    arn = None
    if refund_entity.acquirer_data:
        arn = refund_entity.acquirer_data.arn

    # ---- Store raw provider event FIRST ----
    provider_event = ProviderEvent(
        id=str(uuid.uuid4()),
        provider="RAZORPAY",
        provider_event_id=event_id,
        event_type=event_type,
        entity_id=razorpay_refund_id,
        payload=webhook.model_dump(),
    )
    db.add(provider_event)

    # ---- Find our refund ----
    refund = (
        db.query(Refund)
        .filter(Refund.id == razorpay_refund_id)
        .first()
    )

    if not refund:
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail="Refund not found",
        )

    # ---- Idempotency at financial-state level ----
    if refund.status == "PROCESSED":
        provider_event.processed_at = datetime.utcnow()
        db.commit()
        return {
            "status": "already_processed",
            "refund_id": refund.id,
            "event_id": event_id,
        }

    # ---- Update refund ----
    refund.status = "PROCESSED"
    refund.processed_at = datetime.utcnow()

    if arn:
        refund.arn = arn

    # ---- Create immutable ledger event ----
    ledger_event = LedgerEvent(
        payment_id=payment_id,
        event_type="REFUND_PROCESSED",
        amount_paise=amount_paise,
        reference_id=razorpay_refund_id,
        event_metadata={
            "provider": "RAZORPAY",
            "event_id": event_id,
            "arn": arn,
        },
        previous_hash=None,
        event_hash=f"sha256-{event_id}-{razorpay_refund_id}",
    )
    db.add(ledger_event)

    provider_event.processed_at = datetime.utcnow()
    db.commit()

    return {
        "status": "processed",
        "event_id": event_id,
        "refund_id": refund.id,
        "payment_id": refund.payment_id,
        "amount_paise": amount_paise,
        "arn": refund.arn,
        "ledger_event": "REFUND_PROCESSED",
    }


# =========================================================
# 7. DISPUTE CREATED WEBHOOK
# =========================================================

@app.post("/webhooks/razorpay/dispute")
async def razorpay_dispute_webhook(
    webhook: RazorpayDisputeWebhook,
    db: Session = Depends(get_db),
    event_id: str | None = Header(
        default=None,
        alias="x-razorpay-event-id",
    ),
):
    if webhook.event != "payment.dispute.created":
        return {
            "status": "ignored",
            "event": webhook.event,
        }

    dispute_entity = webhook.payload.dispute.entity
    payment_entity = webhook.payload.payment.entity

    payment_id = payment_entity.id
    dispute_id = dispute_entity.id

    # ---- Deduplication via provider_event ----
    evt_key = event_id or f"dispute-{dispute_id}"
    existing_event = (
        db.query(ProviderEvent)
        .filter(ProviderEvent.provider_event_id == evt_key)
        .first()
    )
    if existing_event:
        return {
            "status": "duplicate_event_ignored",
            "dispute_id": dispute_id,
        }

    # ---- Store provider event ----
    provider_event = ProviderEvent(
        id=str(uuid.uuid4()),
        provider="RAZORPAY",
        provider_event_id=evt_key,
        event_type=webhook.event,
        entity_id=dispute_id,
        payload=webhook.model_dump(),
    )
    db.add(provider_event)

    # ---- Check that payment exists ----
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .first()
    )

    if not payment:
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail="Payment not found",
        )

    # ---- Store the dispute (idempotent) ----
    existing_dispute = (
        db.query(Dispute)
        .filter(Dispute.id == dispute_id)
        .first()
    )

    if existing_dispute:
        provider_event.processed_at = datetime.utcnow()
        db.commit()
        return {
            "status": "already_processed",
            "dispute_id": dispute_id,
            "payment_id": payment_id,
        }

    dispute = Dispute(
        id=dispute_id,
        payment_id=payment_id,
        amount_paise=dispute_entity.amount,
        phase=dispute_entity.phase,
        status=dispute_entity.status.upper(),
        reason_code=dispute_entity.reason_code,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(dispute)
    db.flush()

    # ---- Build defense package ----
    result = build_defense_package(
        db=db,
        dispute_id=dispute_id,
        payment_id=payment_id,
        dispute_amount_paise=dispute_entity.amount,
    )

    provider_event.processed_at = datetime.utcnow()
    db.commit()

    return {
        "status": "processed",
        "dispute_id": dispute_id,
        "payment_id": payment_id,
        "dispute_amount_paise": dispute_entity.amount,
        "refunds_found": result["refunds_found"],
        "total_refunded_paise": result["total_refunded_paise"],
        "contestable_amount_paise": result["contestable_amount_paise"],
        "uncovered_amount_paise": result["uncovered_amount_paise"],
        "defense_package_id": result["defense_package_id"],
        "defense_status": result["defense_status"],
        "missing_evidence": result["missing_evidence"],
    }


# =========================================================
# 8. SCENARIO ENGINE
# =========================================================

@app.post("/api/scenarios/reset")
def reset_scenarios(db: Session = Depends(get_db)):
    """
    Wipe all scenario data and reload clean demo payments.
    NEVER touches .env or secrets.
    """
    # Delete in reverse dependency order
    db.query(EvidenceItem).delete()
    db.query(DefensePackage).delete()
    db.query(SupportMessage).delete()
    db.query(OutboxEvent).delete()
    db.query(LedgerEvent).delete()
    db.query(ProviderEvent).delete()
    db.query(Refund).delete()
    db.query(RefundIntent).delete()
    db.query(PreAlert).delete()
    db.query(Dispute).delete()
    db.query(Payment).delete()
    db.commit()

    # Re-seed base payments
    _seed_base_payments(db)

    return {
        "status": "reset_complete",
        "message": "All scenario data wiped. Base payments re-seeded.",
    }


@app.post("/api/scenarios/load/{scenario_name}")
def load_scenario(
    scenario_name: str,
    db: Session = Depends(get_db),
):
    """
    Load a named scenario. Call /api/scenarios/reset first for a clean state.
    """
    name = scenario_name.upper()
    loaders = {
        "SAFE_REFUND": _load_safe_refund,
        "ACTIVE_DISPUTE": _load_active_dispute,
        "PRE_ALERT": _load_pre_alert,
        "PARTIAL_REFUND_THEN_CHARGEBACK": _load_partial_refund_then_chargeback,
        "REFUND_THEN_CHARGEBACK": _load_refund_then_chargeback,
        "WEBHOOK_FAILURE": _load_webhook_failure,
        "DUPLICATE_WEBHOOK": _load_duplicate_webhook,
        "OUT_OF_ORDER_WEBHOOK": _load_out_of_order_webhook,
    }

    if name not in loaders:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{name}'. Available: {list(loaders.keys())}",
        )

    return loaders[name](db)


@app.get("/api/scenarios")
def list_scenarios():
    return {
        "scenarios": [
            {
                "name": "SAFE_REFUND",
                "description": "Payment with no dispute/pre-alert — refund approved and processed",
                "payment_id": "scen_safe_001",
            },
            {
                "name": "ACTIVE_DISPUTE",
                "description": "Payment has active dispute — refund blocked",
                "payment_id": "scen_dispute_001",
            },
            {
                "name": "PRE_ALERT",
                "description": "Payment has open simulated network pre-alert — refund blocked",
                "payment_id": "scen_alert_001",
            },
            {
                "name": "PARTIAL_REFUND_THEN_CHARGEBACK",
                "description": "₹10,000 payment, ₹4k+₹2k partial refunds, then full dispute. Contestable=₹6k, Uncovered=₹4k",
                "payment_id": "scen_partial_001",
            },
            {
                "name": "REFUND_THEN_CHARGEBACK",
                "description": "Full refund processed with ARN, then dispute arrives — defense package auto-built",
                "payment_id": "scen_rtc_001",
            },
            {
                "name": "WEBHOOK_FAILURE",
                "description": "Network timeout scenario — retry uses same idempotency key → one refund",
                "payment_id": "scen_wf_001",
            },
            {
                "name": "DUPLICATE_WEBHOOK",
                "description": "Same refund.processed webhook arrives twice — exactly one financial effect",
                "payment_id": "scen_dup_001",
            },
            {
                "name": "OUT_OF_ORDER_WEBHOOK",
                "description": "Out-of-order webhook — stale event cannot regress a newer state",
                "payment_id": "scen_ooo_001",
            },
        ]
    }


# =========================================================
# SCENARIO LOADERS (internal helpers)
# =========================================================

def _seed_base_payments(db: Session):
    for payment in [
        Payment(
            id="pay_demo_001",
            merchant_id="merchant_demo",
            amount_paise=1_000_000,
            currency="INR",
            status="CAPTURED",
        ),
        Payment(
            id="pay_demo_002",
            merchant_id="merchant_demo",
            amount_paise=500_000,
            currency="INR",
            status="CAPTURED",
        ),
    ]:
        db.merge(payment)
    db.commit()


def _load_safe_refund(db: Session) -> dict:
    """Scenario A: Payment → approved refund → processed."""
    pay_id = "scen_safe_001"

    _upsert_payment(db, pay_id, 750_000)

    # Create refund intent (approved)
    intent_id = "ri_safe_001"
    intent = RefundIntent(
        id=intent_id,
        payment_id=pay_id,
        amount_paise=750_000,
        status="APPROVED",
        decision="ALLOW",
        reason="No active dispute or pre-alert detected.",
        idempotency_key=f"idem-{intent_id}",
    )
    db.merge(intent)

    # Create processed refund
    refund_id = "rfnd_safe_001"
    refund = Refund(
        id=refund_id,
        payment_id=pay_id,
        refund_intent_id=intent_id,
        amount_paise=750_000,
        status="PROCESSED",
        idempotency_key=f"idem-{intent_id}",
        arn="ARN123456789SAFE",
        processed_at=datetime.utcnow(),
    )
    db.merge(refund)

    # Ledger event
    _append_ledger(db, pay_id, "REFUND_PROCESSED", 750_000, refund_id, {
        "arn": "ARN123456789SAFE",
        "scenario": "SAFE_REFUND",
    })

    # Support message
    _upsert_support_message(
        db, "msg_safe_001", pay_id,
        "customer",
        "Hi, I need a refund for my order. I haven't received it.",
    )

    db.commit()
    return {
        "scenario": "SAFE_REFUND",
        "payment_id": pay_id,
        "payment_amount_paise": 750_000,
        "refund_status": "PROCESSED",
        "arn": "ARN123456789SAFE",
        "message": "Safe refund scenario loaded. Refund is APPROVED and PROCESSED.",
    }


def _load_active_dispute(db: Session) -> dict:
    """Scenario B: Payment with active dispute → refund blocked."""
    pay_id = "scen_dispute_001"
    _upsert_payment(db, pay_id, 500_000)

    # Active dispute
    dispute = Dispute(
        id="disp_scen_001",
        payment_id=pay_id,
        amount_paise=500_000,
        phase="chargeback",
        status="OPEN",
        reason_code="chargeback",
    )
    db.merge(dispute)
    db.commit()

    return {
        "scenario": "ACTIVE_DISPUTE",
        "payment_id": pay_id,
        "payment_amount_paise": 500_000,
        "dispute_id": "disp_scen_001",
        "message": (
            "Active dispute scenario loaded. "
            "POST /api/refunds/request with payment_id='scen_dispute_001' "
            "to see the refund blocked."
        ),
    }


def _load_pre_alert(db: Session) -> dict:
    """Scenario C: Payment with open simulated network pre-alert → refund blocked."""
    pay_id = "scen_alert_001"
    _upsert_payment(db, pay_id, 300_000)

    alert = PreAlert(
        id="alert_scen_001",
        payment_id=pay_id,
        provider="SIMULATED_NETWORK_FEED",
        alert_type="pre_dispute_alert",
        status="OPEN",
    )
    db.merge(alert)
    db.commit()

    return {
        "scenario": "PRE_ALERT",
        "payment_id": pay_id,
        "payment_amount_paise": 300_000,
        "alert_id": "alert_scen_001",
        "alert_note": "This is a simulated Visa/Mastercard network pre-alert feed. Not live Verifi/Ethoca integration.",
        "message": (
            "Pre-alert scenario loaded. "
            "POST /api/refunds/request with payment_id='scen_alert_001' "
            "to see the refund blocked."
        ),
    }


def _load_partial_refund_then_chargeback(db: Session) -> dict:
    """Scenario D: ₹10,000 payment, ₹4k+₹2k refunds, full dispute. Contestable=₹6k, Uncovered=₹4k."""
    pay_id = "scen_partial_001"
    _upsert_payment(db, pay_id, 1_000_000)

    # Two partial refunds (already processed)
    r1_id = "rfnd_partial_001_a"
    r2_id = "rfnd_partial_001_b"

    r1 = Refund(
        id=r1_id,
        payment_id=pay_id,
        amount_paise=400_000,
        status="PROCESSED",
        idempotency_key=f"idem-{r1_id}",
        arn="ARN_PARTIAL_001A",
        processed_at=datetime.utcnow(),
    )
    r2 = Refund(
        id=r2_id,
        payment_id=pay_id,
        amount_paise=200_000,
        status="PROCESSED",
        idempotency_key=f"idem-{r2_id}",
        arn="ARN_PARTIAL_001B",
        processed_at=datetime.utcnow(),
    )
    db.merge(r1)
    db.merge(r2)

    _append_ledger(db, pay_id, "REFUND_PROCESSED", 400_000, r1_id, {"arn": "ARN_PARTIAL_001A"})
    _append_ledger(db, pay_id, "REFUND_PROCESSED", 200_000, r2_id, {"arn": "ARN_PARTIAL_001B"})

    # Support message
    _upsert_support_message(
        db, "msg_partial_001", pay_id,
        "customer",
        "I requested a partial refund for items not delivered. Please confirm.",
    )

    # Full dispute for ₹10,000
    dispute_id = "disp_partial_001"
    dispute = Dispute(
        id=dispute_id,
        payment_id=pay_id,
        amount_paise=1_000_000,
        phase="chargeback",
        status="OPEN",
        reason_code="goods_not_received",
    )
    db.merge(dispute)
    db.flush()

    # Build defense package
    build_defense_package(
        db=db,
        dispute_id=dispute_id,
        payment_id=pay_id,
        dispute_amount_paise=1_000_000,
    )

    db.commit()

    return {
        "scenario": "PARTIAL_REFUND_THEN_CHARGEBACK",
        "payment_id": pay_id,
        "payment_amount_paise": 1_000_000,
        "refund_1_paise": 400_000,
        "refund_2_paise": 200_000,
        "total_refunded_paise": 600_000,
        "dispute_amount_paise": 1_000_000,
        "contestable_amount_paise": 600_000,
        "uncovered_amount_paise": 400_000,
        "message": "Partial refund + chargeback scenario loaded. GET /api/defense/disp_partial_001",
    }


def _load_refund_then_chargeback(db: Session) -> dict:
    """Scenario E: Full refund with ARN + support msg, then dispute → defense package."""
    pay_id = "scen_rtc_001"
    _upsert_payment(db, pay_id, 800_000)

    refund_id = "rfnd_rtc_001"
    refund = Refund(
        id=refund_id,
        payment_id=pay_id,
        amount_paise=800_000,
        status="PROCESSED",
        idempotency_key=f"idem-{refund_id}",
        arn="ARN987654321RTC",
        processed_at=datetime.utcnow(),
    )
    db.merge(refund)

    _append_ledger(db, pay_id, "REFUND_PROCESSED", 800_000, refund_id, {
        "arn": "ARN987654321RTC",
        "scenario": "REFUND_THEN_CHARGEBACK",
    })

    _upsert_support_message(
        db, "msg_rtc_001", pay_id,
        "customer",
        "I want to return the product. I was promised a full refund.",
    )
    _upsert_support_message(
        db, "msg_rtc_002", pay_id,
        "agent",
        "We have processed a full refund of ₹8,000. ARN: ARN987654321RTC. Please allow 3-5 business days.",
    )

    # Dispute arrives later
    dispute_id = "disp_rtc_001"
    dispute = Dispute(
        id=dispute_id,
        payment_id=pay_id,
        amount_paise=800_000,
        phase="chargeback",
        status="OPEN",
        reason_code="goods_not_received",
    )
    db.merge(dispute)
    db.flush()

    build_defense_package(
        db=db,
        dispute_id=dispute_id,
        payment_id=pay_id,
        dispute_amount_paise=800_000,
    )

    db.commit()

    return {
        "scenario": "REFUND_THEN_CHARGEBACK",
        "payment_id": pay_id,
        "payment_amount_paise": 800_000,
        "refund_id": refund_id,
        "arn": "ARN987654321RTC",
        "dispute_id": dispute_id,
        "message": "Refund-then-chargeback scenario loaded. GET /api/defense/disp_rtc_001",
    }


def _load_webhook_failure(db: Session) -> dict:
    """
    Scenario F: Simulates network timeout — retry with same idempotency key.
    Creates a PENDING refund. A retry would use the same idempotency key → safe.
    """
    pay_id = "scen_wf_001"
    _upsert_payment(db, pay_id, 600_000)

    intent_id = "ri_wf_001"
    intent = RefundIntent(
        id=intent_id,
        payment_id=pay_id,
        amount_paise=600_000,
        status="PENDING",
        decision="ALLOW",
        reason="Refund approved — execution pending (simulated timeout scenario).",
        idempotency_key=f"idem-{intent_id}",
    )
    db.merge(intent)

    refund_id = "rfnd_wf_001"
    refund = Refund(
        id=refund_id,
        payment_id=pay_id,
        refund_intent_id=intent_id,
        amount_paise=600_000,
        status="PENDING",
        idempotency_key=f"idem-{intent_id}",
        arn=None,
    )
    db.merge(refund)
    db.commit()

    return {
        "scenario": "WEBHOOK_FAILURE",
        "payment_id": pay_id,
        "payment_amount_paise": 600_000,
        "refund_id": refund_id,
        "refund_status": "PENDING",
        "idempotency_key": f"idem-{intent_id}",
        "message": (
            "Network timeout scenario loaded. Refund is PENDING. "
            "Send refund.processed webhook with refund_id='rfnd_wf_001' twice "
            "using x-razorpay-event-id='evt_wf_001' — second delivery is idempotent."
        ),
    }


def _load_duplicate_webhook(db: Session) -> dict:
    """Scenario G: Same event arrives twice — one financial effect."""
    pay_id = "scen_dup_001"
    _upsert_payment(db, pay_id, 400_000)

    intent_id = "ri_dup_001"
    intent = RefundIntent(
        id=intent_id,
        payment_id=pay_id,
        amount_paise=400_000,
        status="PENDING",
        decision="ALLOW",
        reason="No active dispute or pre-alert detected.",
        idempotency_key=f"idem-{intent_id}",
    )
    db.merge(intent)

    refund_id = "rfnd_dup_001"
    refund = Refund(
        id=refund_id,
        payment_id=pay_id,
        refund_intent_id=intent_id,
        amount_paise=400_000,
        status="PENDING",
        idempotency_key=f"idem-{intent_id}",
        arn=None,
    )
    db.merge(refund)
    db.commit()

    return {
        "scenario": "DUPLICATE_WEBHOOK",
        "payment_id": pay_id,
        "refund_id": refund_id,
        "message": (
            "Duplicate webhook scenario loaded. "
            "Send refund.processed twice with event_id='evt_dup_001'. "
            "Second delivery returns duplicate_event_ignored — zero extra ledger events."
        ),
    }


def _load_out_of_order_webhook(db: Session) -> dict:
    """Scenario H: Out-of-order webhook — stale event cannot regress state."""
    pay_id = "scen_ooo_001"
    _upsert_payment(db, pay_id, 500_000)

    intent_id = "ri_ooo_001"
    intent = RefundIntent(
        id=intent_id,
        payment_id=pay_id,
        amount_paise=500_000,
        status="PENDING",
        decision="ALLOW",
        reason="No active dispute or pre-alert detected.",
        idempotency_key=f"idem-{intent_id}",
    )
    db.merge(intent)

    refund_id = "rfnd_ooo_001"
    refund = Refund(
        id=refund_id,
        payment_id=pay_id,
        refund_intent_id=intent_id,
        amount_paise=500_000,
        status="PROCESSED",
        idempotency_key=f"idem-{intent_id}",
        arn="ARN_OOO_001",
        processed_at=datetime.utcnow(),
    )
    db.merge(refund)

    _append_ledger(db, pay_id, "REFUND_PROCESSED", 500_000, refund_id, {
        "arn": "ARN_OOO_001",
        "scenario": "OUT_OF_ORDER_WEBHOOK",
    })

    # Pre-store the event so duplicate delivery of the same event is rejected
    evt = ProviderEvent(
        id=str(uuid.uuid4()),
        provider="RAZORPAY",
        provider_event_id="evt_ooo_processed",
        event_type="refund.processed",
        entity_id=refund_id,
        payload={"scenario": "out_of_order"},
        processed_at=datetime.utcnow(),
    )
    db.merge(evt)
    db.commit()

    return {
        "scenario": "OUT_OF_ORDER_WEBHOOK",
        "payment_id": pay_id,
        "refund_id": refund_id,
        "refund_status": "PROCESSED",
        "message": (
            "Out-of-order scenario loaded. Refund is ALREADY PROCESSED. "
            "Sending a late/stale refund.processed webhook (evt_ooo_stale) will be idempotent — "
            "system returns already_processed without creating new ledger events."
        ),
    }


# =========================================================
# HELPERS
# =========================================================

def _upsert_payment(db: Session, payment_id: str, amount_paise: int):
    payment = Payment(
        id=payment_id,
        merchant_id="merchant_demo",
        amount_paise=amount_paise,
        currency="INR",
        status="CAPTURED",
    )
    db.merge(payment)
    db.flush()


def _append_ledger(
    db: Session,
    payment_id: str,
    event_type: str,
    amount_paise: int,
    reference_id: str,
    meta: dict,
):
    ref = str(uuid.uuid4())[:8]
    ledger = LedgerEvent(
        payment_id=payment_id,
        event_type=event_type,
        amount_paise=amount_paise,
        reference_id=reference_id,
        event_metadata=meta,
        previous_hash=None,
        event_hash=f"sha256-{reference_id}-{ref}",
    )
    db.add(ledger)
    db.flush()


def _upsert_support_message(
    db: Session,
    msg_id: str,
    payment_id: str,
    sender: str,
    text: str,
):
    msg = SupportMessage(
        id=msg_id,
        payment_id=payment_id,
        channel="email",
        sender=sender,
        message_text=text,
    )
    db.merge(msg)
    db.flush()