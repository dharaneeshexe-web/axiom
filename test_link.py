import asyncio
from src.services.razorpay import RazorpayClient

async def main():
    c = RazorpayClient()
    # 1. create order
    try:
        order = await c.create_order({"amount": 100, "currency": "INR", "receipt": "test-6001"})
        print("ORDER:", order["id"])
    except Exception as e:
        print("ORDER ERR:", str(e)[:200])
        return
    # 2. create payment link
    try:
        link = await c.create_payment_link({
            "amount": 100,
            "currency": "INR",
            "description": "test",
            "callback_url": "https://example.com/callback",
            "callback_method": "get",
        })
        print("PAYMENT LINK OK:", link.get("id"), link.get("short_url"))
    except Exception as e:
        print("LINK ERR:", str(e)[:300])

asyncio.run(main())
