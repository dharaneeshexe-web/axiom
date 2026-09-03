"""Hermetic tests for real, webhook-driven payment recovery.

These all use an injected stub client (no real Razorpay API), so the suite stays
offline and reliable. Combined with the session recovery tests, they prove both
tiers of the recovery story: the deterministic demo sim trigger AND the real
webhook trigger for live mode.
"""

import asyncio
import hashlib
import hmac
import json

from src.services.webhook_recovery import WebhookRecoveryHandler, verify_signature
from src.services.webhook_store import WebhookRecord, WebhookStore


class StubClient:
    def __init__(self):
        self.calls = []

    async def create_payment_link(self, data):
        self.calls.append(data)
        return {"id": "plink_rec_1", "short_url": "https://rzp.link/recovery1"}


def _register(store, order_id="ord_x", amount=52000, item="Cake"):
    rec = WebhookRecord(order_id=order_id, currency="INR", amount=amount, item=item)
    store.register("plink_orig", rec, order_id)
    return rec


def _failed_payload(order_id="ord_x", code="BAD_REQUEST_CARD_DECLINED", desc="declined"):
    return {
        "event": "payment.failed",
        "payload": {"payment": {"entity": {
            "id": "pay_1",
            "order_id": order_id,
            "notes": {"order_id": order_id, "upi_link": "1"},
            "error_code": code,
            "error_description": desc,
        }}},
    }


def test_signature_verification():
    secret = "sekret"
    body = b'{"event":"payment.failed"}'
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert verify_signature(body, sig, secret) is True
    assert verify_signature(body, "nope", secret) is False
    assert verify_signature(body, sig, "") is False


def test_declined_card_triggers_upi_recovery():
    store = WebhookStore()
    rec = _register(store)
    client = StubClient()
    handler = WebhookRecoveryHandler(client, secret="sekret", store=store)
    d = asyncio.run(handler.handle(_failed_payload()))
    assert d.action == "recovered"
    assert d.recovered_link == "https://rzp.link/recovery1"
    assert d.recovered_method == "upi"
    assert len(client.calls) == 1
    assert rec.status == "recovery_sent"
    assert rec.retry_count == 1
    # the recovery link reuses the SAME order amount (bounded, not inflated)
    assert client.calls[0]["amount"] == 52000


def test_fraud_or_risk_is_never_retried():
    """Defence-only: a suspected-fraud decline must NOT re-attempt money."""
    store = WebhookStore()
    _register(store)
    client = StubClient()
    handler = WebhookRecoveryHandler(client, secret="sekret", store=store)
    d = asyncio.run(handler.handle(
        _failed_payload(code="SUSPECTED_FRAUD", desc="high risk")
    ))
    assert d.action == "not_retryable"
    assert len(client.calls) == 0


def test_unknown_order_is_not_recovered():
    store = WebhookStore()
    client = StubClient()
    handler = WebhookRecoveryHandler(client, secret="sekret", store=store)
    d = asyncio.run(handler.handle(_failed_payload(order_id="ghost_order")))
    assert d.action == "unknown_order"
    assert len(client.calls) == 0


def test_max_retries_respected():
    store = WebhookStore()
    rec = _register(store)
    rec.retry_count = 1
    client = StubClient()
    handler = WebhookRecoveryHandler(client, secret="sekret", store=store, max_retries=1)
    d = asyncio.run(handler.handle(_failed_payload()))
    assert d.action == "not_retryable"
    assert d.reason == "max retries reached"
    assert len(client.calls) == 0


def test_webhook_endpoint_rejects_bad_signature():
    """When a WEBHOOK_SECRET is set, an unsigned/incorrect request is rejected."""
    from fastapi.testclient import TestClient

    import src.api.endpoints as ep

    orig = ep.app_settings.webhook_secret
    ep.app_settings.webhook_secret = "test_secret"
    try:
        c = TestClient(ep.app)
        r = c.post("/webhooks/razorpay", json={"event": "payment.failed"}, headers={})
        assert r.status_code == 400
        # a correctly-signed request passes verification (and is handled)
        body = json.dumps({"event": "payment.paid"}).encode("utf-8")
        sig = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        r2 = c.post(
            "/webhooks/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        assert r2.status_code == 200
        assert r2.json()["verified"] is True
    finally:
        ep.app_settings.webhook_secret = orig
