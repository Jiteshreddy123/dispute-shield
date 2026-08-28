"""
refund_execution.py
--------------------
Executes an approved refund intent against the payment provider.

Safety properties:
- Only APPROVED intents can be executed.
- Uses the intent's idempotency_key for the provider call.
  If the provider times out and you retry, you get the same result.
- The external provider is NOT part of our database transaction.
  We use: transaction + idempotency + outbox/retry.
- NEVER claim distributed database lock eliminates the external network race.
"""

from sqlalchemy.orm import Session

from app.db.models import Refund, RefundIntent
from app.domain.states import RefundStatus
from app.providers.razorpay_mock import RazorpayMock, RefundTimeoutError


razorpay = RazorpayMock()


def execute_refund(
    db: Session,
    intent: RefundIntent,
) -> Refund:
    if intent.status != RefundStatus.APPROVED:
        raise ValueError(
            "Only APPROVED refund intents can be executed."
        )

    # Check if refund was already created (idempotency guard)
    existing_refund = (
        db.query(Refund)
        .filter(Refund.refund_intent_id == intent.id)
        .first()
    )
    if existing_refund:
        return existing_refund

    # Mark intent as EXECUTING
    intent.status = RefundStatus.EXECUTING
    db.commit()
    db.refresh(intent)

    try:
        provider_response = razorpay.create_refund(
            payment_id=intent.payment_id,
            amount_paise=intent.amount_paise,
            idempotency_key=intent.idempotency_key,
        )
    except RefundTimeoutError as exc:
        # Timeout: mark intent as APPROVED again so retry is safe.
        # The idempotency_key is preserved — a retry will use the same key.
        intent.status = RefundStatus.APPROVED
        db.commit()
        raise ValueError(
            f"Provider timeout: {exc}. "
            "Retry this intent using the same idempotency key — no double charge risk."
        ) from exc

    refund = Refund(
        id=provider_response["id"],
        payment_id=intent.payment_id,
        refund_intent_id=intent.id,
        amount_paise=intent.amount_paise,
        status="PENDING",
        idempotency_key=intent.idempotency_key,
    )

    db.add(refund)
    intent.status = RefundStatus.PENDING

    db.commit()
    db.refresh(refund)

    return refund