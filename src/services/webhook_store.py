"""Shared registry for Razorpay webhook-driven payment recovery.

Orders and payments normally live inside per-chat-session services that are
garbage-collected once a session expires. Webhooks arrive as independent HTTP
calls (often minutes later), so we need a cross-session lookup keyed by both
the payment-link id (what Razorpay addresses the webhook with) and the order id.

Thread-safe, bounded, TTL-pruned. This is NOT a durable database - it is an
in-process registry for the demo. A production build would persist these rows.
"""
import threading
from datetime import datetime


class WebhookRecord:
    __slots__ = (
        "order_id",
        "currency",
        "amount",
        "session_id",
        "method",
        "status",
        "retry_count",
        "ts",
        "recovered_link",
        "recovered_method",
        "recovered_from_code",
        "item",
    )

    def __init__(
        self,
        order_id: str,
        currency: str,
        amount: int,
        session_id: str | None = None,
        method: str | None = None,
        item: str | None = None,
    ):
        self.order_id = order_id
        self.currency = currency
        self.amount = amount
        self.session_id = session_id
        self.method = method
        self.item = item
        self.status = "created"  # created | recovery_sent | recovered | failed
        self.retry_count = 0
        self.ts = datetime.utcnow().isoformat()
        self.recovered_link: str | None = None
        self.recovered_method: str | None = None
        self.recovered_from_code: str | None = None


class WebhookStore:
    def __init__(self, ttl_seconds: int = 3600, cap: int = 500):
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._cap = cap
        self._by_link: dict[str, WebhookRecord] = {}
        self._by_order: dict[str, WebhookRecord] = {}
        self._by_recovery: dict[str, WebhookRecord] = {}

    def register(self, payment_link_id: str, record: WebhookRecord, order_id: str) -> None:
        with self._lock:
            self._by_link[payment_link_id] = record
            self._by_order[order_id] = record
            self._prune()

    def register_recovery(self, recovery_link: str, record: WebhookRecord) -> None:
        """Index a recovery payment link so a later payment.paid webhook can be matched."""
        with self._lock:
            self._by_recovery[recovery_link] = record

    def by_link(self, payment_link_id: str) -> WebhookRecord | None:
        with self._lock:
            rec = self._by_link.get(payment_link_id)
            return rec if rec and not self._expired(rec) else None

    def by_payment_link(self, link: str) -> WebhookRecord | None:
        """Look up a record by either the original or a recovery payment link."""
        with self._lock:
            rec = self._by_link.get(link) or self._by_recovery.get(link)
            return rec if rec and not self._expired(rec) else None

    def by_order(self, order_id: str) -> WebhookRecord | None:
        with self._lock:
            rec = self._by_order.get(order_id)
            return rec if rec and not self._expired(rec) else None

    def recent_recoveries(self, n: int = 5) -> list[dict]:
        """Recent recovery links (order -> upi link), newest first, for the dashboard."""
        with self._lock:
            records = [
                r for r in self._by_order.values()
                if r.recovered_link and not self._expired(r)
            ]
        records.sort(key=lambda r: r.ts, reverse=True)
        return [
            {
                "order_id": r.order_id,
                "recovered_link": r.recovered_link,
                "method": r.recovered_method,
                "from_code": r.recovered_from_code,
                "status": r.status,
                "item": r.item,
                "amount": r.amount,
                "ts": r.ts,
            }
            for r in records[:n]
        ]

    def _expired(self, rec: WebhookRecord) -> bool:
        try:
            ts = datetime.fromisoformat(rec.ts)
        except ValueError:
            return True
        age = (datetime.utcnow() - ts).total_seconds()
        return age > self._ttl

    def _prune(self) -> None:
        if len(self._by_link) <= self._cap:
            return
        # drop oldest entries by timestamp until under cap
        ordered = sorted(self._by_link.items(), key=lambda kv: kv[1].ts)
        for link_id, rec in ordered[: len(self._by_link) - self._cap]:
            self._by_link.pop(link_id, None)
            self._by_order.pop(rec.order_id, None)


# shared singleton so webhook handlers and payment creation share the registry
webhook_store = WebhookStore()
