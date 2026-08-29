import asyncio
import aiohttp

QUERIES = [
    "Buy 2kg apples",
    "I need crepe bandages",
    "Order an ice cream cake",
    "Get me milk",
    "Get iPhone 16 Blue",
    "I want tomatoes",
    "Get me farm eggs",
    "I need bandages for sprain",
    "Buy fresh tomatoes 2kg",
    "Chocolate cake half kg",
]

async def send(session, q, i):
    try:
        async with session.post(
            "http://localhost:8000/checkout",
            json={"query": q, "payment_method": "card"},
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            data = await resp.json()
            return i, resp.status, data.get("success"), data.get("error")
    except Exception as e:
        return i, -1, None, str(e)

async def main():
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[send(session, q, i) for i, q in enumerate(QUERIES)])
    ok = 0
    for i, status, success, err in results:
        if status == 200 and success:
            ok += 1
            print(f"[{i+1:>2}] PASS http={status} success=True")
        else:
            print(f"[{i+1:>2}] FAIL http={status} success={success} err={err}")
    print(f"\nRESPONDED OK: {ok}/{len(QUERIES)}")
    print("THRESHOLD: all return valid response (success or graceful failure), no crash")

asyncio.run(main())
