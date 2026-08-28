from sqlalchemy.orm import Session

from app.db.models import Dispute, PreAlert


def has_active_dispute(
    db: Session,
    payment_id: str
) -> bool:

    dispute = (
        db.query(Dispute)
        .filter(
            Dispute.payment_id == payment_id,
            Dispute.status == "OPEN"
        )
        .first()
    )

    return dispute is not None


def has_active_prealert(
    db: Session,
    payment_id: str
) -> bool:

    alert = (
        db.query(PreAlert)
        .filter(
            PreAlert.payment_id == payment_id,
            PreAlert.status == "OPEN"
        )
        .first()
    )

    return alert is not None