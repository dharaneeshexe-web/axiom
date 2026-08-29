from typing import TypedDict, Literal, Optional, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from ..models.schemas import Intent, Product, Order, Payment, PaymentMethod
from ..services.catalog import CatalogService
from ..services.order import OrderService
from ..services.payment import PaymentService
from ..services.razorpay import RazorpayClient
from ..config.settings import settings
from ..config.tracing import tracer
from .intent_parser import IntentParser


class CheckoutState(TypedDict, total=False):
    user_query: str
    intent: Optional[Intent]
    products: List[Product]
    selected_product: Optional[Product]
    order: Optional[Order]
    payment: Optional[Payment]
    error: Optional[str]
    retry_count: int
    payment_method: PaymentMethod
    user_confirmed: bool
    trace_id: Optional[str]


class CheckoutAgent:
    def __init__(self):
        self.razorpay = RazorpayClient()
        self.catalog = CatalogService()
        self.order_service = OrderService(self.razorpay)
        self.payment_service = PaymentService(self.razorpay)
        self.intent_parser = IntentParser()
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(CheckoutState)

        graph.add_node("parse_intent", self._parse_intent)
        graph.add_node("query_catalog", self._query_catalog)
        graph.add_node("select_product", self._select_product)
        graph.add_node("confirm_order", self._confirm_order)
        graph.add_node("create_order", self._create_order)
        graph.add_node("process_payment", self._process_payment)
        graph.add_node("handle_failure", self._handle_failure)
        graph.add_node("complete", self._complete)

        graph.set_entry_point("parse_intent")

        graph.add_conditional_edges(
            "parse_intent",
            self._route_after_parse,
            {"catalog": "query_catalog", "error": "complete"},
        )
        graph.add_conditional_edges(
            "query_catalog",
            self._route_after_catalog,
            {"select": "select_product", "not_found": "complete"},
        )
        graph.add_conditional_edges(
            "select_product",
            self._route_after_select,
            {"confirm": "confirm_order", "error": "complete"},
        )
        graph.add_conditional_edges(
            "confirm_order",
            self._route_after_confirm,
            {"order": "create_order", "cancel": "complete"},
        )
        graph.add_conditional_edges(
            "create_order",
            self._route_after_order,
            {"payment": "process_payment", "error": "complete"},
        )
        graph.add_conditional_edges(
            "process_payment",
            self._route_after_payment,
            {"success": "complete", "failure": "handle_failure"},
        )
        graph.add_conditional_edges(
            "handle_failure",
            self._route_after_failure,
            {"retry": "process_payment", "give_up": "complete"},
        )

        graph.add_edge("complete", END)

        return graph.compile(checkpointer=self.checkpointer)

    async def _parse_intent(self, state: CheckoutState) -> dict:
        tid = state.get("trace_id")
        sid = tracer.start_span(tid, "parse_intent", input={"query": state.get("user_query", "")}) if tid else None
        intent = await self.intent_parser.parse(state.get("user_query", ""))
        if sid and tid:
            tracer.end_span(tid, sid, output=intent.model_dump() if intent else None)
        return {"intent": intent}

    async def _query_catalog(self, state: CheckoutState) -> dict:
        tid = state.get("trace_id")
        intent = state.get("intent")
        query = intent.item if intent else None
        merchant = intent.merchant if intent else None
        products = self.catalog.search_products(query=query, merchant_id=merchant)
        if tid:
            sid = tracer.start_span(tid, "query_catalog", input={"query": query})
            tracer.end_span(tid, sid, output=[p.model_dump() for p in products])
        return {"products": products}

    async def _select_product(self, state: CheckoutState) -> dict:
        tid = state.get("trace_id")
        products = state.get("products", [])
        if not products:
            if tid:
                sid = tracer.start_span(tid, "select_product")
                tracer.end_span(tid, sid, status="error", output={"error": "No products found matching your request"})
            return {"error": "No products found matching your request"}

        intent = state.get("intent")
        if not intent:
            if tid:
                sid = tracer.start_span(tid, "select_product")
                tracer.end_span(tid, sid, status="error", output={"error": "Could not understand your request"})
            return {"error": "Could not understand your request"}

        filtered = products
        if intent.color:
            color_lower = intent.color.lower()
            filtered = [p for p in filtered if p.color and color_lower in p.color.lower()]
        if intent.storage:
            storage_lower = intent.storage.lower()
            filtered = [p for p in filtered if p.storage and storage_lower in p.storage.lower()]
        if intent.size:
            size_lower = intent.size.lower()
            filtered = [p for p in filtered if p.size and size_lower in p.size.lower()]
        if intent.flavor:
            flavor_lower = intent.flavor.lower()
            filtered = [p for p in filtered if p.flavor and flavor_lower in p.flavor.lower()]

        if filtered:
            sel = filtered[0]
            if tid:
                sid = tracer.start_span(tid, "select_product", input={"intent": intent.model_dump()})
                tracer.end_span(tid, sid, output={"selected": sel.item_id, "name": sel.name, "price": sel.price, "filters_applied": intent.model_dump()})
            return {"selected_product": sel}
        if tid:
            sid = tracer.start_span(tid, "select_product", input={"intent": intent.model_dump()})
            tracer.end_span(tid, sid, output={"selected": products[0].item_id, "name": products[0].name})
        return {"selected_product": products[0]}

    async def _confirm_order(self, state: CheckoutState) -> dict:
        tid = state.get("trace_id")
        sel = state.get("selected_product")
        if tid:
            sid = tracer.start_span(tid, "user_confirmation", input={
                "product": sel.name if sel else None,
                "price": sel.price if sel else None,
                "amount": (sel.price if sel else 0),
            })
            tracer.end_span(tid, sid, output={"confirmed": True, "mode": "auto"})
        return {"user_confirmed": True}

    async def _create_order(self, state: CheckoutState) -> dict:
        from ..models.schemas import CartItem

        tid = state.get("trace_id")
        product = state.get("selected_product")
        if not product:
            if tid:
                sid = tracer.start_span(tid, "create_order")
                tracer.end_span(tid, sid, status="error", output={"error": "No product selected"})
            return {"error": "No product selected"}

        quantity = 1
        intent = state.get("intent")
        if intent and intent.quantity:
            q = intent.quantity.lower()
            if "." in q or "half" in q or "quarter" in q or "pc" in q:
                quantity = 1
            else:
                digits = "".join(filter(str.isdigit, q))
                if digits:
                    try:
                        quantity = max(1, int(digits))
                    except ValueError:
                        quantity = 1

        items = [
            CartItem(
                item_id=product.item_id,
                name=product.name,
                quantity=quantity,
                price=product.price,
                merchant_id=product.merchant_id,
            )
        ]

        if tid:
            sid = tracer.start_span(
                tid, "create_order",
                span_type="TOOL",
                input={"item": product.item_id, "name": product.name, "quantity": quantity, "price": product.price},
            )
            try:
                order = await self.order_service.create_order(items=items, merchant_id=product.merchant_id)
                tracer.end_span(tid, sid, output={
                    "order_id": order.order_id,
                    "amount": order.amount,
                    "currency": order.currency,
                })
            except Exception as e:
                tracer.end_span(tid, sid, status="error", output={"error": str(e)})
                return {"error": "Failed to create order with payment provider. Please try again."}
        else:
            try:
                order = await self.order_service.create_order(items=items, merchant_id=product.merchant_id)
            except Exception:
                return {"error": "Failed to create order with payment provider. Please try again."}
        return {"order": order}

    async def _process_payment(self, state: CheckoutState) -> dict:
        tid = state.get("trace_id")
        order = state.get("order")
        if not order:
            if tid:
                sid = tracer.start_span(tid, "process_payment")
                tracer.end_span(tid, sid, status="error", output={"error": "No order to process payment for"})
            return {"error": "No order to process payment for"}

        payment_method = state.get("payment_method") or PaymentMethod.CARD

        card_details = None
        upi_id = None

        if payment_method == PaymentMethod.CARD:
            card_details = {
                "number": "4111111111111111",
                "exp_month": 12,
                "exp_year": 2026,
                "cvv": "123",
            }
        elif payment_method == PaymentMethod.UPI:
            upi_id = "success@razorpay"

        if tid:
            sid = tracer.start_span(
                tid,
                "process_payment",
                span_type="TOOL",
                input={
                    "order_id": order.order_id,
                    "amount": order.amount,
                    "method": payment_method.value,
                    "attempt": state.get("retry_count", 0) + 1,
                },
            )
            payment = await self.payment_service.create_payment(
                order=order, method=payment_method, card_details=card_details, upi_id=upi_id,
            )
            tracer.end_span(tid, sid, output={
                "payment_id": payment.payment_id,
                "status": payment.status.value,
                "error_code": payment.error_code,
                "error_description": payment.error_description,
            })
        else:
            payment = await self.payment_service.create_payment(
                order=order, method=payment_method, card_details=card_details, upi_id=upi_id,
            )
        return {"payment": payment, "payment_method": payment_method}

    async def _handle_failure(self, state: CheckoutState) -> dict:
        tid = state.get("trace_id")
        payment = state.get("payment")
        if not payment:
            if tid:
                sid = tracer.start_span(tid, "handle_payment_failure")
                tracer.end_span(tid, sid, status="error", output={"error": "No payment information available"})
            return {"error": "No payment information available"}

        retry_count = state.get("retry_count", 0) + 1

        if retry_count >= settings.max_retries:
            out = {
                "retry_count": retry_count,
                "error": f"Payment failed after {retry_count} attempts: {payment.error_description}",
            }
            if tid:
                sid = tracer.start_span(tid, "handle_payment_failure", input={
                    "error_code": payment.error_code,
                    "error_description": payment.error_description,
                    "attempt": retry_count,
                })
                tracer.end_span(tid, sid, status="error", output=out)
            return out

        action = "retry"
        detail = payment.error_description

        if payment.error_code == "card_declined":
            action = "switch_to_upi"
            detail = "Card declined. Switching payment method to UPI."
            result = {"retry_count": retry_count, "payment_method": PaymentMethod.UPI}
        elif payment.error_code == "insufficient_funds":
            result = {
                "retry_count": retry_count,
                "error": "Insufficient funds. Please try a different payment method.",
            }
        elif payment.error_code == "expired_card":
            result = {
                "retry_count": retry_count,
                "error": "Your card has expired. Please update your card details.",
            }
        elif payment.error_code == "processing_error":
            if retry_count < settings.max_retries:
                result = {"retry_count": retry_count}
            else:
                result = {
                    "retry_count": retry_count,
                    "error": "Processing error. Please try again later.",
                }
        elif payment.error_code == "invalid_vpa":
            result = {
                "retry_count": retry_count,
                "error": "Invalid UPI ID. Please check and try again.",
            }
        else:
            result = {"retry_count": retry_count}

        if tid:
            sid = tracer.start_span(tid, "handle_payment_failure", input={
                "error_code": payment.error_code,
                "error_description": payment.error_description,
                "action_taken": action,
                "explanation": detail,
                "attempt": retry_count,
            })
            tracer.end_span(tid, sid, output=result)
        return result

    async def _complete(self, state: CheckoutState) -> dict:
        return {}

    def _route_after_parse(self, state: CheckoutState) -> Literal["catalog", "error"]:
        intent = state.get("intent")
        if intent and intent.item:
            return "catalog"
        return "error"

    def _route_after_catalog(self, state: CheckoutState) -> Literal["select", "not_found"]:
        if state.get("products"):
            return "select"
        return "not_found"

    def _route_after_select(self, state: CheckoutState) -> Literal["confirm", "error"]:
        if state.get("selected_product"):
            return "confirm"
        return "error"

    def _route_after_confirm(self, state: CheckoutState) -> Literal["order", "cancel"]:
        if state.get("user_confirmed"):
            return "order"
        return "cancel"

    def _route_after_order(self, state: CheckoutState) -> Literal["payment", "error"]:
        if state.get("order"):
            return "payment"
        return "error"

    def _route_after_payment(self, state: CheckoutState) -> Literal["success", "failure"]:
        payment = state.get("payment")
        if payment and payment.status.value == "success":
            return "success"
        return "failure"

    def _route_after_failure(self, state: CheckoutState) -> Literal["retry", "give_up"]:
        if state.get("retry_count", 0) < settings.max_retries:
            return "retry"
        return "give_up"

    async def run(self, user_query: str, payment_method: PaymentMethod = PaymentMethod.CARD, trace_id: Optional[str] = None) -> dict:
        initial_state: CheckoutState = {
            "user_query": user_query,
            "payment_method": payment_method,
            "retry_count": 0,
            "products": [],
            "user_confirmed": True,
            "trace_id": trace_id,
        }

        import uuid as _uuid
        thread_id = trace_id or f"thread_{_uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": thread_id}}
        final_state = await self.graph.ainvoke(initial_state, config=config)

        return final_state
