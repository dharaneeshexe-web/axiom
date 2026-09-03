import re
import time as _time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ..config.settings import settings
from ..config.tracing import tracer
from ..models.schemas import CartItem, Intent, PaymentMethod, PaymentStatus
from ..services.catalog import CatalogService
from ..services.metrics import metrics_tracker
from ..services.order import OrderService
from ..services.payment import PaymentService
from ..services.policy import PolicyEngine
from ..services.razorpay import RazorpayClient, get_payment_mode, set_payment_mode
from .intent_parser import IntentParser


class Stage(str, Enum):
    BROWSE = "browse"        # waiting for initial product query
    SELECT = "select"        # variants shown, waiting for user pick
    CONFIRM = "confirm"      # one product chosen, waiting for yes/no
    EXECUTE = "execute"      # creating order + payment (transient)
    DONE = "done"


@dataclass
class VariantOption:
    label: str
    summary: str
    price_rupees: int
    item_id: str


@dataclass
class PolicyPayload:
    approved: bool
    requires_approval: bool
    over_budget: bool
    reason: str | None = None
    remaining_budget: int | None = None
    suggested_actions: list[str] = field(default_factory=list)
    merchant_rule: str | None = None
    decisions: list[str] = field(default_factory=list)


@dataclass
class AgentReply:
    text: str
    stage: Stage
    options: list[VariantOption] = field(default_factory=list)
    success: bool = False
    order_id: str | None = None
    amount: int | None = None
    currency: str | None = None
    payment_link: str | None = None
    trace_id: str | None = None
    payment_status: str | None = None
    error: str | None = None
    product_name: str | None = None
    product_summary: str | None = None
    product_emoji: str | None = None
    policy: PolicyPayload | None = None
    latency_ms: float | None = None
    upsell_item_id: str | None = None
    upsell_label: str | None = None
    upsell_price: int | None = None


