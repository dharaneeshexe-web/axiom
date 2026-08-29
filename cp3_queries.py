import asyncio
from src.agent.intent_parser import IntentParser
from src.services.catalog import CatalogService

QUERIES = [
    ("Buy 2kg apples", "apples"),
    ("I need crepe bandages", "crepe bandage"),
    ("Order an ice cream cake", "ice cream cake"),
    ("Place an order for iPhone 16", "iphone 16"),
    ("Get me milk", "milk"),
    ("Buy bread and eggs", None),  # multiple items - agent picks one
    ("I want tomatoes", "tomato"),
    ("Send me rice", "rice"),
    ("Buy bananas using UPI", "banana"),
    ("Get iPhone 16 Blue", "iphone 16"),
    ("I need bandages for sprain", "bandage"),
    ("Chocolate cake half kg", "cake"),
    ("Buy iPhone 16 with card", "iphone 16"),
    ("Get me farm eggs", "egg"),
    ("I want basmati rice 1kg", "rice"),
    ("Order whole wheat bread", "bread"),
    ("Buy fresh tomatoes 2kg", "tomato"),
    ("Get ripe bananas 1kg", "banana"),
    ("I need pasteurized milk 1l", "milk"),
    ("Buy apples and bananas", None),  # multiple items
]

async def main():
    parser = IntentParser()
    catalog = CatalogService()
    passed = 0
    total = len(QUERIES)
    fails = []

    for i, (q, expected) in enumerate(QUERIES, 1):
        try:
            intent = await parser.parse(q)
        except Exception as e:
            fails.append((i, q, f"EXCEPTION: {e}"))
            continue

        item = intent.item
        if item is None:
            fails.append((i, q, f"item is None"))
            continue

        # catalog match
        products = catalog.search_products(query=item, merchant_id=intent.merchant)
        if not products:
            fails.append((i, q, f"parse item='{item}' but NO catalog match"))
            continue

        # hallucination check: parsed item must hit catalog
        passed += 1
        print(f"[{i:>2}] PASS  q='{q}' -> item='{item}'  ({len(products)} products)")

    # multiple-item queries: report as info only (agent handles one)
    print("\n--- SUMMARY ---")
    print(f"Passed {passed}/{total} ({(passed/total)*100:.1f}%)")
    if fails:
        print("\nFAILURES:")
        for i, q, reason in fails:
            print(f"  [{i}] q='{q}' :: {reason}")
    print("\nThreshold: 18/20 (90%).")

asyncio.run(main())
