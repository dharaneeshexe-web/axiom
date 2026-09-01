import httpx
import asyncio
import random
from typing import Dict, Any, Optional
from ..config.settings import settings


# ---- Global payment-mode toggle ----
# "live":     call the real Razorpay API (payment_links cap: 30/day per account).
# "simulate": short-circuit money calls so the demo never burns the daily quota.
#             Flip it at runtime via the chat ("don't call razorpay api") or the
#             /payment-mode admin endpoint.
_payment_mode = {"value": settings.payment_mode}


def get_payment_mode() -> str:
    return _payment_mode["value"]


def set_payment_mode(mode: str) -> str:
    mode = mode.strip().lower()
    _payment_mode["value"] = "simulate" if mode in ("simulate", "sim", "off", "fake", "mock") else "live"
    return _payment_mode["value"]


class RazorpayClient:
    def __init__(self):
        self.base_url = settings.razorpay_base_url
        # primary first, then any fallback keys (test-mode payment_links cap is
        # 30/day per account, so a second account extends the demo quota)
        self._creds = settings.razorpay_creds_list
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
        # Transient statuses worth a retry with backoff. Everything else (e.g. 401/400/403)
        # is terminal.
        transient = (429, 500, 502, 503, 504)
        max_attempts = max(1, settings.max_retries + 1)
        last_error: Optional[httpx.HTTPStatusError] = None

        # Try each credential in turn. A daily-cap RATE_LIMIT_EXCEEDED on one account
        # won't reset in seconds, so rotate to the next account instead of backoff-waiting.
        for key_id, key_secret in self._creds:
            rotate = False
            attempt = 0
            while attempt < max_attempts and not rotate:
                attempt += 1
                try:
                    async with self._semaphore:
                        async with httpx.AsyncClient() as client:
                            response = await client.request(
                                method,
                                url,
                                json=data,
                                auth=(key_id, key_secret),
                                headers=self.headers,
                                timeout=settings.payment_timeout,
                            )
                    # Daily cap reached for THIS account -> move to the next key.
                    if self._is_daily_cap_limit(response):
                        last_error = self._http_status_error(
                            httpx.HTTPStatusError(
                                f"{response.status_code} {response.reason_phrase}",
                                request=response.request,
                                response=response,
                            )
                        )
                        rotate = True
                        break
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
                    # network-level terminal on this key; rotate to the next
                    rotate = True
                except httpx.HTTPStatusError as e:
                    last_error = self._http_status_error(e)
                    # terminal daily-cap on this account -> rotate to next key
                    if e.response is not None and self._is_daily_cap_limit(e.response):
                        rotate = True
                    else:
                        raise last_error

            # If rotation was requested and there are more keys, try them.
            if rotate and (key_id, key_secret) is not self._creds[-1]:
                continue
            break

        if last_error is not None:
            raise last_error
        raise httpx.ConnectError(
            f"request failed across {len(self._creds)} credential(s): {url}",
            request=None,
        )

    _DAILY_CAP_MARKERS = (
        "test mode limit",
        "limit of",
        "daily limit",
        "limit reached",
        "quota",
        "per day",
    )

    @staticmethod
    def _is_daily_cap_limit(response: httpx.Response) -> bool:
        """True only when a 429 is a hard daily-cap quota (e.g. payment_link limit exhausted)
        rather than a transient burst. This drives circular key rotation: bursts keep
        backing off on the SAME account, while a genuine daily cap rotates to the next key."""
        if response.status_code != 429:
            return False
        try:
            body = response.json()
            error = body.get("error", {})
            if isinstance(error, dict):
                desc = f"{error.get('description') or ''} {error.get('message') or ''}"
            else:
                desc = str(body.get("message") or error or "")
        except Exception:
            desc = ""
        low = desc.lower()
        return any(marker in low for marker in RazorpayClient._DAILY_CAP_MARKERS)

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
