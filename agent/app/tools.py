import asyncio
import os

import httpx

from app.gcp_auth import IdentityTokenProvider
from app.observability import REQUEST_ID_HEADER, request_id_var


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
        self, token: str, transaction_id: str | None, reason_code: str, summary: str
    ) -> dict:
        return await self._request(
            "POST",
            "/disputes",
            token=token,
            json={"transaction_id": transaction_id, "reason_code": reason_code, "summary": summary},
        )

    async def get_dispute(self, token: str, case_id: str) -> dict:
        return await self._request("GET", f"/disputes/{case_id}", token=token)

    async def list_disputes(self, token: str) -> list:
        body = await self._request("GET", "/me/disputes", token=token)
        return body if isinstance(body, list) else []

    async def resolve_dispute(self, token: str, case_id: str, resolution: str) -> dict:
        return await self._request(
            "POST", f"/disputes/{case_id}/resolve", token=token, json={"resolution": resolution}
        )

    async def escalate_dispute(self, token: str, case_id: str, handoff: dict) -> dict:
        return await self._request(
            "POST", f"/disputes/{case_id}/escalate", token=token, json={"handoff": handoff}
        )

    # --- admin console: thin proxies to the backend (same double-enforcement as /session) ----

    async def admin_login(self, username: str, password: str) -> dict:
        return await self._request(
            "POST", "/admin/session", json={"username": username, "password": password}
        )

    async def admin_list_disputes(
        self,
        token: str,
        status: str | None = None,
        customer_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if customer_id:
            params["customer_id"] = customer_id
        return await self._request("GET", "/admin/disputes", token=token, params=params)

    async def admin_get_dispute(self, token: str, case_id: str) -> dict:
        return await self._request("GET", f"/admin/disputes/{case_id}", token=token)

    async def admin_transition(
        self,
        token: str,
        case_id: str,
        action: str,
        note: str,
        resolution: str | None = None,
    ) -> dict:
        body: dict = {"action": action, "note": note}
        if resolution:
            body["resolution"] = resolution
        return await self._request(
            "POST", f"/admin/disputes/{case_id}/transition", token=token, json=body
        )

    async def admin_metrics(self, token: str, window_hours: int | None = None) -> dict:
        params = {"window": window_hours} if window_hours is not None else None
        return await self._request("GET", "/admin/metrics", token=token, params=params)

    async def get_meta_data(self, token: str) -> dict:
        return await self._request("GET", "/meta/data", token=token)

    async def get_demo_scenarios(self) -> dict:
        return await self._request("GET", "/meta/demo-scenarios")

    async def ready(self) -> bool:
        """True when the backend answers and can reach the database."""
        try:
            await self._request("GET", "/ready")
        except ToolError:
            return False
        return True

    async def _request(self, method: str, path: str, token: str | None = None, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        request_id = request_id_var.get()
        if request_id:
            # The same id the customer's request carries, so the backend's log line for this call can be matched.
            headers[REQUEST_ID_HEADER] = request_id
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
