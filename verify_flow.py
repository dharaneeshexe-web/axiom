import asyncio
import traceback
from src.agent.workflow import CheckoutAgent
from src.models.schemas import PaymentMethod
from src.config.tracing import tracer, _LMNR_AVAILABLE

async def main():
    print("LMNR available:", _LMNR_AVAILABLE)
    tracer._ensure_initialized()
    tid = tracer.start_trace("test_trace")
    sid = tracer.start_span(tid, "checkout_request", input={"query": "test"}, span_type="DEFAULT")
    agent = CheckoutAgent()
    final = await agent.run("Place an order for iPhone 16, Blue, 256GB", PaymentMethod.CARD, trace_id=tid)
    order = final.get("order")
    payment = final.get("payment")
    print("SUCCESS:", final.get("error") is None)
    print("ORDER:", order.order_id if order else None, order.amount if order else None)
    print("PAYMENT:", payment.status.value if payment else None, payment.payment_id if payment else None)
    print("PAYMENT_LINK:", payment.alias if payment else None)
    tracer.end_span(tid, sid)
    print("SPANS:", [s["name"] for s in tracer.get_trace(tid)])

asyncio.run(main())
