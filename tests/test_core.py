"""Core behaviour tests for the Axiom conversational checkout agent.

Hermetic: the Groq intent parser is stubbed (see conftest.py) and payments run
in simulate mode, so every test is deterministic and offline. These guard the
most important guarantees: stage transitions, the policy approval gate, the
approval-gate auto-confirm loop regression, and card-declined -> UPI recovery.
"""


from src.agent.session import ChatSession, Stage
from src.services.razorpay import set_payment_mode


def _session() -> ChatSession:
    set_payment_mode("simulate")
    return ChatSession()


async def test_chocolate_cake_auto_approves_and_reaches_done():
    s = _session()
    r1 = await s.process("Order a chocolate ice cream cake")
    assert r1.stage == Stage.CONFIRM
    assert r1.policy.requires_approval is False
    r2 = await s.process("yes")
    assert r2.stage == Stage.DONE
    assert r2.success is True


async def test_high_ticket_requires_explicit_approval_not_yes():
    """iPhone (Rs 85,900) must not execute on 'yes' — only on APPROVE."""
    s = _session()
    r1 = await s.process("order an iphone blue 256")
    assert r1.stage == Stage.CONFIRM
    assert r1.policy.requires_approval is True

    # 'yes' must be BLOCKED at the approval gate (does not execute)
    r2 = await s.process("yes")
    assert r2.stage == Stage.CONFIRM
    assert r2.policy.requires_approval is True
    assert s.stage == Stage.CONFIRM

    # 'approve' unlocks execution
    r3 = await s.process("approve")
    assert r3.stage == Stage.DONE
    assert r3.success is True


async def test_no_loop_after_done_repeated_yes_stays_done():
    """Regression for the infinite user_confirmation loop."""
    s = _session()
    await s.process("Order a chocolate ice cream cake")   # -> CONFIRM
    r = await s.process("yes")                             # -> DONE
    assert r.stage == Stage.DONE
    # repeated confirmations after DONE must NOT re-enter CONFIRM / loop
    for _ in range(5):
        r = await s.process("yes")
        assert r.stage == Stage.DONE
    assert s.stage == Stage.DONE


async def test_card_declined_recovers_via_upi():
    s = _session()
    s.payment_service.demo_failure = "card_declined"
    await s.process("Order a chocolate ice cream cake")    # -> CONFIRM (auto)
    r = await s.process("yes")                             # executes -> card declined -> UPI retry
    assert r.stage == Stage.DONE
    assert r.success is True
    assert "upi" in r.text.lower()
    assert "recovered" in r.text.lower()
    assert r.payment_status == "success"


async def test_over_budget_is_gated():
    s = _session()
    # deplete the monthly budget so the next purchase is over budget
    s.policy.record_spend(9_999_999)
    r1 = await s.process("Order a chocolate ice cream cake")
    assert r1.stage == Stage.CONFIRM
    assert r1.policy.over_budget is True
    # over-budget must NOT execute on 'yes' — it is refused (no money moved)
    r2 = await s.process("yes")
    assert r2.stage == Stage.BROWSE
    assert r2.success is False
    assert s.stage == Stage.BROWSE


async def test_catalog_loads_48_products_from_json():
    from src.services.catalog import CatalogService
    c = CatalogService()
    assert len(c.products) == 48
    assert c.get_product("iphone16_blue_256") is not None
    assert any(p.category == "Meat & Fish" for p in c.products)


def test_catalog_search_endpoints():
    from fastapi.testclient import TestClient

    from src.api.endpoints import app
    c = TestClient(app)
    r = c.get("/catalog/search?q=chicken")
    assert r.status_code == 200
    ids = [x["item_id"] for x in r.json()]
    assert "chicken_curry_500" in ids
    r = c.get("/catalog/item/iphone16_blue_256")
    assert r.status_code == 200
    assert r.json()["name"] == "iPhone 16 Blue 256GB"
    assert c.get("/catalog/item/does_not_exist").status_code == 404


async def test_cross_sell_offered_and_adding_it_increases_order():
    """Track-01 growth: a bounded, in-budget cross-sell is offered at confirm."""
    s = _session()
    r1 = await s.process("Order a chocolate ice cream cake")
    assert r1.stage == Stage.CONFIRM
    assert r1.upsell_item_id == "brownie_1"   # cake -> brownie add-on, in budget
    # plain 'yes' skips the upsell (single item order)
    s2 = _session()
    await s2.process("Order a chocolate ice cream cake")
    r_skip = await s2.process("yes")
    assert r_skip.amount == 45_000  # just the cake
    # accepting the upsell adds it to the same order
    s3 = _session()
    await s3.process("Order a chocolate ice cream cake")
    r_add = await s3.process("yes add")
    assert r_add.amount == 52_000   # 45,000 cake + 7,000 brownie
    assert r_add.success is True


async def test_upsell_not_offered_on_approval_gated_purchase():
    """High-ticket purchases pause for approval and never push a cross-sell."""
    s = _session()
    r1 = await s.process("order an iphone blue 256")
    assert r1.stage == Stage.CONFIRM
    assert r1.policy.requires_approval is True
    assert r1.upsell_item_id is None
