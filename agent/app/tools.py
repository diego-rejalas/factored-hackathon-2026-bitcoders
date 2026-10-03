import asyncio
import os

import httpx

from app.gcp_auth import IdentityTokenProvider


# Bounded retries: a call is tried up to MAX_ATTEMPTS times when the backend cannot be reached or answers 502, 503
# or 504, with a short wait between attempts. Every call here is safe to repeat: reads, the login, and the dispute
# writes, which are idempotent (one case per transaction; resolve and escalate do nothing the second time).
# A 4xx is the backend's answer and is never retried.
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.2, 0.6)
# Connecting to a service that is down usually hangs instead of failing, so the connection gets a short limit of
# its own: with the full read timeout per attempt, three attempts took 31 seconds to say "unavailable".
CONNECT_TIMEOUT_SECONDS = 2.0
RETRY_STATUSES = (502, 503, 504)


class ToolError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class BankTools:
    """Thin HTTP clients to the backend banking service.

    Every call forwards the user's session token; the backend re-validates it,
    so enforcement is double (agent pre-check + backend enforcement).
    """

    def __init__(
        self, base_url: str, timeout: float = 10.0, identity: IdentityTokenProvider | None = None
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.http_timeout = httpx.Timeout(timeout, connect=min(CONNECT_TIMEOUT_SECONDS, timeout))
        self.identity = identity

    async def login(self, customer_id: str, document_number: str) -> dict:
        return await self._request(
            "POST", "/session", json={"customer_id": customer_id, "document_number": document_number}
        )

    async def list_transactions(
        self,
        token: str,
        status: str | None = None,
        merchant: str | None = None,
        days: int | None = None,
        limit: int = 50,
    ) -> list:
        params = {"limit": limit}
        if status:
            params["status"] = status
        if merchant:
            params["merchant"] = merchant
        if days is not None:
            params["days"] = days
        body = await self._request("GET", "/me/transactions", token=token, params=params)
        return body if isinstance(body, list) else []

    async def get_transaction(self, token: str, transaction_id: str) -> dict:
        return await self._request("GET", f"/me/transactions/{transaction_id}", token=token)

    async def create_dispute(
        self, token: str, transaction_id: str, reason_code: str, summary: str
    ) -> dict:
        return await self._request(
            "POST",
            "/disputes",
            token=token,
            json={"transaction_id": transaction_id, "reason_code": reason_code, "summary": summary},
        )

    async def get_dispute(self, token: str, case_id: str) -> dict:
        return await self._request("GET", f"/disputes/{case_id}", token=token)

    async def resolve_dispute(self, token: str, case_id: str, resolution: dict) -> dict:
        return await self._request(
            "POST", f"/disputes/{case_id}/resolve", token=token, json={"resolution": resolution}
        )

    async def escalate_dispute(self, token: str, case_id: str, handoff: dict) -> dict:
        return await self._request(
            "POST", f"/disputes/{case_id}/escalate", token=token, json={"handoff": handoff}
        )

    async def _request(self, method: str, path: str, token: str | None = None, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        if self.identity:
            headers["X-Serverless-Authorization"] = f"Bearer {await self.identity.token()}"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = None
        for attempt in range(MAX_ATTEMPTS):
            last = attempt == MAX_ATTEMPTS - 1
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.http_timeout) as client:
                    response = await client.request(method, path, headers=headers, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if last:
                    raise ToolError(503, f"banking service unreachable after {MAX_ATTEMPTS} attempts: {type(error).__name__}")
                await asyncio.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                continue
            if response.status_code in RETRY_STATUSES and not last:
                await asyncio.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                continue
            break
        if response.status_code >= 400:
            detail = response.text[:300]
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise ToolError(response.status_code, str(detail))
        if not response.content:
            return {}
        return response.json()


def bank_tools_from_env() -> BankTools:
    # BANK_IAM_AUDIENCE is set where the backend requires an identity token (Cloud Run with IAM on);
    # elsewhere (local, Railway) it is unset and the call goes out as before.
    audience = os.environ.get("BANK_IAM_AUDIENCE")
    return BankTools(
        os.environ.get("BANK_URL", "http://localhost:8000"),
        identity=IdentityTokenProvider(audience) if audience else None,
    )
