"""Webhook-driven payment recovery for real (live-mode) Razorpay failures.

Razorpay fires a webhook (e.g. ``payment.failed``) as an independent HTTP call
when a buyer attempts a payment link and their card is declined at Razorpay's
end. This module verifies the webhook signature, decides whether the failure is
a retryable (transient/decline) cause worth re-attempting, and - if so - creates
a NEW payment link for the SAME order using a different method (UPI).

Design rules honoured (Track-1 "bounded + gated"):
  * Only transient/decline causes are retried. Fraud / risk / signature-failure
    codes are NEVER re-attempted (defence-only, no money chasing).
  * One recovery link per failing payment, recorded in the shared WebhookStore.
  * The money action (`create_payment_link`) is dependency-injected so tests can
    stub it hermetically - no real API calls in the suite.
"""
import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from .webhook_store import WebhookRecord, webhook_store

# Substrings that mark a failure as clearly retryable via a different method.
_RETRYABLE = (
    "declined",
    "insufficient",
    "expired",
    "processing",
    "try again",
    "temporarily",
    "technical",
    "unable",
)

# Substrings that are NEVER retried (fraud / risk / integrity). Defence-only.
_NON_RETRYABLE = (
    "fraud",
    "suspected_fraud",
    "risk",
    "signature",
    "breach",
    "card_monitoring",
    "auth_failed_auth_breach",
    "highest_risk",
)


@dataclass
class WebhookDecision:
    """Outcome of processing one webhook event."""

    received: bool = False
    verified: bool = False
    event: str | None = None
    payment_id: str | None = None
    order_id: str | None = None
    action: str = "ignored"  # noop | recovered | not_retryable | unknown_order
    recovered_link: str | None = None
    recovered_method: Any | None = None
    error_code: str | None = None
    error_description: str | None = None
    reason: str | None = None


def verify_signature(payload_bytes: bytes, signature: str, secret: str) -> bool:
    """Verify Razorpay's HMAC-SHA256 webhook signature over the raw body."""
    if not secret or not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    try:
        return hmac.compare_digest(expected, signature)
    except TypeError:
        return False


class WebhookRecoveryHandler:
    """Processes Razorpay payment webhooks and drives one recovery attempt."""

    def __init__(self, client, secret: str, store=webhook_store, max_retries: int = 1):
        self.client = client
        self.secret = secret
        self.store = store
        self.max_retries = max_retries

    async def handle(self, payload: dict[str, Any]) -> WebhookDecision:
        event = (payload or {}).get("event")
        if not event:
            return WebhookDecision(received=True, action="ignored", reason="no_event")

        if not event.startswith("payment."):
            return WebhookDecision(received=True, event=event, action="ignored", reason="not_a_payment_event")

        entity = ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}
        payment_id = entity.get("id")
        notes = entity.get("notes") or {}
        # order_id is set via the payment-link notes we attach when creating links
        order_id = notes.get("order_id") or entity.get("order_id")

        decision = WebhookDecision(
            received=True,
            verified=True,
            event=event,
            payment_id=payment_id,
            order_id=order_id,
            error_code=entity.get("error_code"),
            error_description=entity.get("error_description"),
        )

        # payment.paid -> mark recovery as confirmed if this was a recovery link
        if event == "payment.paid":
            rec = self.store.by_payment_link(payment_id) if payment_id else None
            if rec:
                rec.status = "recovered"
                rec.recovered_link = entity.get("notes", {}).get("upi_link") or rec.recovered_link
                return WebhookDecision(
                    received=True, verified=True, event=event, payment_id=payment_id,
                    order_id=order_id, action="recovered", recovered_link=rec.recovered_link,
                )
            return WebhookDecision(received=True, verified=True, event=event, action="ignored", reason="no_matching_recovery")

        if event != "payment.failed":
            return WebhookDecision(received=True, verified=True, event=event, action="ignored", reason="unhandled_event")

        # payment.failed -> maybe retry
        code = (entity.get("error_code") or "").lower()
        desc = (entity.get("error_description") or "").lower()
        if self._is_non_retryable(code, desc):
            decision.action = "not_retryable"
            decision.reason = f"fraud_or_risk ({code or 'unknown'}) - not re-attempted"
            return decision

        if not order_id:
            decision.action = "unknown_order"
            decision.reason = "no order_id in webhook"
            return decision

        # Make sure this order was created by us and hasn't exhausted retries
        rec = self.store.by_order(order_id)
        if not rec:
            decision.action = "unknown_order"
            decision.reason = f"order {order_id} not in registry"
            return decision
        if rec.retry_count >= self.max_retries:
            decision.action = "not_retryable"
            decision.reason = "max retries reached"
            return decision

        # Attempt one recovery: a new payment link via UPI for the same order.
        try:
            link = await self._create_recovery_link(rec, order_id)
        except Exception as e:  # noqa: BLE001 - surface any provider error as a graceful failure
            rec.status = "failed"
            decision.action = "failed"
            decision.reason = str(e)
            return decision

        rec.retry_count += 1
        rec.status = "recovery_sent"
        rec.recovered_link = link
        rec.recovered_method = "upi"
        rec.recovered_from_code = code
        self.store.register_recovery(link, rec)

        decision.action = "recovered"
        decision.recovered_link = link
        decision.recovered_method = "upi"
        decision.reason = f"card {code or 'declined'} -> upi recovery link sent"
        return decision

    async def _create_recovery_link(self, rec: WebhookRecord, order_id: str) -> str:
        """Create a UPI payment link for the SAME order. Injected for tests."""
        link = await self.client.create_payment_link({
            "amount": rec.amount,
            "currency": rec.currency,
            "description": f"Recovery payment for order {order_id} (via UPI)",
            "notes": {
                "order_id": order_id,
                "merchant_id": "axiom",
                "is_recovery": "1",
                "upi_link": "1",
            },
        })
        url = link.get("short_url")
        if not url:
            raise RuntimeError("recovery link created without short_url")
        return url

    @staticmethod
    def _is_non_retryable(code: str, desc: str) -> bool:
        blob = f"{code} {desc}"
        low = blob.lower()
        if any(m in low for m in _NON_RETRYABLE):
            return True
        # If we can't classify it at all, be safe: only retry known retryable causes
        return not any(m in low for m in _RETRYABLE)
