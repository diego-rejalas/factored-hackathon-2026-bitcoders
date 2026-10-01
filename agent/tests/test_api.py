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
