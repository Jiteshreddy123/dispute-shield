from datetime import datetime

from sqlalchemy import (
    String,
    BigInteger,
    DateTime,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    merchant_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    amount_paise: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )


class RefundIntent(Base):
    __tablename__ = "refund_intents"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    payment_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    amount_paise: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    decision: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    payment_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    refund_intent_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True
    )

    amount_paise: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False
    )

    arn: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    payment_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    amount_paise: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    phase: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    reason_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True
    )

    respond_by: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )


class PreAlert(Base):
    __tablename__ = "pre_alerts"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    payment_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    alert_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )


class ProviderEvent(Base):
    __tablename__ = "provider_events"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    provider_event_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False
    )

    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    entity_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False
    )

    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )


class LedgerEvent(Base):
    __tablename__ = "ledger_events"

    sequence: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    payment_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    amount_paise: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True
    )

    reference_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True
    )

    event_metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True
    )

    previous_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    event_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    aggregate_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False
    )

    attempts: Mapped[int] = mapped_column(
        default=0,
        nullable=False
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
class DefensePackage(Base):
    __tablename__ = "defense_packages"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    dispute_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    payment_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    disputed_amount_paise: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    contestable_amount_paise: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    uncovered_amount_paise: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="READY",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    defense_package_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    evidence_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    source_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    document_reference: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    payment_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False
    )

    sender: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    message_text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    