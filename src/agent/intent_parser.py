import asyncio
import json
from typing import Optional
from groq import Groq, RateLimitError
from ..models.schemas import Intent, PaymentMethod
from ..config.settings import settings
from ..config.tracing import _LMNR_AVAILABLE

if _LMNR_AVAILABLE:
    from lmnr import Laminar


class IntentParser:
    def __init__(self):
        self.keys = settings.groq_key_list
        self.current_key_index = 0
        self.model = settings.groq_model
        self.client = Groq(api_key=self.keys[self.current_key_index])

    def _rotate_key(self) -> Groq:
        self.current_key_index = (self.current_key_index + 1) % len(self.keys)
        return Groq(api_key=self.keys[self.current_key_index])

    async def parse(self, user_query: str) -> Intent:
        system_prompt = """You are an intent parser for a shopping assistant.
Parse the user's query into structured data.

Return a JSON object with these fields:
- item: the product name/type (string or null)
- quantity: the quantity (string or null, e.g., "2kg", "1l", "12")
- merchant: the merchant name (string or null)
- payment_method: one of "card", "upi", "netbanking" (string or null)
- color: the color/variant (string or null, e.g., "black", "blue", "pink")
- storage: the storage size for electronics (string or null, e.g., "128GB", "256GB")
- size: the size for clothing/bandages (string or null, e.g., "small", "medium", "large")
- flavor: the flavor for food (string or null, e.g., "chocolate", "vanilla")

Examples:
User: "Buy 2kg of apples from FreshCart"
{"item": "apples", "quantity": "2kg", "merchant": "FreshCart", "payment_method": null, "color": null, "storage": null, "size": null, "flavor": null}

User: "Place an order for iPhone 16, Blue, 256GB"
{"item": "iphone 16", "quantity": "1", "merchant": null, "payment_method": null, "color": "blue", "storage": "256GB", "size": null, "flavor": null}

User: "I need crepe bandages for a sprain, small size, 2 pack"
{"item": "crepe bandage", "quantity": "2", "merchant": null, "payment_method": null, "color": null, "storage": null, "size": "small", "flavor": null}

User: "Order a chocolate ice cream cake, half kg, for a birthday"
{"item": "ice cream cake", "quantity": "0.5kg", "merchant": null, "payment_method": null, "color": null, "storage": null, "size": null, "flavor": "chocolate"}

User: "Get me a loaf of bread with UPI"
{"item": "bread", "quantity": "1", "merchant": null, "payment_method": "upi", "color": null, "storage": null, "size": null, "flavor": null}

Only return the JSON object, no other text."""

        max_attempts = len(self.keys) * 2
        attempt = 0

        while attempt < max_attempts:
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query},
                ]

                def _call():
                    import asyncio

                    async def _inner():
                        return await asyncio.to_thread(
                            lambda: self.client.chat.completions.create(
                                model=self.model,
                                messages=messages,
                                temperature=0.1,
                                max_tokens=200,
                            )
                        )

                    return _inner()

                if _LMNR_AVAILABLE:
                    with Laminar.start_as_current_span(
                        name="groq_intent_parse",
                        input=messages,
                        span_type="LLM",
                        metadata={"model": self.model},
                    ):
                        response = await _call()
                        content = response.choices[0].message.content.strip()
                        try:
                            Laminar.set_span_output(content)
                        except Exception:
                            pass
                else:
                    response = await _call()
                    content = response.choices[0].message.content.strip()

                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

                parsed = json.loads(content)

                payment_method = None
                if parsed.get("payment_method"):
                    try:
                        payment_method = PaymentMethod(parsed["payment_method"])
                    except ValueError:
                        payment_method = None

                item = parsed.get("item")
                # Multi-item query: keep only the first item (agent orders one at a time)
                if isinstance(item, str) and item:
                    item = item.split(",")[0].strip()
                    if " and " in item:
                        item = item.split(" and ")[0].strip()

                return Intent(
                    raw_query=user_query,
                    item=item,
                    quantity=parsed.get("quantity"),
                    merchant=parsed.get("merchant"),
                    payment_method=payment_method,
                    color=parsed.get("color"),
                    storage=parsed.get("storage"),
                    size=parsed.get("size"),
                    flavor=parsed.get("flavor"),
                )

            except RateLimitError:
                attempt += 1
                if attempt < max_attempts:
                    self.client = self._rotate_key()
                    await asyncio.sleep(0.5)
                continue

            except Exception:
                break

        return Intent(
            raw_query=user_query,
            item=None,
            quantity=None,
            merchant=None,
            payment_method=None,
            color=None,
            storage=None,
            size=None,
            flavor=None,
        )
