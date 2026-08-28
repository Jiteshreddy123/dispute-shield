import uuid

from sqlalchemy.orm import Session

from app.db.models import Payment, Refund, RefundIntent
from app.domain.risk_engine import (
    has_active_dispute,
    has_active_prealert,
)
from app.domain.states import (
    RefundStatus,
    RefundDecision,
)


def request_refund(
    db: Session,
    payment_id: str,
    amount_paise: int,
):
    # ---------------------------------------------------
    # 1. Find and lock the payment
    # ---------------------------------------------------

    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .with_for_update()
        .first()
    )

    if not payment:
        raise ValueError("Payment not found")

    # ---------------------------------------------------
    # 2. Validate payment status
    # ---------------------------------------------------

    if payment.status != "CAPTURED":
        raise ValueError(
            f"Payment cannot be refunded because "
            f"its status is {payment.status}"
        )

    # ---------------------------------------------------
    # 3. Validate refund amount
    # ---------------------------------------------------

    if amount_paise > payment.amount_paise:
        raise ValueError(
            "Refund amount cannot exceed payment amount"
        )

    # ---------------------------------------------------
    # 4. Check previous refunds
    # ---------------------------------------------------

    refunded_amount = (
        db.query(Refund)
        .filter(
            Refund.payment_id == payment_id,
            Refund.status.in_(["PENDING", "PROCESSED"])
        )
        .with_entities(Refund.amount_paise)
        .all()
    )

    total_refunded = sum(
        refund_amount[0]
        for refund_amount in refunded_amount
    )

    remaining_refundable = (
        payment.amount_paise - total_refunded
    )

    if amount_paise > remaining_refundable:
        raise ValueError(
            f"Refund exceeds remaining refundable balance. "
            f"Remaining: {remaining_refundable} paise"
        )

    # ---------------------------------------------------
    # 5. Create REFUND_INTENT
    # ---------------------------------------------------

    intent_id = str(uuid.uuid4())

    intent = RefundIntent(
        id=intent_id,
        payment_id=payment_id,
        amount_paise=amount_paise,
        status=RefundStatus.CHECKING,
        decision=None,
        reason=None,
        idempotency_key=f"refund-{intent_id}",
    )

    db.add(intent)
    db.flush()

    # ---------------------------------------------------
    # 6. Risk checks
    # ---------------------------------------------------

    if has_active_dispute(db, payment_id):

        intent.status = RefundStatus.BLOCKED

        intent.decision = (
            RefundDecision.BLOCK_DISPUTE
        )

        intent.reason = (
            "Active dispute detected. "
            "Refund blocked to prevent duplicate "
            "financial outflow."
        )

    elif has_active_prealert(db, payment_id):

        intent.status = RefundStatus.BLOCKED

        intent.decision = (
            RefundDecision.BLOCK_PRE_ALERT
        )

        intent.reason = (
            "Active pre-dispute alert detected. "
            "Refund blocked pending further review."
        )

    else:

        intent.status = RefundStatus.APPROVED

        intent.decision = RefundDecision.ALLOW

        intent.reason = (
            "No active dispute or pre-alert detected."
        )

    # ---------------------------------------------------
    # 7. Commit decision
    # ---------------------------------------------------

    db.commit()
    db.refresh(intent)

    return intent