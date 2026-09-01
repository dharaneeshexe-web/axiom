import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from ..models.schemas import Payment, PaymentStatus, PaymentMethod, Order
from .razorpay import RazorpayClient, get_payment_mode
from ..config.settings import settings


class PaymentService:
    def __init__(self, razorpay: RazorpayClient):
        self.razorpay = razorpay
        self.payments: Dict[str, Payment] = {}
        self.demo_failure = settings.demo_failure.lower() or "none"
        self._declined_tried = False

    async def create_payment(
        self,
        order: Order,
        method: PaymentMethod,
        card_details: Optional[Dict[str, Any]] = None,
        upi_id: Optional[str] = None,
    ) -> Payment:
        # Deterministic demo failure simulation (models real Razorpay error responses)
        if self.demo_failure != "none":
            # card_declined recovers on UPI retry
            if self.demo_failure == "card_declined" and self._declined_tried and method == PaymentMethod.UPI:
                payment = Payment(
                    payment_id=f"pay_{uuid.uuid4().hex[:12]}",
                    order_id=order.order_id,
                    amount=order.amount,
                    currency=order.currency,
                    method=method,
                    status=PaymentStatus.SUCCESS,
                    created_at=datetime.utcnow(),
                )
                self.payments[payment.payment_id] = payment
                return payment
            self._declined_tried = True
            return self._simulate_failure(order, method)

        # Simulate mode: NEVER call the real Razorpay API. Protects the daily
        # payment_links quota during repeated demos / spot-checks.
        if get_payment_mode() == "simulate":
            payment = Payment(
                payment_id=f"pay_sim_{uuid.uuid4().hex[:12]}",
                order_id=order.order_id,
                amount=order.amount,
                currency=order.currency,
                method=method,
                status=PaymentStatus.SUCCESS,
                created_at=datetime.utcnow(),
            )
            # simulated payable link so the demo UI still shows a pay action
            payment.alias = f"https://sim.razorpay.example/p/{payment.payment_id}"
            self.payments[payment.payment_id] = payment
            return payment

        # Real flow: create a Razorpay payment link for the order (money-collection surface)
        try:
            link = await self.razorpay.create_payment_link({
                "amount": order.amount,
                "currency": order.currency,
                "description": f"Payment for order {order.order_id}",
                "notes": {
                    "order_id": order.order_id,
                    "merchant_id": order.merchant_id,
                },
            })

            payment = Payment(
                payment_id=link.get("id", f"plink_{uuid.uuid4().hex[:12]}"),
                order_id=order.order_id,
                amount=order.amount,
                currency=order.currency,
                method=method,
                status=PaymentStatus.SUCCESS,
                created_at=datetime.utcnow(),
            )
            # attach link url for the demo/response
            payment.alias = link.get("short_url")
            self.payments[payment.payment_id] = payment
            return payment

        except Exception as e:
            payment = Payment(
                payment_id=f"pay_{uuid.uuid4().hex[:12]}",
                order_id=order.order_id,
                amount=order.amount,
                currency=order.currency,
                method=method,
                status=PaymentStatus.FAILED,
                error_code="link_creation_failed",
                error_description=str(e),
                created_at=datetime.utcnow(),
            )
            self.payments[payment.payment_id] = payment
            return payment

    def _simulate_failure(self, order: Order, method: PaymentMethod) -> Payment:
        scenario = self.demo_failure
        code = "unknown_error"
        desc = "Payment failed"

        if scenario == "card_declined":
            code = "card_declined"
            desc = "Your card was declined"
        elif scenario == "insufficient_funds":
            code = "insufficient_funds"
            desc = "Insufficient funds"
        elif scenario == "expired_card":
            code = "expired_card"
            desc = "Your card has expired"
        elif scenario == "processing_error":
            code = "processing_error"
            desc = "Processing error occurred"
        elif scenario == "invalid_vpa":
            code = "invalid_vpa"
            desc = "Invalid UPI ID"

        payment = Payment(
            payment_id=f"pay_{uuid.uuid4().hex[:12]}",
            order_id=order.order_id,
            amount=order.amount,
            currency=order.currency,
            method=method,
            status=PaymentStatus.FAILED,
            error_code=code,
            error_description=desc,
            created_at=datetime.utcnow(),
        )
        self.payments[payment.payment_id] = payment
        return payment

    async def capture_payment(self, payment_id: str, amount: int) -> Optional[Payment]:
        try:
            await self.razorpay.capture_payment(payment_id, amount)
            if payment_id in self.payments:
                self.payments[payment_id].status = PaymentStatus.SUCCESS
                self.payments[payment_id].captured_at = datetime.utcnow()
                return self.payments[payment_id]
            return None
        except Exception:
            return None

    async def get_payment(self, payment_id: str) -> Optional[Payment]:
        if payment_id in self.payments:
            return self.payments[payment_id]
        return None

    async def refund_payment(self, payment_id: str) -> Optional[Payment]:
        try:
            await self.razorpay.create_refund(payment_id)
            if payment_id in self.payments:
                self.payments[payment_id].status = PaymentStatus.REFUNDED
                return self.payments[payment_id]
            return None
        except Exception:
            return None
