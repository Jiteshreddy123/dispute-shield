"""
defense_service.py
------------------
Builds a grounded defense package for a dispute.

Rules:
- ONLY use evidence that actually exists in the database.
- NEVER invent ARN, refund amounts, or support messages.
- AI/LLM summary is grounded in structured retrieved facts.
- Deterministic financial calculations use integer paise.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from app.db.models import (
    Refund,
    SupportMessage,
    DefensePackage,
    EvidenceItem,
)


def build_defense_package(
    db: "Session",
    dispute_id: str,
    payment_id: str,
    dispute_amount_paise: int,
) -> dict:
    """
    Build a defense package for a dispute.
    Uses only structured evidence that exists in the database.
    Returns a result dict (does not commit — caller commits).
    """

    # --------------------------------------------------------
    # 1. Find all verified (PROCESSED) refunds for this payment
    # --------------------------------------------------------
    refunds = (
        db.query(Refund)
        .filter(
            Refund.payment_id == payment_id,
            Refund.status == "PROCESSED",
        )
        .order_by(Refund.created_at.asc())
        .all()
    )

    total_refunded_paise = sum(r.amount_paise for r in refunds)

    # --------------------------------------------------------
    # 2. Calculate contestable and uncovered amounts
    #    Integer arithmetic only — no floats for money.
    # --------------------------------------------------------
    contestable_amount_paise = min(dispute_amount_paise, total_refunded_paise)
    uncovered_amount_paise = dispute_amount_paise - contestable_amount_paise

    # --------------------------------------------------------
    # 3. Find support messages (customer communication evidence)
    # --------------------------------------------------------
    support_messages = (
        db.query(SupportMessage)
        .filter(SupportMessage.payment_id == payment_id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )

    # --------------------------------------------------------
    # 4. Identify missing evidence types
    # --------------------------------------------------------
    missing_evidence = []
    available_evidence_types = []

    if refunds:
        available_evidence_types.append("refund_confirmation")
    else:
        missing_evidence.append("refund_confirmation — no processed refunds found")

    if support_messages:
        available_evidence_types.append("customer_communication")
    else:
        missing_evidence.append("customer_communication — no support messages found")

    # These would require merchant-side data we don't have:
    missing_evidence.append(
        "delivery_proof — not available in this demo dataset"
    )
    missing_evidence.append(
        "order_confirmation — not available in this demo dataset"
    )

    # --------------------------------------------------------
    # 5. Generate grounded defense summary
    #    This is rule-based text grounded in structured facts.
    #    An LLM could improve fluency but must NOT invent facts.
    # --------------------------------------------------------
    summary = _generate_summary(
        payment_id=payment_id,
        dispute_amount_paise=dispute_amount_paise,
        refunds=refunds,
        total_refunded_paise=total_refunded_paise,
        contestable_amount_paise=contestable_amount_paise,
        uncovered_amount_paise=uncovered_amount_paise,
        support_messages=support_messages,
        missing_evidence=missing_evidence,
    )

    # --------------------------------------------------------
    # 6. Determine defense package status
    # --------------------------------------------------------
    if uncovered_amount_paise > 0 and not refunds:
        status = "INCOMPLETE"
    elif uncovered_amount_paise > 0:
        status = "PARTIALLY_DEFENSIBLE"
    else:
        status = "READY"

    # --------------------------------------------------------
    # 7. Create defense package record
    # --------------------------------------------------------
    defense_package_id = f"def_{dispute_id}"

    # Check for existing package (idempotent)
    existing = (
        db.query(DefensePackage)
        .filter(DefensePackage.dispute_id == dispute_id)
        .first()
    )
    if existing:
        # Return existing data
        return {
            "defense_package_id": existing.id,
            "refunds_found": len(refunds),
            "total_refunded_paise": total_refunded_paise,
            "contestable_amount_paise": existing.contestable_amount_paise,
            "uncovered_amount_paise": existing.uncovered_amount_paise,
            "defense_status": existing.status,
            "missing_evidence": missing_evidence,
        }

    defense_package = DefensePackage(
        id=defense_package_id,
        dispute_id=dispute_id,
        payment_id=payment_id,
        disputed_amount_paise=dispute_amount_paise,
        contestable_amount_paise=contestable_amount_paise,
        uncovered_amount_paise=uncovered_amount_paise,
        summary=summary,
        status=status,
    )
    db.add(defense_package)
    db.flush()

    # --------------------------------------------------------
    # 8. Create evidence items (only real evidence)
    # --------------------------------------------------------
    for refund in refunds:
        arn_text = f"ARN: {refund.arn}" if refund.arn else "ARN: not yet available"
        evidence = EvidenceItem(
            id=f"ev_ref_{refund.id}",
            defense_package_id=defense_package_id,
            evidence_type="refund_confirmation",
            source_type="refund",
            source_id=refund.id,
            description=(
                f"Verified refund of ₹{refund.amount_paise / 100:.2f} "
                f"for payment {payment_id}. "
                f"Status: {refund.status}. "
                f"{arn_text}. "
                f"Processed at: {refund.processed_at.isoformat() if refund.processed_at else 'unknown'}."
            ),
            document_reference=refund.arn if refund.arn else refund.id,
        )
        db.add(evidence)

    for message in support_messages:
        evidence = EvidenceItem(
            id=f"ev_msg_{message.id}",
            defense_package_id=defense_package_id,
            evidence_type="customer_communication",
            source_type="support_message",
            source_id=message.id,
            description=message.message_text,
            document_reference=message.id,
        )
        db.add(evidence)

    db.flush()

    return {
        "defense_package_id": defense_package_id,
        "refunds_found": len(refunds),
        "total_refunded_paise": total_refunded_paise,
        "contestable_amount_paise": contestable_amount_paise,
        "uncovered_amount_paise": uncovered_amount_paise,
        "defense_status": status,
        "missing_evidence": missing_evidence,
    }


def _generate_summary(
    payment_id: str,
    dispute_amount_paise: int,
    refunds: list,
    total_refunded_paise: int,
    contestable_amount_paise: int,
    uncovered_amount_paise: int,
    support_messages: list,
    missing_evidence: list,
) -> str:
    """
    Generate a grounded defense summary from structured facts.
    This is deterministic rule-based text — no LLM hallucination risk.
    """
    lines = [
        f"DISPUTE DEFENSE SUMMARY",
        f"Payment: {payment_id}",
        f"Disputed Amount: ₹{dispute_amount_paise / 100:.2f}",
        "",
    ]

    if refunds:
        lines.append(f"VERIFIED REFUNDS ({len(refunds)} found):")
        for r in refunds:
            arn_text = f"ARN: {r.arn}" if r.arn else "ARN: pending"
            lines.append(
                f"  • ₹{r.amount_paise / 100:.2f} — {arn_text} — {r.processed_at.strftime('%Y-%m-%d') if r.processed_at else 'date unknown'}"
            )
        lines.append(f"  Total Refunded: ₹{total_refunded_paise / 100:.2f}")
    else:
        lines.append("VERIFIED REFUNDS: None found.")

    lines.append("")
    lines.append(
        f"CONTESTABLE AMOUNT: ₹{contestable_amount_paise / 100:.2f} "
        f"(covered by verified refunds)"
    )

    if uncovered_amount_paise > 0:
        lines.append(
            f"UNCOVERED EXPOSURE: ₹{uncovered_amount_paise / 100:.2f} "
            f"(no refund evidence to contest this portion)"
        )
    else:
        lines.append("UNCOVERED EXPOSURE: ₹0.00 — fully covered by refunds.")

    if support_messages:
        lines.append("")
        lines.append(f"CUSTOMER COMMUNICATION ({len(support_messages)} messages):")
        for m in support_messages:
            lines.append(f"  [{m.sender}]: {m.message_text[:100]}{'...' if len(m.message_text) > 100 else ''}")

    if missing_evidence:
        lines.append("")
        lines.append("MISSING EVIDENCE (explicitly noted):")
        for m in missing_evidence:
            lines.append(f"  ✗ {m}")

    lines.append("")
    if contestable_amount_paise > 0:
        lines.append(
            "RECOMMENDED ACTION: Contest the dispute with refund confirmation evidence. "
            f"Contest amount: ₹{contestable_amount_paise / 100:.2f}."
        )
        if uncovered_amount_paise > 0:
            lines.append(
                f"NOTE: ₹{uncovered_amount_paise / 100:.2f} remains uncontested — "
                "merchant should review additional evidence sources."
            )
    else:
        lines.append(
            "RECOMMENDED ACTION: Gather additional evidence before contesting. "
            "No verified refunds found to support a contest."
        )

    lines.append("")
    lines.append(
        "DISCLAIMER: This defense package was automatically assembled from structured "
        "transaction data. Dispute outcomes depend on network/issuer decisions and are not guaranteed."
    )

    return "\n".join(lines)
