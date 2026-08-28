"""
Integration tests for Dispute Shield.

Tests are run against the real database with real FastAPI routes.
Uses TestClient to avoid needing a running server.

Each test resets to a clean scenario via /api/scenarios/reset.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import SessionLocal
from app.db.models import (
    Payment, Dispute, PreAlert, Refund, RefundIntent,
    LedgerEvent, ProviderEvent, EvidenceItem, DefensePackage, SupportMessage, OutboxEvent,
)
from app.providers.razorpay_mock import clear_idempotency_store

client = TestClient(app)


def clean_db():
    """Wipe all scenario data for a fresh test."""
    db = SessionLocal()
    try:
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
    finally:
        db.close()
    clear_idempotency_store()


@pytest.fixture(autouse=True)
def reset_before_each():
    clean_db()
    yield


# =========================================================
# SCENARIO A: SAFE REFUND
# =========================================================

def test_safe_refund_flow():
    """A payment with no dispute/pre-alert should produce APPROVED refund intent."""
    # Load scenario
    resp = client.post("/api/scenarios/load/SAFE_REFUND")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["scenario"] == "SAFE_REFUND"
    assert data["refund_status"] == "PROCESSED"
    assert data["arn"] is not None

    # State check
    state = client.get("/api/state/scen_safe_001").json()
    assert state["risk_state"]["has_active_dispute"] is False
    assert state["risk_state"]["has_active_pre_alert"] is False
    assert state["risk_state"]["would_block_refund"] is False
    assert len(state["refunds"]) == 1
    assert state["refunds"][0]["status"] == "PROCESSED"


def test_safe_refund_request_approved():
    """Requesting a refund on a payment with no dispute should be APPROVED."""
    db = SessionLocal()
    try:
        db.add(Payment(
            id="test_safe_pay",
            merchant_id="m1",
            amount_paise=500_000,
            currency="INR",
            status="CAPTURED",
        ))
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/refunds/request", json={
        "payment_id": "test_safe_pay",
        "amount_paise": 500_000,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "APPROVED"
    assert data["decision"] == "ALLOW"


# =========================================================
# SCENARIO B: ACTIVE DISPUTE → REFUND BLOCKED
# =========================================================

def test_active_dispute_blocks_refund():
    """A payment with an active OPEN dispute must block any refund."""
    resp = client.post("/api/scenarios/load/ACTIVE_DISPUTE")
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenario"] == "ACTIVE_DISPUTE"

    refund_resp = client.post("/api/refunds/request", json={
        "payment_id": "scen_dispute_001",
        "amount_paise": 100_000,
    })
    assert refund_resp.status_code == 200
    refund_data = refund_resp.json()
    assert refund_data["status"] == "BLOCKED"
    assert refund_data["decision"] == "BLOCK_DISPUTE"
    assert "dispute" in refund_data["reason"].lower()

    # State confirms block reason
    state = client.get("/api/state/scen_dispute_001").json()
    assert state["risk_state"]["has_active_dispute"] is True
    assert state["risk_state"]["would_block_refund"] is True


# =========================================================
# SCENARIO C: PRE-ALERT → REFUND BLOCKED
# =========================================================

def test_prealert_blocks_refund():
    """A payment with an open simulated network pre-alert must block refund."""
    resp = client.post("/api/scenarios/load/PRE_ALERT")
    assert resp.status_code == 200

    refund_resp = client.post("/api/refunds/request", json={
        "payment_id": "scen_alert_001",
        "amount_paise": 100_000,
    })
    assert refund_resp.status_code == 200
    refund_data = refund_resp.json()
    assert refund_data["status"] == "BLOCKED"
    assert refund_data["decision"] == "BLOCK_PRE_ALERT"

    state = client.get("/api/state/scen_alert_001").json()
    assert state["risk_state"]["has_active_pre_alert"] is True


# =========================================================
# SCENARIO D: PARTIAL REFUNDS THEN CHARGEBACK
# =========================================================

def test_partial_refund_then_chargeback():
    """₹10k payment, ₹4k+₹2k refunds, full dispute. Contestable=₹6k, Uncovered=₹4k."""
    resp = client.post("/api/scenarios/load/PARTIAL_REFUND_THEN_CHARGEBACK")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_refunded_paise"] == 600_000
    assert data["contestable_amount_paise"] == 600_000
    assert data["uncovered_amount_paise"] == 400_000

    # Defense package
    defense = client.get("/api/defense/disp_partial_001").json()
    dp = defense["defense_package"]
    assert dp["contestable_amount_paise"] == 600_000
    assert dp["uncovered_amount_paise"] == 400_000
    assert len(defense["evidence_items"]) >= 2  # 2 refunds + 1 support msg

    # Contest payload is correct
    assert defense["contest_payload"]["contest_amount"] == 600_000


# =========================================================
# SCENARIO E: REFUND THEN CHARGEBACK
# =========================================================

def test_refund_then_chargeback():
    """Full refund with ARN + support messages, then dispute → defense package built."""
    resp = client.post("/api/scenarios/load/REFUND_THEN_CHARGEBACK")
    assert resp.status_code == 200
    data = resp.json()
    assert data["arn"] == "ARN987654321RTC"

    defense = client.get("/api/defense/disp_rtc_001").json()
    dp = defense["defense_package"]
    assert dp["contestable_amount_paise"] == 800_000
    assert dp["uncovered_amount_paise"] == 0

    # Evidence should include refund confirmation + customer communication
    ev_types = set(ev["evidence_type"] for ev in defense["evidence_items"])
    assert "refund_confirmation" in ev_types
    assert "customer_communication" in ev_types

    # ARN in evidence
    refund_ev = [ev for ev in defense["evidence_items"] if ev["evidence_type"] == "refund_confirmation"]
    assert len(refund_ev) >= 1
    assert "ARN987654321RTC" in refund_ev[0]["description"]


# =========================================================
# SCENARIO F: WEBHOOK FAILURE / IDEMPOTENCY
# =========================================================

def test_webhook_idempotency():
    """Same refund.processed webhook arriving twice → exactly one financial effect."""
    resp = client.post("/api/scenarios/load/WEBHOOK_FAILURE")
    assert resp.status_code == 200
    data = resp.json()
    refund_id = data["refund_id"]

    webhook_payload = {
        "event": "refund.processed",
        "payload": {
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": "scen_wf_001",
                    "amount": 600_000,
                    "status": "processed",
                    "acquirer_data": {"arn": "ARN_WF_001_TEST"},
                }
            }
        }
    }

    # First delivery
    r1 = client.post(
        "/webhooks/razorpay",
        json=webhook_payload,
        headers={"x-razorpay-event-id": "evt_wf_test_001"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "processed"

    # Second delivery — same event_id
    r2 = client.post(
        "/webhooks/razorpay",
        json=webhook_payload,
        headers={"x-razorpay-event-id": "evt_wf_test_001"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate_event_ignored"

    # Check only one ledger event was created
    db = SessionLocal()
    try:
        ledger_count = (
            db.query(LedgerEvent)
            .filter(
                LedgerEvent.payment_id == "scen_wf_001",
                LedgerEvent.event_type == "REFUND_PROCESSED",
            )
            .count()
        )
        assert ledger_count == 1, f"Expected 1 ledger event, got {ledger_count}"
    finally:
        db.close()


# =========================================================
# SCENARIO G: DUPLICATE WEBHOOK
# =========================================================

def test_duplicate_webhook_one_financial_effect():
    """Duplicate webhook with same event_id → zero extra financial effects."""
    resp = client.post("/api/scenarios/load/DUPLICATE_WEBHOOK")
    assert resp.status_code == 200
    refund_id = resp.json()["refund_id"]

    webhook_payload = {
        "event": "refund.processed",
        "payload": {
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": "scen_dup_001",
                    "amount": 400_000,
                    "status": "processed",
                    "acquirer_data": {"arn": "ARN_DUP_001"},
                }
            }
        }
    }

    r1 = client.post(
        "/webhooks/razorpay",
        json=webhook_payload,
        headers={"x-razorpay-event-id": "evt_dup_001"},
    )
    assert r1.json()["status"] == "processed"

    r2 = client.post(
        "/webhooks/razorpay",
        json=webhook_payload,
        headers={"x-razorpay-event-id": "evt_dup_001"},
    )
    assert r2.json()["status"] == "duplicate_event_ignored"

    db = SessionLocal()
    try:
        count = (
            db.query(LedgerEvent)
            .filter(LedgerEvent.payment_id == "scen_dup_001")
            .count()
        )
        assert count == 1
    finally:
        db.close()


# =========================================================
# SCENARIO H: OUT-OF-ORDER WEBHOOK
# =========================================================

def test_out_of_order_webhook_does_not_regress_state():
    """Out-of-order stale webhook cannot regress a PROCESSED refund."""
    resp = client.post("/api/scenarios/load/OUT_OF_ORDER_WEBHOOK")
    assert resp.status_code == 200
    refund_id = resp.json()["refund_id"]
    assert resp.json()["refund_status"] == "PROCESSED"

    # Send a "stale" webhook with a NEW event ID — system sees already_processed
    stale_webhook = {
        "event": "refund.processed",
        "payload": {
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": "scen_ooo_001",
                    "amount": 500_000,
                    "status": "processed",
                    "acquirer_data": {"arn": "ARN_OOO_STALE"},
                }
            }
        }
    }

    r = client.post(
        "/webhooks/razorpay",
        json=stale_webhook,
        headers={"x-razorpay-event-id": "evt_ooo_stale"},
    )
    assert r.status_code == 200
    # Idempotency at financial-state level: already_processed
    assert r.json()["status"] == "already_processed"

    # Confirm refund is still PROCESSED, ARN unchanged
    db = SessionLocal()
    try:
        refund = db.query(Refund).filter(Refund.id == refund_id).first()
        assert refund.status == "PROCESSED"
        assert refund.arn == "ARN_OOO_001"  # original ARN preserved
    finally:
        db.close()


# =========================================================
# DUPLICATE REFUND REQUEST
# =========================================================

def test_duplicate_refund_request():
    """Requesting a refund for more than the remaining balance is rejected."""
    db = SessionLocal()
    try:
        db.add(Payment(
            id="test_dup_pay",
            merchant_id="m1",
            amount_paise=500_000,
            currency="INR",
            status="CAPTURED",
        ))
        db.commit()
    finally:
        db.close()

    # First refund for full amount
    r1 = client.post("/api/refunds/request", json={
        "payment_id": "test_dup_pay",
        "amount_paise": 500_000,
    })
    assert r1.status_code == 200
    assert r1.json()["status"] == "APPROVED"

    # Execute first refund
    intent_id = r1.json()["refund_intent_id"]
    exec_resp = client.post(f"/api/refunds/{intent_id}/execute")
    assert exec_resp.status_code == 200

    # Second refund — should fail: no remaining balance
    r2 = client.post("/api/refunds/request", json={
        "payment_id": "test_dup_pay",
        "amount_paise": 1,
    })
    assert r2.status_code == 400
    assert "remaining" in r2.json()["detail"].lower()


# =========================================================
# DEFENSE PACKAGE — MISSING EVIDENCE IDENTIFIED
# =========================================================

def test_defense_package_identifies_missing_evidence():
    """Defense package must explicitly note missing evidence types."""
    resp = client.post("/api/scenarios/load/ACTIVE_DISPUTE")
    assert resp.status_code == 200

    # Trigger a dispute for a payment with no refunds
    dispute_webhook = {
        "event": "payment.dispute.created",
        "payload": {
            "payment": {
                "entity": {
                    "id": "scen_dispute_001",
                    "amount": 500_000,
                    "currency": "INR",
                    "status": "captured",
                }
            },
            "dispute": {
                "entity": {
                    "id": "disp_scen_missing_ev",
                    "payment_id": "scen_dispute_001",
                    "amount": 500_000,
                    "status": "open",
                    "phase": "chargeback",
                    "reason_code": "chargeback",
                }
            }
        }
    }

    r = client.post(
        "/webhooks/razorpay/dispute",
        json=dispute_webhook,
        headers={"x-razorpay-event-id": "evt_missing_ev_001"},
    )
    assert r.status_code == 200
    data = r.json()
    # No refunds → not contestable, missing evidence noted
    assert data["refunds_found"] == 0
    assert data["contestable_amount_paise"] == 0
    assert data["uncovered_amount_paise"] == 500_000
    assert len(data["missing_evidence"]) > 0


# =========================================================
# METRICS
# =========================================================

def test_metrics_endpoint():
    """Metrics must return expected keys and sane values."""
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.json()

    required_keys = [
        "refund_requests_intercepted",
        "dangerous_refunds_blocked",
        "duplicate_outflow_prevented_paise",
        "safe_refunds_executed",
        "disputes_detected",
        "defense_packages_generated",
        "refund_supported_dispute_amount_paise",
        "uncovered_dispute_exposure_paise",
        "evidence_completeness_pct",
    ]
    for key in required_keys:
        assert key in data, f"Missing key: {key}"

    # All values must be integers or floats, not None
    for key in required_keys:
        assert data[key] is not None


# =========================================================
# SCENARIOS LIST
# =========================================================

def test_scenarios_list():
    resp = client.get("/api/scenarios")
    assert resp.status_code == 200
    data = resp.json()
    assert "scenarios" in data
    names = [s["name"] for s in data["scenarios"]]
    assert "SAFE_REFUND" in names
    assert "ACTIVE_DISPUTE" in names
    assert "PARTIAL_REFUND_THEN_CHARGEBACK" in names
