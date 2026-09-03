"""Shared fixtures for the Axiom test suite.

The real IntentParser calls Groq over the network. For hermetic, offline,
reliable tests we replace it with a deterministic stub that maps a handful of
canned queries to Intent objects. This keeps the whole session state machine,
policy engine, payment simulation and no-loop guarantees testable with zero
external calls.
"""

import pytest

import src.agent.session as session_mod
from src.models.schemas import Intent, PaymentMethod
from src.services.razorpay import set_payment_mode


class StubIntentParser:
    """Deterministic stand-in for IntentParser (no Groq / network)."""

    def _match(self, q: str, *keys: str) -> bool:
        ql = q.lower()
        return any(k in ql for k in keys)

    async def parse(self, user_query: str) -> Intent:
        q = user_query
        if self._match(q, "chocolate", "ice cream cake"):
            return Intent(
                raw_query=q,
                item="ice cream cake",
                flavor="chocolate",
                payment_method=PaymentMethod.CARD,
            )
        if self._match(q, "iphone", "blue 256"):
            return Intent(
                raw_query=q,
                item="iphone",
                color="blue",
                storage="256gb",
                payment_method=PaymentMethod.CARD,
            )
        if self._match(q, "bandage", "crepe"):
            return Intent(
                raw_query=q,
                item="bandage",
                size="small",
                payment_method=PaymentMethod.CARD,
            )
        if self._match(q, "blue", "256") and self._match(q, "iphone"):
            return Intent(
                raw_query=q, item="iphone", color="blue", storage="256gb"
            )
        # default: use the whole query as the item token (single-token search)
        return Intent(raw_query=q, item=q.strip())


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Swap the Groq-backed parser for the stub and force payment simulation."""
    monkeypatch.setattr(session_mod, "IntentParser", StubIntentParser)
    set_payment_mode("simulate")
    yield
    set_payment_mode("live")
