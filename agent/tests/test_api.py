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


# ------------------------------------------------------------------ the customer's conversations


from app.conversations import MemoryConversations, title_of  # noqa: E402
from tests.fakes import CUS_B  # noqa: E402


@pytest.fixture()
def history_client(tools):
    store = MemoryConversations()
    return TestClient(create_app(tools=tools, tracer=NullTracer(), llm=None, conversations=store)), store


def _bearer_for(customer=CUS_A):
    return {"Authorization": f"Bearer {_jwt(customer)}"}


def _say(client, message, customer=CUS_A, conversation_id=None):
    return client.post(
        "/chat", json={"session_token": _jwt(customer), "message": message, "conversation_id": conversation_id}
    ).json()


def test_a_conversation_is_kept_and_listed_with_the_first_thing_the_customer_wrote(history_client):
    client, _ = history_client
    first = _say(client, "hola")
    listed = client.get("/me/conversations", headers=_bearer_for()).json()
    assert [c["conversation_id"] for c in listed] == [first["conversation_id"]]
    assert listed[0]["title"] == "hola"


def test_a_conversation_comes_back_whole_with_the_cards_that_went_with_each_answer(history_client):
    client, _ = history_client
    first = _say(client, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")
    _say(client, "gracias", conversation_id=first["conversation_id"])
    body = client.get(f"/me/conversations/{first['conversation_id']}", headers=_bearer_for()).json()
    assert [m["role"] for m in body["messages"]] == ["user", "bot", "user", "bot"]
    assert body["messages"][0]["text"].startswith("Me hicieron un cobro")
    assert body["messages"][1]["response"]["case"]["case_id"] == first["case"]["case_id"]


def test_new_conversations_do_not_replace_the_old_ones_and_the_latest_is_first(history_client):
    client, _ = history_client
    older = _say(client, "hola")
    newer = _say(client, "Me hicieron un cobro que no reconozco de 45.50 en Tienda Don Pepe")
    ids = [c["conversation_id"] for c in client.get("/me/conversations", headers=_bearer_for()).json()]
    assert ids == [newer["conversation_id"], older["conversation_id"]]


def test_a_customer_never_sees_another_customers_conversations(history_client):
    client, _ = history_client
    mine = _say(client, "hola", customer=CUS_A)
    assert client.get("/me/conversations", headers=_bearer_for(CUS_B)).json() == []
    assert client.get(f"/me/conversations/{mine['conversation_id']}", headers=_bearer_for(CUS_B)).status_code == 404


def test_writing_into_someone_elses_conversation_id_does_not_expose_it(history_client):
    client, _ = history_client
    mine = _say(client, "hola", customer=CUS_A)
    _say(client, "hola", customer=CUS_B, conversation_id=mine["conversation_id"])  # B reuses A's id
    body = client.get(f"/me/conversations/{mine['conversation_id']}", headers=_bearer_for(CUS_A)).json()
    assert [m["text"] for m in body["messages"] if m["role"] == "user"] == ["hola"]  # only A's turn


def test_the_history_needs_a_valid_session(history_client):
    client, _ = history_client
    assert client.get("/me/conversations").status_code == 401
    assert client.get("/me/conversations", headers={"Authorization": f"Bearer {_jwt(expired=True)}"}).status_code == 401
    assert client.get("/me/conversations/x", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_an_unknown_conversation_is_a_404(history_client):
    client, _ = history_client
    assert client.get("/me/conversations/nope", headers=_bearer_for()).status_code == 404


def test_without_a_store_the_chat_still_works_and_the_history_is_empty(client):
    assert _say(client, "hola")["outcome"]
    assert client.get("/me/conversations", headers=_bearer_for()).json() == []


def test_the_title_is_short_and_one_line():
    assert title_of("  hola\n  mundo ") == "hola mundo"
    assert len(title_of("x" * 200)) == 60 and title_of("x" * 200).endswith("…")
