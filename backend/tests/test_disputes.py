import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import CUS_A, CUS_B, FakeStore

HANDOFF = {
    "request": "Human review: possible fraud",
    "verified_facts": ["TXN-A1 is Declined"],
    "actions_taken": [],
    "evidence": [],
    "open_questions": ["Who made the charge?"],
}


@pytest.fixture()
def store():
    return FakeStore()


@pytest.fixture()
def client(store):
    return TestClient(create_app(store))


@pytest.fixture()
def auth_headers(client):
    token = client.post(
        "/session", json={"customer_id": CUS_A, "document_number": "CC-123"}
    ).json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_dispute(client, headers, transaction_id="TXN-A1"):
    return client.post(
        "/disputes",
        json={"transaction_id": transaction_id, "reason_code": "unrecognized_charge", "summary": "Cargo que no reconozco"},
        headers=headers,
    )


def test_create_dispute_on_own_transaction(client, auth_headers):
    response = _create_dispute(client, auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["customer_id"] == CUS_A
    assert body["evidence"]["transaction"]["transaction_id"] == "TXN-A1"


def test_create_dispute_on_foreign_transaction_is_404(client, auth_headers):
    response = _create_dispute(client, auth_headers, transaction_id="TXN-B1")
    assert response.status_code == 404
    assert client.get("/disputes").status_code in (404, 405)


def test_dispute_not_created_when_transaction_missing(client, auth_headers, store):
    _create_dispute(client, auth_headers, transaction_id="TXN-NOPE")
    assert store.disputes == {}


def test_get_dispute_includes_events(client, auth_headers):
    case_id = _create_dispute(client, auth_headers).json()["case_id"]
    body = client.get(f"/disputes/{case_id}", headers=auth_headers).json()
    assert body["status"] == "open"
    assert body["events"][0]["event"] == "created"


def test_get_foreign_dispute_is_404(client, auth_headers):
    case_id = _create_dispute(client, auth_headers).json()["case_id"]
    other = TestClient(create_app(FakeStore()))
    token = other.post(
        "/session", json={"customer_id": CUS_B, "document_number": "CPF-456"}
    ).json()["session_token"]
    response = other.get(f"/disputes/{case_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_escalate_stores_structured_handoff(client, auth_headers):
    case_id = _create_dispute(client, auth_headers).json()["case_id"]
    response = client.post(f"/disputes/{case_id}/escalate", json={"handoff": HANDOFF}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "escalated"
    assert body["evidence"]["handoff"] == HANDOFF

    events = client.get(f"/disputes/{case_id}", headers=auth_headers).json()["events"]
    assert events[-1]["event"] == "escalated"
    assert events[-1]["payload"] == HANDOFF


def test_escalate_foreign_dispute_is_404(client, auth_headers):
    response = client.post(
        "/disputes/ffffffff-ffff-ffff-ffff-ffffffffffff/escalate",
        json={"handoff": HANDOFF},
        headers=auth_headers,
    )
    assert response.status_code == 404
