import os

import httpx

from app.gcp_auth import IdentityTokenProvider


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
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.request(method, path, headers=headers, **kwargs)
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
