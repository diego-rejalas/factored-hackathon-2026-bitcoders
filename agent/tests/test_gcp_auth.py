import httpx
import pytest

from app.gcp_auth import IdentityTokenProvider
from app.tools import BankTools, bank_tools_from_env


def metadata_transport(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=f"id-token-{len(calls)}\n")

    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_token_is_requested_with_audience_and_metadata_header():
    calls: list = []
    provider = IdentityTokenProvider("https://backend.run.app", transport=metadata_transport(calls))
    assert await provider.token() == "id-token-1"
    assert calls[0].url.params["audience"] == "https://backend.run.app"
    assert calls[0].headers["Metadata-Flavor"] == "Google"


@pytest.mark.anyio
async def test_token_is_cached_until_near_expiry(monkeypatch):
    calls: list = []
    provider = IdentityTokenProvider("https://backend.run.app", transport=metadata_transport(calls))
    await provider.token()
    await provider.token()
    assert len(calls) == 1
    provider._expires_at = 0.0
    assert await provider.token() == "id-token-2"


@pytest.mark.anyio
async def test_backend_receives_identity_and_session_tokens_in_separate_headers(monkeypatch):
    seen: dict = {}

    def backend(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    provider = IdentityTokenProvider("https://backend.run.app", transport=metadata_transport([]))
    tools = BankTools("https://backend.run.app", identity=provider)
    real = httpx.AsyncClient

    def client_with_fake_backend(**kwargs):
        # The provider passes its own metadata transport; every other client talks to the fake backend.
        kwargs.setdefault("transport", httpx.MockTransport(backend))
        return real(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_with_fake_backend)
    await tools._request("GET", "/me", token="session-jwt")
    assert seen["x-serverless-authorization"] == "Bearer id-token-1"
    assert seen["authorization"] == "Bearer session-jwt"


def test_identity_is_only_enabled_when_the_audience_is_set(monkeypatch):
    monkeypatch.delenv("BANK_IAM_AUDIENCE", raising=False)
    assert bank_tools_from_env().identity is None
    monkeypatch.setenv("BANK_IAM_AUDIENCE", "https://backend.run.app")
    assert bank_tools_from_env().identity.audience == "https://backend.run.app"
