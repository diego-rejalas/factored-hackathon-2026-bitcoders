import os
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tracing import NullTracer
from tests.fakes import CUS_A, FakeBankTools

TEST_SECRET = os.environ.get("SESSION_JWT_SECRET", "test-secret")


@pytest.fixture()
def tools():
    return FakeBankTools()


@pytest.fixture()
def client(tools):
    return TestClient(create_app(tools=tools, tracer=NullTracer(), llm=None))


def _jwt(customer_id=CUS_A, expired=False):
    now = int(time.time())
    payload = {
        "sub": customer_id,
        "iat": now,
        "exp": now - 10 if expired else now + 3600,
        "iss": "backend-sandbox",
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok", "service": "agent"}


def test_session_is_a_thin_proxy(client):
    response = client.post("/session", json={"customer_id": CUS_A, "document_number": "x"})
    assert response.status_code == 200
    assert response.json()["session_token"] == f"token-{CUS_A}"


def test_session_proxy_maps_backend_401(client):
    response = client.post("/session", json={"customer_id": CUS_A, "document_number": "bad"})
    assert response.status_code == 401


def test_chat_rejects_garbage_token(client):
    response = client.post(
        "/chat",
        json={"session_token": "garbage", "message": "hola"},
    )
    assert response.status_code == 401


def test_chat_rejects_expired_token(client):
    response = client.post(
        "/chat",
        json={"session_token": _jwt(expired=True), "message": "hola"},
    )
    assert response.status_code == 401


def test_chat_resolves_a_dispute_end_to_end(client):
    response = client.post(
        "/chat",
        json={
            "session_token": _jwt(),
            "message": "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "resolved"
    assert body["conversation_id"]
    assert "45.50" in body["reply"] or "45,50" in body["reply"]


def test_chat_conversation_continuity_via_conversation_id(client):
    first = client.post(
        "/chat",
        json={"session_token": _jwt(), "message": "Me hicieron un cobro que no reconozco"},
    ).json()
    second = client.post(
        "/chat",
        json={
            "session_token": _jwt(),
            "message": "fue el cobro de 120 en Farmacia Central",
            "conversation_id": first["conversation_id"],
        },
    ).json()
    assert first["outcome"] == "clarify"
    assert second["outcome"] == "resolved"


def test_chat_precheck_is_optional_without_shared_secret(client, monkeypatch):
    monkeypatch.delenv("SESSION_JWT_SECRET", raising=False)
    response = client.post(
        "/chat",
        json={
            "session_token": f"token-{CUS_A}",
            "message": "cobro de 45.50 en Tienda Don Pepe",
        },
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "resolved"


# --- CORS: the browser chat calls the agent from another origin ------------------------------

PREFLIGHT = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}


def _cors_client(monkeypatch, origins):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)
    return TestClient(create_app(tools=FakeBankTools(), tracer=NullTracer(), llm=None))


def test_cors_allows_a_configured_origin(monkeypatch):
    client = _cors_client(monkeypatch, "https://app.example.com, https://other.example.com/")
    for origin in ("https://app.example.com", "https://other.example.com"):
        response = client.options("/chat", headers={"Origin": origin, **PREFLIGHT})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_an_unlisted_origin(monkeypatch):
    client = _cors_client(monkeypatch, "https://app.example.com")
    response = client.options("/chat", headers={"Origin": "https://evil.example.com", **PREFLIGHT})
    assert "access-control-allow-origin" not in response.headers


def test_cors_is_off_without_configuration(monkeypatch):
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    client = TestClient(create_app(tools=FakeBankTools(), tracer=NullTracer(), llm=None))
    response = client.options("/chat", headers={"Origin": "https://app.example.com", **PREFLIGHT})
    assert "access-control-allow-origin" not in response.headers


def test_cors_refuses_a_wildcard(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        create_app(tools=FakeBankTools(), tracer=NullTracer(), llm=None)


# ------------------------------------------------------------------ transaction picked in the app, case info, safe fallback


def _chat(client, message, token=None, **extra):
    return client.post("/chat", json={"session_token": token or _jwt(), "message": message, **extra})


def test_chat_with_a_picked_transaction_resolves_and_says_which_case(client, tools):
    response = _chat(client, "No reconozco este cobro", transaction_id="TXN-1")
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "resolved"
    assert body["case_id"] and body["case_status"] == "auto_resolved"
    assert body["case_id"] in body["reply"]


def test_an_escalation_about_a_transaction_returns_its_case(client, tools):
    tools.transactions.append(_tx_big())
    body = _chat(client, "No reconozco este cobro", transaction_id="TXN-BIG").json()
    assert body["outcome"] == "escalated"
    assert body["case_id"] == body["handoff"]["case_id"]
    assert body["case_status"] == "escalated"


def test_a_turn_without_a_case_has_none(client):
    body = _chat(client, "hola").json()
    assert body["case_id"] is None and body["case_status"] is None


def test_the_picked_transaction_is_optional_and_bounded(client):
    assert _chat(client, "hola", transaction_id=None).status_code == 200
    assert _chat(client, "hola", transaction_id="x" * 101).status_code == 422


def test_when_the_backend_is_down_the_customer_gets_a_safe_answer_not_an_error(client, tools, monkeypatch):
    from app.tools import ToolError

    async def down(*args, **kwargs):
        raise ToolError(503, "banking service unreachable after 3 attempts: ConnectError")

    monkeypatch.setattr(tools, "list_transactions", down)
    monkeypatch.setattr(tools, "get_transaction", down)
    response = _chat(client, "No reconozco el cobro de 45.50")
    assert response.status_code == 200  # a answer, not a 502 and not a stack trace
    body = response.json()
    assert body["outcome"] == "unavailable"
    assert "ningún cambio" in body["reply"] and "503" not in body["reply"] and "unreachable" not in body["reply"]
    assert body["case_id"] is None and body["handoff"] is None


def test_the_safe_answer_follows_the_customers_language(client, tools, monkeypatch):
    from app.tools import ToolError

    async def down(*args, **kwargs):
        raise ToolError(503, "down")

    monkeypatch.setattr(tools, "list_transactions", down)
    body = _chat(client, "Não reconheço esta cobrança de 45.50").json()
    assert body["outcome"] == "unavailable" and "Nenhuma alteração" in body["reply"]


def test_an_expired_session_is_still_a_401_not_a_safe_answer(client, tools, monkeypatch):
    from app.tools import ToolError

    async def unauthorized(*args, **kwargs):
        raise ToolError(401, "Invalid or expired session token")

    monkeypatch.setattr(tools, "list_transactions", unauthorized)
    assert _chat(client, "No reconozco el cobro de 45.50").status_code == 401


def _tx_big():
    from tests.fakes import _tx

    return _tx("TXN-BIG", CUS_A, "Electro Mega", "Declined", 600.00)
