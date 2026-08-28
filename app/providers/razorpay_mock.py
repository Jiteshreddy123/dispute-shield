"""
razorpay_mock.py
-----------------
Mock Razorpay payment provider.

This simulates the Razorpay API boundary for demo and testing purposes.
It does NOT make real network calls.

The provider interface is decoupled from domain logic:
- Domain calls provider.create_refund(...)
- Provider returns a normalized response dict
- Domain never knows or cares that this is a mock

Scenarios supported:
  - successful_refund: immediate success
  - timeout: raises TimeoutError (domain must retry with same idempotency key)
  - duplicate: returns same refund ID for same idempotency key
"""

from __future__ import annotations

import uuid
from typing import Literal


# Simulate a simple in-memory idempotency store
# In production this would be in the provider's system
_idempotency_store: dict[str, dict] = {}


class RefundTimeoutError(Exception):
    """Raised when the provider simulates a network timeout."""
    pass


class RazorpayMock:
    """
    Mock implementation of the Razorpay provider boundary.

    The 'scenario' parameter controls provider behavior:
      - 'success': normal refund creation
      - 'timeout': raises RefundTimeoutError (retry with same idempotency key)
      - 'pending': returns status='pending' (webhook expected later)
    """

    def __init__(self, scenario: Literal["success", "timeout", "pending"] = "success"):
        self.scenario = scenario

    def create_refund(
        self,
        payment_id: str,
        amount_paise: int,
        idempotency_key: str,
    ) -> dict:
        """
        Create a refund against Razorpay (mocked).

        Idempotency: Same key always returns the same refund ID.
        This is critical for retry safety — if a network timeout occurs
        and you retry with the same key, you get the same result
        (no double refund).

        NOTE: The external payment provider is NOT part of our database
        transaction. We use idempotency + outbox/retry instead of
        distributed 2PC.
        """
        # Idempotency: return same result for same key
        if idempotency_key in _idempotency_store:
            return _idempotency_store[idempotency_key]

        if self.scenario == "timeout":
            # Simulate network timeout — caller must retry with same key
            raise RefundTimeoutError(
                f"Provider network timeout for payment {payment_id}. "
                "Retry with the same idempotency key."
            )

        refund_id = f"rfnd_{uuid.uuid4().hex[:12]}"

        if self.scenario == "pending":
            status = "pending"
        else:
            status = "created"

        result = {
            "id": refund_id,
            "payment_id": payment_id,
            "amount": amount_paise,
            "status": status,
            "idempotency_key": idempotency_key,
        }

        _idempotency_store[idempotency_key] = result
        return result

    def build_dispute_webhook_payload(
        self,
        payment_id: str,
        dispute_id: str,
        amount_paise: int,
        reason_code: str = "chargeback",
        phase: str = "chargeback",
    ) -> dict:
        """
        Build a realistic Razorpay dispute webhook payload.
        Used by the scenario engine to simulate dispute events.
        """
        return {
            "event": "payment.dispute.created",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "amount": amount_paise,
                        "currency": "INR",
                        "status": "captured",
                    }
                },
                "dispute": {
                    "entity": {
                        "id": dispute_id,
                        "payment_id": payment_id,
                        "amount": amount_paise,
                        "status": "open",
                        "phase": phase,
                        "reason_code": reason_code,
                    }
                },
            },
        }

    def build_refund_processed_webhook_payload(
        self,
        refund_id: str,
        payment_id: str,
        amount_paise: int,
        arn: str | None = None,
    ) -> dict:
        """
        Build a realistic Razorpay refund.processed webhook payload.
        Used by the scenario engine.
        """
        return {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": refund_id,
                        "payment_id": payment_id,
                        "amount": amount_paise,
                        "status": "processed",
                        "acquirer_data": {
                            "arn": arn or f"ARN{uuid.uuid4().hex[:16].upper()}",
                        },
                    }
                }
            },
        }


def clear_idempotency_store():
    """
    Clear the mock idempotency store.
    Call this between test runs to ensure clean state.
    """
    _idempotency_store.clear()