class ChatSession:
    """Stateful multi-turn conversational checkout session.

    Stage machine:
      BROWSE -> SELECT -> CONFIRM -> EXECUTE -> DONE
    """

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        self.stage = Stage.BROWSE
        self.candidates: list = []          # Product objects (variants)
        self.selected: Optional = None      # chosen Product
        self.intent: Intent | None = None
        self.payment_method: PaymentMethod = PaymentMethod.CARD
        self.retry_count: int = 0
        self.trace_id: str | None = None
        self.final_reply: AgentReply | None = None

        # wired services per-session so demo failure simulation is deterministic
        self.razorpay = RazorpayClient()
        self.catalog = CatalogService()
        self.order_service = OrderService(self.razorpay)
        self.payment_service = PaymentService(self.razorpay)
        self.intent_parser = IntentParser()
        # policy engine: buyer profile + explicit rules evaluated before money moves
        self.preferred_payment = PaymentMethod.CARD
        self.policy = PolicyEngine(
            preferred_payment=self.preferred_payment,
            monthly_budget=settings.monthly_budget_paise,
            approval_threshold=settings.approval_threshold_paise,
        )
        self.turn_started = _time.perf_counter()
        self.approval_granted = False
        self.pending_policy = None
        self.upsell: Optional = None

    # ---- internal helpers ----

    def _rupees(self, paise: int) -> int:
        return paise // 100

    def _variant_list(self, products: list) -> list[VariantOption]:
        seen = set()
        out = []
        for p in products:
            marker = (p.name, p.price, p.item_id)
            if marker in seen:
                continue
            seen.add(marker)
            extra = []
            if p.color:
                extra.append(p.color)
            if p.storage:
                extra.append(p.storage)
            if p.size:
                extra.append(p.size)
            if p.flavor:
                extra.append(p.flavor)
            if p.merchant_name:
                extra.append(p.merchant_name)
            label = p.name
            out.append(
                VariantOption(
                    label=label,
                    summary=" - ".join(extra),
                    price_rupees=self._rupees(p.price),
                    item_id=p.item_id,
                )
            )
        return out

    def _describe(self, product) -> str:
        detail = product.name
        if product.price:
            detail += f" at \u20b9{self._rupees(product.price):,}"
        merchant = product.merchant_name or product.merchant_id
        if merchant:
            detail += f" (by {merchant})"
        return detail

    def _pick_from_message(self, message: str, candidates: list) -> Optional:
        msg = message.lower().strip()

        # try exact/near item-id or numeric index
        idx_match = re.search(r"^(?:option|#|number)?\s*([1-9]\d*)\s*$", msg)
        if idx_match:
            idx = int(idx_match.group(1)) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]

        # fall back on token similarity against name/description/attrs
        def norm(w: str) -> str:
            return w.lower().strip(".,!?()\"")

        msg_tokens = {norm(t) for t in msg.split() if len(t) > 1}
        best = None
        best_score = 0
        for p in candidates:
            hay = " ".join(
                [
                    p.name,
                    p.description or "",
                    p.color or "",
                    p.storage or "",
                    p.size or "",
                    p.flavor or "",
                ]
            )
            hay_tokens = {norm(t) for t in hay.split() if len(t) > 1}
            score = len(msg_tokens & hay_tokens)
            # exact item_id match wins
            if p.item_id.lower() in msg:
                return p
            if score > best_score:
                best_score = score
                best = p
        return best if best_score > 0 else None

    def _confirm_requested(self, message: str) -> bool:
        m = message.lower().strip()
        return any(tok in m for tok in ["yes", "confirm", "yep", "sure", "go ahead", "place it", "order it", "buy it", "ok"])

    def _deny_requested(self, message: str) -> bool:
        m = message.lower().strip()
        return any(tok in m for tok in ["no", "cancel", "never mind", "stop", "wrong", "different"])

    # ---- main entry ----

    async def process(self, message: str) -> AgentReply:
        # one conversation produces one trace; keep it open across turns
        if self.trace_id is None:
            self.trace_id = tracer.start_trace()
        tid = self.trace_id
        self.turn_started = _time.perf_counter()

        # Control command: switch between LIVE Razorpay API and SIMULATE (no API calls).
        # Protects the daily payment_links quota during demos — "don't call razorpay api".
        cmd = re.sub(r"[^a-z0-9 ]", "", message.lower())
        sim_on = any(p in cmd for p in [
            "don't call razorpay", "dont call razorpay", "stop calling razorpay",
            "simulate mode", "simulate payment", "simulate", "mock payments",
            "fake payments", "simulation mode", "offline mode", "no razorpay",
            "dont call razorpay api", "don't call razorpay api",
        ])
        sim_off = any(p in cmd for p in [
            "use razorpay", "call razorpay", "live mode", "go live",
            "real payment", "use real razorpay", "online mode", "set live",
        ])
        if sim_on or sim_off:
            mode = set_payment_mode("simulate" if sim_on else "live")
            return AgentReply(
                text=(
                    "Payments are now SIMULATED — I will NOT call the Razorpay API, "
                    "so the demo quota is safe. Say 'use razorpay' to go back live."
                    if mode == "simulate"
                    else "Payments are now LIVE — I will call the real Razorpay API."
                ),
                stage=self.stage,
                success=True,
                trace_id=tid,
            )
        if "payment mode" in cmd or "mode is" in cmd or "what mode" in cmd:
            mode = get_payment_mode()
            return AgentReply(
                text=f"Current payment mode: {mode.upper()} ({'real Razorpay API' if mode == 'live' else 'simulated, no API calls'}).",
                stage=self.stage,
                success=True,
                trace_id=tid,
            )

        if self.stage == Stage.DONE:
            return self.final_reply or AgentReply(
                text="This session is complete. Start a new session to order again.",
                stage=Stage.DONE,
                success=True,
                trace_id=tid,
            )

        if self.stage == Stage.BROWSE:
            reply = await self._handle_browse(message, tid)
        elif self.stage == Stage.SELECT:
            reply = await self._handle_select(message, tid)
        elif self.stage == Stage.CONFIRM:
            reply = await self._handle_confirm(message, tid)
        else:
            reply = AgentReply(
                text="I'm processing your order.",
                stage=self.stage,
                trace_id=tid,
            )

        if reply.stage == Stage.EXECUTE:
            reply = await self._execute_order(tid)
        if reply.stage == Stage.DONE and reply.success:
            self.final_reply = reply
        # attach per-turn latency for the metrics/trace story
        if reply.latency_ms is None:
            reply.latency_ms = self._turn_latency()
        return reply

    # ---- stage handlers ----

    async def _handle_browse(self, message: str, tid: str) -> AgentReply:
        sid = tracer.start_span(tid, "parse_intent", input={"message": message})
        intent = await self.intent_parser.parse(message)
        tracer.end_span(tid, sid, output=intent.model_dump())
        self.intent = intent

        if intent.payment_method:
            self.payment_method = intent.payment_method

        products = self.catalog.search_products(query=intent.item, merchant_id=intent.merchant)
        self.candidates = products

        if not intent.item or not products:
            return self._fail(tid, self._no_match_text(message))

        variants = self._variant_list(products)

        # If a specific variant is fully specified, try to pin it directly
        pinned = None
        if any([intent.color, intent.storage, intent.size, intent.flavor]):
            pinned = self._pin_from_intent(products, intent)
            if pinned:
                self.selected = pinned
                self.stage = Stage.CONFIRM
                return self._confirm_reply(tid, pinned)

        # If only one product exists, no need to disambiguate
        if len(variants) == 1:
            self.selected = products[0]
            self.stage = Stage.CONFIRM
            return self._confirm_reply(tid, products[0])

        # Multiple variants -> ask user to choose
        self.stage = Stage.SELECT
        sid = tracer.start_span(tid, "query_catalog", input={"item": intent.item})
        tracer.end_span(tid, sid, output=[p.item_id for p in products])
        names = " / ".join(dict.fromkeys(p.name.split(" ")[0] if p.name else "item" for p in products))
        return AgentReply(
            text=f"I found these options for {names}. Which would you like?",
            stage=Stage.SELECT,
            options=variants,
            success=True,
            trace_id=tid,
        )

    def _pin_from_intent(self, products: list, intent: Intent) -> Optional:
        if intent.color:
            products = [p for p in products if p.color and intent.color.lower() in p.color.lower()]
        if intent.storage:
            products = [p for p in products if p.storage and intent.storage.lower() in p.storage.lower()]
        if intent.size:
            products = [p for p in products if p.size and intent.size.lower() in p.size.lower()]
        if intent.flavor:
            products = [p for p in products if p.flavor and intent.flavor.lower() in p.flavor.lower()]
        return products[0] if products else None

    async def _handle_select(self, message: str, tid: str) -> AgentReply:
        chosen = self._pick_from_message(message, self.candidates)
        if not chosen:
            # maybe user gave more detail; re-parse to try to pin
            intent = await self.intent_parser.parse(message)
            self.intent = intent
            chosen = self._pin_from_intent(self.candidates, intent)
            if intent.payment_method:
                self.payment_method = intent.payment_method
        if not chosen:
            variants = self._variant_list(self.candidates)
            return AgentReply(
                text="Sorry, I couldn't match that. Please pick one of these options.",
                stage=Stage.SELECT,
                options=variants,
                success=True,
                trace_id=tid,
            )
        self.selected = chosen
        self.stage = Stage.CONFIRM
        sid = tracer.start_span(tid, "select_product", input={"message": message})
        tracer.end_span(tid, sid, output={"item_id": chosen.item_id, "name": chosen.name})
        return self._confirm_reply(tid, chosen)

    async def _handle_confirm(self, message: str, tid: str) -> AgentReply:
        # If an approval prompt is pending, "approve"/"authorize" grants it and proceeds.
        if self.pending_policy and self._approval_granted(message):
            sid = tracer.start_span(tid, "user_confirmation", input={"message": message})
            tracer.end_span(tid, sid, output={"confirmed": True, "approved": True})
            self.pending_policy = False
            self.approval_granted = True
            self.stage = Stage.EXECUTE
            return AgentReply(
                text="Approved. Placing your order now.",
                stage=Stage.EXECUTE,
                success=True,
                trace_id=tid,
            )
        if self._deny_requested(message):
            sid = tracer.start_span(tid, "user_confirmation", input={"message": message})
            tracer.end_span(tid, sid, output={"confirmed": False})
            self.stage = Stage.BROWSE
            self.candidates = []
            self.selected = None
            self.intent = None
            self.pending_policy = False
            return AgentReply(
                text="No problem — the order is cancelled. Is there something else you'd like?",
                stage=Stage.BROWSE,
                success=True,
                trace_id=tid,
            )
        if self._confirm_requested(message) or self._approval_granted(message):
            sid = tracer.start_span(tid, "user_confirmation", input={"message": message})
            price = self._current_price()
            policy = self._evaluate_policy(tid, self.selected, price)

            # Hard gate: never move money beyond the buyer's remaining monthly
            # budget. Over-budget is NOT approvable — it is refused, and the
            # session returns to browse so the buyer can change the item.
            if policy.over_budget:
                tracer.end_span(tid, sid, output={"confirmed": True, "blocked": "over_budget"})
                self.stage = Stage.BROWSE
                self.candidates = []
                self.selected = None
                self.intent = None
                self.pending_policy = False
                return AgentReply(
                    text=(
                        "I can't place this order: it's over your remaining monthly budget "
                        f"of \u20b9{self._rupees(policy.remaining_budget):,}. "
                        "Tell me a cheaper option or a lower quantity."
                    ),
                    stage=Stage.BROWSE,
                    success=False,
                    trace_id=tid,
                    policy=self._policy_payload(policy),
                )

            # Policy approval gate: big purchases pause for explicit human approval.
            if policy.requires_approval and not self.approval_granted:
                tracer.end_span(tid, sid, output={"confirmed": True, "awaiting_approval": True})
                self.pending_policy = True
                return AgentReply(
                    text=(
                        f"This purchase of \u20b9{self._rupees(price):,} is above your "
                        f"auto-approval limit of \u20b9{self._rupees(self.policy.approval_threshold):,}. "
                        f"Reply APPROVE to continue, or tell me to change it."
                    ),
                    stage=Stage.CONFIRM,
                    success=True,
                    trace_id=tid,
                    product_name=self.selected.name,
                    product_summary=self._describe(self.selected),
                    product_emoji=self.selected.emoji,
                    policy=self._policy_payload(policy),
                )
            tracer.end_span(tid, sid, output={"confirmed": True, "product": self.selected.name, "upsell": bool(self.upsell)})
            # Resolve the offered cross-sell: accept it or skip it, then execute.
            if self.upsell and not self._accept_upsell(message):
                self.upsell = None
            self.stage = Stage.EXECUTE
            return AgentReply(
                text="Great — placing your order now.",
                stage=Stage.EXECUTE,
                success=True,
                trace_id=tid,
                policy=self._policy_payload(policy),
            )
        # Ambiguous -> could be a re-spec or a different product
        policy = self._evaluate_policy(tid, self.selected, self._current_price())
        return AgentReply(
            text=f"Just to confirm — you want {self._describe(self.selected)}? Reply yes to place the order, or tell me to change anything.",
            stage=Stage.CONFIRM,
            success=True,
            trace_id=tid,
            policy=self._policy_payload(policy),
        )

    # ---- execution ----

    async def _execute_order(self, tid: str) -> AgentReply:
        if not self.selected:
            return self._fail(tid, "No product selected.")

        quantity = 1
        if self.intent and self.intent.quantity:
            q = self.intent.quantity.lower()
            # fractional/half sizes are baked into the product, treat as qty 1
            if "." in q or "half" in q or "quarter" in q or "pc" in q:
                quantity = 1
            else:
                digits = "".join(re.findall(r"\d+", q))
                if digits:
                    try:
                        quantity = max(1, int(digits))
                    except ValueError:
                        quantity = 1

        items = [
            CartItem(
                item_id=self.selected.item_id,
                name=self.selected.name,
                quantity=quantity,
                price=self.selected.price,
                merchant_id=self.selected.merchant_id,
            )
        ]
        upsell = self.upsell
        if upsell is not None:
            items.append(
                CartItem(
                    item_id=upsell.item_id,
                    name=upsell.name,
                    quantity=1,
                    price=upsell.price,
                    merchant_id=upsell.merchant_id,
                )
            )

        # Create order
        sid = tracer.start_span(
            tid, "create_order", span_type="TOOL",
            input={"item": self.selected.item_id, "quantity": quantity, "price": self.selected.price, "upsell": upsell.item_id if upsell else None},
        )
        try:
            order = await self.order_service.create_order(items=items, merchant_id=self.selected.merchant_id)
        except Exception as e:
            tracer.end_span(tid, sid, status="error", output={"error": str(e)})
            return self._fail(tid, "Failed to create the order with the payment provider. Please try again.")
        tracer.end_span(tid, sid, output={"order_id": order.order_id, "amount": order.amount})

        # Process payment with failure recovery (card_declined -> UPI, once)
        method = self.payment_method
        attempts = 1
        recovered = False
        try:
            payment = await self._pay(tid, order, method)
        except Exception as e:
            return self._fail(
                tid,
                f"Payment could not be processed right now ({e}). Please try again in a moment.",
            )

        while (
            payment.status == PaymentStatus.FAILED
            and payment.error_code == "card_declined"
            and method != PaymentMethod.UPI
            and attempts < settings.max_retries
        ):
            method = PaymentMethod.UPI
            attempts += 1
            recovered = True
            try:
                payment = await self._pay(tid, order, method)
            except Exception:
                break

        self.stage = Stage.DONE
        latency = self._turn_latency()

        if payment.status == PaymentStatus.SUCCESS:
            # record the money moved + recovery for the merchant dashboard
            metrics_tracker.record(
                outcome="recovered" if recovered else "success",
                order_id=order.order_id,
                item=self.selected.name,
                amount_paise=order.amount,
                method=method.value,
                recovered_from="card_declined" if recovered else None,
                latency_ms=latency,
            )
            self.policy.record_spend(order.amount)
            if recovered:
                text = (
                    f"Your card was declined, so I retried with UPI and it succeeded. "
                    f"Order confirmed! Payment of \u20b9{self._rupees(order.amount):,} recovered via UPI."
                )
            else:
                text = f"Order confirmed! Payment of \u20b9{self._rupees(order.amount):,} succeeded via {method.value.upper()}."
            self.final_reply = AgentReply(
                text=text,
                stage=Stage.DONE,
                success=True,
                order_id=order.order_id,
                amount=order.amount,
                currency=order.currency,
                payment_link=payment.alias,
                trace_id=tid,
                payment_status=payment.status.value,
                product_name=self.selected.name,
                product_summary=self._describe(self.selected),
                product_emoji=self.selected.emoji,
                latency_ms=latency,
            )
            return self.final_reply

        # Give up gracefully
        metrics_tracker.record(
            outcome="failed",
            order_id=order.order_id,
            item=self.selected.name,
            amount_paise=order.amount,
            method=method.value,
            latency_ms=latency,
        )
        self.final_reply = AgentReply(
            text=f"Payment failed after {attempts} attempt(s): {payment.error_description}. Please try a different payment method.",
            stage=Stage.DONE,
            success=False,
            order_id=order.order_id,
            trace_id=tid,
            payment_status=payment.status.value,
            error=payment.error_description,
            product_name=self.selected.name,
            product_emoji=self.selected.emoji,
            latency_ms=latency,
        )
        return self.final_reply

    async def _pay(self, tid: str, order, method: PaymentMethod):
        card_details = None
        upi_id = None
        if method == PaymentMethod.CARD:
            card_details = {"number": "4111111111111111", "exp_month": 12, "exp_year": 2026, "cvv": "123"}
        elif method == PaymentMethod.UPI:
            upi_id = "success@razorpay"

        sid = tracer.start_span(
            tid, "process_payment", span_type="TOOL",
            input={"order_id": order.order_id, "amount": order.amount, "method": method.value},
        )
        payment = await self.payment_service.create_payment(
            order=order, method=method, card_details=card_details, upi_id=upi_id,
        )
        # honest audit: a failed money action is recorded as an error span, not a success
        span_status = "error" if payment.status == PaymentStatus.FAILED else "completed"
        tracer.end_span(tid, sid, status=span_status, output={
            "payment_id": payment.payment_id,
            "status": payment.status.value,
            "error_code": payment.error_code,
            "error_description": payment.error_description,
            "method": method.value,
        })
        return payment

    # ---- helpers ----

    def _current_price(self) -> int:
        if not self.selected:
            return 0
        return self.selected.price

    def _approval_granted(self, message: str) -> bool:
        m = message.lower().strip()
        if "approve" in m or "approved" in m or "authorize" in m or "yes" in m and "approve" in m:
            self.approval_granted = True
            return True
        return False

    def _no_match_text(self, query: str) -> str:
        return f"Sorry, I couldn't find a product matching \"{query}\". Try asking for apples, bread, bandages, ice cream cake, or an iPhone 16."

    def _confirm_reply(self, tid: str, product) -> AgentReply:
        amount = product.price  # qty 1 baked into size for variants
        policy = self._evaluate_policy(tid, product, amount)
        suffix = ""
        if policy.requires_approval:
            suffix = " (approval required)"
        elif policy.over_budget:
            suffix = " (over budget)"
        text = f"Here's what I have: {self._describe(product)}. Shall I place the order{suffix}?"
        if policy.reason:
            text += f" {policy.reason}"
        if policy.suggested_actions:
            text += " " + " ".join(policy.suggested_actions)

        # Cross-sell: only for auto-approved, in-budget orders (growth half of Track 01).
        upsell = None
        if not policy.requires_approval and not policy.over_budget:
            upsell = self._find_upsell(product)
            if upsell:
                text += (f" While you're at it, could I add a {self._describe(upsell)} "
                         f"(+\u20b9{self._rupees(upsell.price):,})?")
        self.upsell = upsell  # remember the offered cross-sell for the next turn

        return AgentReply(
            text=text,
            stage=Stage.CONFIRM,
            success=True,
            trace_id=tid,
            product_name=product.name,
            product_summary=self._describe(product),
            product_emoji=product.emoji,
            policy=self._policy_payload(policy),
            latency_ms=self._turn_latency(),
            upsell_item_id=upsell.item_id if upsell else None,
            upsell_label=self._describe(upsell) if upsell else None,
            upsell_price=upsell.price if upsell else None,
        )

    def _find_upsell(self, product) -> Optional:
        """Pick a single, complementary, budget-bounded cross-sell for the item."""
        if not product or not self.policy:
            return None
        category = (product.category or "").lower()
        # map main item -> candidate accessory item ids (curated, bounded)
        target = None
        if "electronics" in category and "iphone" in product.name.lower():
            target = self.catalog.get_product("earbuds_1")
        elif "electronics" in category and "phone" in product.name.lower():
            target = self.catalog.get_product("earbuds_1")
        elif "food" in category and "cake" in product.name.lower():
            target = self.catalog.get_product("brownie_1")
        elif "food" in category and "coffee" in product.name.lower():
            target = self.catalog.get_product("tea_250g")
        if not target:
            return None
        # bounded: the add-on must fit the remaining budget and be substantially
        # smaller than the main purchase (no surprise bill inflation).
        remaining = self.policy.remaining_budget
        if target.price > remaining or target.price > product.price:
            return None
        return target

    def _accept_upsell(self, message: str) -> bool:
        m = message.lower()
        if any(k in m for k in ("add", "sure", "why not", "yes add", "go for it")):
            return True
        if self.upsell is not None and self.upsell.name and self.upsell.name.lower() in m:
            return True
        return False


    def _evaluate_policy(self, tid: str, product, amount_paise: int):
        sid = tracer.start_span(tid, "policy_check", span_type="TOOL", input={
            "item": product.item_id, "price": amount_paise, "method": self.payment_method.value,
        })
        policy = self.policy.evaluate(amount_paise, self.payment_method, merchant_rule_hint="no-discount-beyond-15%")
        tracer.end_span(tid, sid, output={
            "approved": policy.approved,
            "requires_approval": policy.requires_approval,
            "over_budget": policy.over_budget,
            "remaining_budget": policy.remaining_budget,
            "reason": policy.reason,
            "decisions": policy.decisions,
        })
        return policy

    def _policy_payload(self, p) -> PolicyPayload:
        return PolicyPayload(
            approved=p.approved,
            requires_approval=p.requires_approval,
            over_budget=p.over_budget,
            reason=p.reason,
            remaining_budget=p.remaining_budget,
            suggested_actions=list(p.suggested_actions),
            merchant_rule=p.merchant_rule,
            decisions=list(p.decisions),
        )

    def _turn_latency(self) -> float:
        return round((_time.perf_counter() - self.turn_started) * 1000, 1)

    def _fail(self, tid: str, message: str) -> AgentReply:
        self.stage = Stage.BROWSE
        return AgentReply(
            text=message,
            stage=Stage.BROWSE,
            success=False,
            error=message,
            trace_id=tid,
        )
