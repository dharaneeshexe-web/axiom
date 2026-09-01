"""Merchant metrics — honest analytics for the Track-1 'merchant growth' story.

Records every checkout outcome (success / failed / recovered) and money moved,
then exposes aggregated conversion, recovery rate, and revenue-recovered metrics
for the merchant dashboard. All values are computed from what actually happened
during the session (or seeded simulation in demo mode).
"""
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class CheckoutEvent:
    ts: str
    outcome: str            # success | failed | recovered
    order_id: Optional[str]
    item: Optional[str]
    amount_paise: int
    method: Optional[str]
    recovered_from: Optional[str] = None
    latency_ms: Optional[float] = None


class MetricsTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self.events: List[CheckoutEvent] = []
        self._prune_cap = 500
        # seeded baseline so the dashboard shows a realistic funnel even fresh
        self._seed: List[CheckoutEvent] = []

    def seed(self, events: List[CheckoutEvent]) -> None:
        self._seed = events

    def record(
        self,
        outcome: str,
        order_id: Optional[str],
        item: Optional[str],
        amount_paise: int,
        method: Optional[str] = None,
        recovered_from: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> None:
        ev = CheckoutEvent(
            ts=datetime.utcnow().isoformat(),
            outcome=outcome,
            order_id=order_id,
            item=item,
            amount_paise=amount_paise,
            method=method,
            recovered_from=recovered_from,
            latency_ms=latency_ms,
        )
        with self._lock:
            self.events.append(ev)
            if len(self.events) > self._prune_cap:
                self.events = self.events[-self._prune_cap:]

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            events = self._seed + self.events
        total = len(events)
        success = sum(1 for e in events if e.outcome == "success")
        recovered = sum(1 for e in events if e.outcome == "recovered")
        failed = sum(1 for e in events if e.outcome == "failed")
        revenue_success = sum(e.amount_paise for e in events if e.outcome == "success")
        revenue_recovered = sum(e.amount_paise for e in events if e.outcome == "recovered")
        orders = success + recovered + failed
        overall_success = success + recovered
        conversion = (overall_success / total * 100) if total else 0.0
        # recovery rate = recovered / (recovered + failed)  -- of the failures we could recover
        attemptable = recovered + failed
        recovery_rate = (recovered / attemptable * 100) if attemptable else 0.0
        return {
            "total_orders": orders,
            "checkouts": total,
            "succeeded": success,
            "recovered": recovered,
            "failed": failed,
            "conversion_rate_pct": round(conversion, 1),
            "recovery_rate_pct": round(recovery_rate, 1),
            "revenue_success_paise": revenue_success,
            "revenue_recovered_paise": revenue_recovered,
            "revenue_total_paise": revenue_success + revenue_recovered,
            "recent": [
                {
                    "ts": e.ts,
                    "outcome": e.outcome,
                    "item": e.item,
                    "amount_paise": e.amount_paise,
                    "method": e.method,
                    "recovered_from": e.recovered_from,
                    "latency_ms": e.latency_ms,
                }
                for e in events[-10:]
            ],
        }


# shared singleton so the merchant dashboard aggregates across all sessions
metrics_tracker = MetricsTracker()
