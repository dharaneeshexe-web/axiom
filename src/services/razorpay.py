import httpx
import asyncio
import random
from typing import Dict, Any, Optional
from ..config.settings import settings


class RazorpayClient:
    def __init__(self):
        self.base_url = settings.razorpay_base_url
        self.key_id = settings.razorpay_key_id
        self.key_secret = settings.razorpay_key_secret
        self.headers = {
            "Content-Type": "application/json",
        }
        self._semaphore = asyncio.Semaphore(1)

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        max_attempts = max(1, settings.max_retries + 1)
        attempt = 0
        # Transient statuses worth a retry with backoff. Everything else (e.g. 401/400/403)
        # is terminal and must fail immediately for the caller to handle gracefully.
        transient = (429, 500, 502, 503, 504)

        while attempt < max_attempts:
            attempt += 1
            try:
                async with self._semaphore:
                    async with httpx.AsyncClient() as client:
                        response = await client.request(
                            method,
                            url,
                            json=data,
                            auth=(self.key_id, self.key_secret),
                            headers=self.headers,
                            timeout=settings.payment_timeout,
                        )
                        if response.status_code in transient and attempt < max_attempts:
                            # capped exponential backoff + jitter
                            await asyncio.sleep(
                                min((3 ** attempt) + random.uniform(0, 1.0), 10.0)
                            )
                            continue
                        response.raise_for_status()
                        return response.json()
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt < max_attempts:
                    await asyncio.sleep(
                        min((3 ** attempt) + random.uniform(0, 1.0), 10.0)
                    )
                    continue
                raise
            except httpx.HTTPStatusError as e:
                raise self._http_status_error(e) from e

    @staticmethod
    def _http_status_error(e: httpx.HTTPStatusError) -> httpx.HTTPStatusError:
        """Attach Razorpay's error code/description (from the JSON body when present)
        to the raised exception so callers can surface a precise reason."""
        status = e.response.status_code
        reason = None
        error_code = None
        try:
            body = e.response.json()
            error = body.get("error", {})
            if isinstance(error, dict):
                reason = error.get("description") or error.get("message") or body.get("message")
                error_code = error.get("code")
            else:
                reason = body.get("message") or str(error)
        except Exception:
            body = None
        if reason is None:
            reason = f"HTTP {status}"
        try:
            # httpx.HTTPStatusError supports .__cause__; attach original for trace context
            reason_note = f"[{error_code or status}] {reason}"
            e._razorpay_status = status
            e._razorpay_error_code = error_code
            # include the reason in the exception string for easy logging
            e.args = (f"{status}: {reason_note}",)
        except Exception:
            pass
        return e

    async def create_order(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/orders", data)

    async def fetch_order(self, order_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/orders/{order_id}")

    async def create_payment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/payments", data)

    async def capture_payment(self, payment_id: str, amount: int) -> Dict[str, Any]:
        return await self._request(
            "POST", f"/payments/{payment_id}/capture", {"amount": amount}
        )

    async def fetch_payment(self, payment_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/payments/{payment_id}")

    async def create_refund(self, payment_id: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._request("POST", f"/payments/{payment_id}/refund", data or {})

    async def create_customer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/customers", data)

    async def create_payment_link(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/payment_links", data)
