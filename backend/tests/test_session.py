import jwt
import pytest
from fastapi.testclient import TestClient

from app.auth import get_session_secret
from app.main import create_app
from tests.fakes import CUS_A, CUS_B, FakeStore


@pytest.fixture()
def store():
    return FakeStore()


@pytest.fixture()
def client(store):
    return TestClient(create_app(store))


def _login(client, customer_id=CUS_A, document_number="CC-123"):
    return client.post("/session", json={"customer_id": customer_id, "document_number": document_number})


def test_session_issues_bearer_token(client):
    response = _login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = jwt.decode(
        body["session_token"], get_session_secret(), algorithms=["HS256"], issuer="backend-sandbox"
    )
    assert payload["sub"] == CUS_A


def test_session_rejects_wrong_document(client):
    response = _login(client, document_number="nope")
    assert response.status_code == 401


def test_session_rejects_unknown_customer(client):
    response = _login(client, customer_id="CUS-NOPE")
    assert response.status_code == 401


def test_missing_token_is_unauthorized(client):
    for path in ["/me", "/me/transactions", "/me/transactions/TXN-A1", "/disputes/x"]:
        assert client.get(path).status_code == 401
    assert client.post("/disputes", json={}).status_code == 401


def test_garbage_and_expired_tokens_are_unauthorized(client, store):
    garbage = client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert garbage.status_code == 401

    expired = jwt.encode(
        {"sub": CUS_A, "exp": 1, "iss": "backend-sandbox"},
        get_session_secret(),
        algorithm="HS256",
    )
    expired_response = client.get("/me", headers={"Authorization": f"Bearer {expired}"})
    assert expired_response.status_code == 401


def test_health_is_public(client):
    assert client.get("/health").json()["status"] == "ok"


def test_login_identity_never_leaks_between_customers(client):
    a = _login(client).json()["session_token"]
    b = _login(client, CUS_B, "CPF-456").json()["session_token"]
    assert jwt.decode(a, options={"verify_signature": False})["sub"] == CUS_A
    assert jwt.decode(b, options={"verify_signature": False})["sub"] == CUS_B
