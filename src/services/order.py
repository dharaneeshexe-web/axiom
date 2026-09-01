import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from ..models.schemas import Order, OrderStatus, CartItem
from .razorpay import RazorpayClient, get_payment_mode


class OrderService:
    def __init__(self, razorpay: RazorpayClient):
        self.razorpay = razorpay
        self.orders: Dict[str, Order] = {}

    async def create_order(
        self,
        items: List[CartItem],
        merchant_id: str,
        customer_id: Optional[str] = None,
    ) -> Order:
        total_amount = sum(item.price * item.quantity for item in items)

        # Simulate mode: never touch the real Razorpay API (protects quotas during demos).
        if get_payment_mode() == "simulate":
            order = Order(
                order_id=f"ord_sim_{uuid.uuid4().hex[:8]}",
                amount=total_amount,
                currency="INR",
                status=OrderStatus.CREATED,
                items=items,
                merchant_id=merchant_id,
                customer_id=customer_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self.orders[order.order_id] = order
            return order

        razorpay_order = await self.razorpay.create_order({
            "amount": total_amount,
            "currency": "INR",
            "receipt": f"order_{uuid.uuid4().hex[:8]}",
            "notes": {
                "merchant_id": merchant_id,
                "item_count": str(len(items)),
            },
        })

        order = Order(
            order_id=razorpay_order["id"],
            amount=total_amount,
            currency="INR",
            status=OrderStatus.CREATED,
            items=items,
            merchant_id=merchant_id,
            customer_id=customer_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.orders[order.order_id] = order
        return order

    async def get_order(self, order_id: str) -> Optional[Order]:
        if order_id in self.orders:
            return self.orders[order_id]
        
        try:
            razorpay_order = await self.razorpay.fetch_order(order_id)
            order = Order(
                order_id=razorpay_order["id"],
                amount=razorpay_order["amount"],
                currency=razorpay_order["currency"],
                status=OrderStatus(razorpay_order["status"]),
                items=[],
                merchant_id=razorpay_order.get("notes", {}).get("merchant_id", ""),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self.orders[order_id] = order
            return order
        except Exception:
            return None

    async def update_order_status(
        self, order_id: str, status: OrderStatus
    ) -> Optional[Order]:
        if order_id in self.orders:
            self.orders[order_id].status = status
            self.orders[order_id].updated_at = datetime.utcnow()
            return self.orders[order_id]
        return None

    async def cancel_order(self, order_id: str) -> Optional[Order]:
        return await self.update_order_status(order_id, OrderStatus.CANCELLED)
