import asyncio
from src.agent.workflow import CheckoutAgent
from src.models.schemas import PaymentMethod
from src.config.tracing import tracer
from src.config.settings import settings
from src.services.payment import PaymentService
from src.services.razorpay import RazorpayClient

async def main():
    # Force card_declined simulation for this test
    settings.demo_failure = "card_declined"
    print("DEMO_FAILURE =", settings.demo_failure)
    agent = CheckoutAgent()
    tracer._ensure_initialized()
    tid = tracer.start_trace("test_fail_trace")
    final = await agent.run("Place an order for iPhone 16, Blue, 256GB", PaymentMethod.CARD, trace_id=tid)
    order = final.get("order")
    payment = final.get("payment")
    print("SUCCESS:", final.get("error") is None)
    print("ORDER:", order.order_id if order else None)
    print("PAYMENT:", payment.status.value if payment else None, "| code:", payment.error_code if payment else None)
    print("FINAL PAYMENT_METHOD:", final.get("payment_method"))
    print("SPANS:", [s["name"] for s in tracer.get_trace(tid)])
    # Confirm recovery happened: payment_method changed to UPI and payment succeeded
    print("RECOVERED_VIA_UPI:", final.get("payment_method") == PaymentMethod.UPI)

asyncio.run(main())
