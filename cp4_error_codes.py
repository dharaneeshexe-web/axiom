import asyncio
from src.agent.workflow import CheckoutAgent
from src.models.schemas import PaymentMethod
from src.config.tracing import tracer
from src.config.settings import settings

SCENARIOS = [
    ("card_declined", "RECOVERY_TO_UPI"),
    ("insufficient_funds", "GRACEFUL_GIVE_UP"),
    ("expired_card", "GRACEFUL_GIVE_UP"),
    ("processing_error", "GRACEFUL_GIVE_UP"),
]

async def main():
    tracer._ensure_initialized()
    for scenario, expected in SCENARIOS:
        # fresh agent per scenario so PaymentService picks up the scenario
        settings.demo_failure = scenario
        agent = CheckoutAgent()
        tid = tracer.start_trace(f"cp4_{scenario}")
        final = await agent.run("Place an order for iPhone 16, Blue, 256GB", PaymentMethod.CARD, trace_id=tid)
        payment = final.get("payment")
        error = final.get("error")
        pm = final.get("payment_method")

        print(f"\n=== {scenario} ===")
        print(f"  error_present: {error is not None}")
        print(f"  final_payment_status: {payment.status.value if payment else None}")
        print(f"  final_payment_code: {payment.error_code if payment else None}")
        print(f"  final_method: {pm.value if pm else None}")
        if error:
            print(f"  graceful_message: {error[:80]}")
        # trace names
        print(f"  spans: {' -> '.join(s['name'] for s in tracer.get_trace(tid))}")
        # assertion helper
        if expected == "RECOVERY_TO_UPI" and payment and payment.status.value == "success" and pm == PaymentMethod.UPI:
            print("  RESULT: PASS RECOVERED VIA UPI")
        elif expected == "GRACEFUL_GIVE_UP" and error is not None:
            print("  RESULT: PASS GRACEFUL FAILURE (no crash)")
        else:
            print(f"  RESULT: NOTE unexpected (expected {expected})")

asyncio.run(main())

