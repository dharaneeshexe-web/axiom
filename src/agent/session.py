import uuid
import re
from enum import Enum
from typing import List, Optional
from dataclasses import dataclass, field

from ..models.schemas import CartItem, Intent, PaymentMethod, PaymentStatus
from ..services.catalog import CatalogService
from ..services.order import OrderService
from ..services.payment import PaymentService
from ..services.razorpay import RazorpayClient
from ..config.settings import settings
from ..config.tracing import tracer
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
class AgentReply:
    text: str
    stage: Stage
    options: List[VariantOption] = field(default_factory=list)
    success: bool = False
    order_id: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    payment_link: Optional[str] = None
    trace_id: Optional[str] = None
    payment_status: Optional[str] = None
    error: Optional[str] = None
    product_name: Optional[str] = None
    product_summary: Optional[str] = None
    product_emoji: Optional[str] = None


class ChatSession:
    """Stateful multi-turn conversational checkout session.

    Stage machine:
      BROWSE -> SELECT -> CONFIRM -> EXECUTE -> DONE
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        self.stage = Stage.BROWSE
        self.candidates: List = []          # Product objects (variants)
        self.selected: Optional = None      # chosen Product
        self.intent: Optional[Intent] = None
        self.payment_method: PaymentMethod = PaymentMethod.CARD
        self.retry_count: int = 0
        self.trace_id: Optional[str] = None
        self.final_reply: Optional[AgentReply] = None

        # wired services per-session so demo failure simulation is deterministic
        self.razorpay = RazorpayClient()
        self.catalog = CatalogService()
        self.order_service = OrderService(self.razorpay)
        self.payment_service = PaymentService(self.razorpay)
        self.intent_parser = IntentParser()

    # ---- internal helpers ----

    def _rupees(self, paise: int) -> int:
        return paise // 100

    def _variant_list(self, products: List) -> List[VariantOption]:
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

    def _pick_from_message(self, message: str, candidates: List) -> Optional:
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

    def _pin_from_intent(self, products: List, intent: Intent) -> Optional:
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
                text=f"Sorry, I couldn't match that. Please pick one of these options.",
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
        if self._deny_requested(message):
            sid = tracer.start_span(tid, "user_confirmation", input={"message": message})
            tracer.end_span(tid, sid, output={"confirmed": False})
            self.stage = Stage.BROWSE
            self.candidates = []
            self.selected = None
            self.intent = None
            return AgentReply(
                text="No problem — the order is cancelled. Is there something else you'd like?",
                stage=Stage.BROWSE,
                success=True,
                trace_id=tid,
            )
        if self._confirm_requested(message):
            sid = tracer.start_span(tid, "user_confirmation", input={"message": message})
            tracer.end_span(tid, sid, output={"confirmed": True, "product": self.selected.name})
            self.stage = Stage.EXECUTE
            return AgentReply(
                text="Great — placing your order now.",
                stage=Stage.EXECUTE,
                success=True,
                trace_id=tid,
            )
        # Ambiguous -> could be a re-spec or a different product
        return AgentReply(
            text=f"Just to confirm — you want {self._describe(self.selected)}? Reply yes to place the order, or tell me to change anything.",
            stage=Stage.CONFIRM,
            success=True,
            trace_id=tid,
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

        # Create order
        sid = tracer.start_span(
            tid, "create_order", span_type="TOOL",
            input={"item": self.selected.item_id, "quantity": quantity, "price": self.selected.price},
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
            try:
                payment = await self._pay(tid, order, method)
            except Exception:
                break

        self.stage = Stage.DONE

        if payment.status == PaymentStatus.SUCCESS:
            self.final_reply = AgentReply(
                text=f"Order confirmed! Payment of \u20b9{self._rupees(order.amount):,} succeeded via {method.value.upper()}.",
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
            )
            return self.final_reply

        # Give up gracefully
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

    def _no_match_text(self, query: str) -> str:
        return f"Sorry, I couldn't find a product matching \"{query}\". Try asking for apples, bread, bandages, ice cream cake, or an iPhone 16."

    def _confirm_reply(self, tid: str, product) -> AgentReply:
        sid = tracer.start_span(tid, "user_confirmation", input={"product": product.name})
        tracer.end_span(tid, sid, output={"confirmed": False, "awaiting": True})
        return AgentReply(
            text=f"Here's what I have: {self._describe(product)}. Shall I place the order?",
            stage=Stage.CONFIRM,
            success=True,
            trace_id=tid,
            product_name=product.name,
            product_summary=self._describe(product),
            product_emoji=product.emoji,
        )

    def _fail(self, tid: str, message: str) -> AgentReply:
        self.stage = Stage.BROWSE
        return AgentReply(
            text=message,
            stage=Stage.BROWSE,
            success=False,
            error=message,
            trace_id=tid,
        )
